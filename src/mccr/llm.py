"""LLM backends (doc section 9.4). ScriptedClient is for debugging only (D11)."""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from typing import Protocol

from mccr.logging import EventLog
from mccr.schema import AgentCtx

BASE_URL = "https://tritonai-api.ucsd.edu/v1"


class LLMTimeout(Exception):
    pass


@dataclass
class RunCtx:
    log: EventLog
    ctx: AgentCtx
    seed: int | None = None


@dataclass
class LLMResult:
    content: str | None = None
    tool_calls: list[dict] = field(default_factory=list)  # {"id", "name", "args"}
    prompt_tokens: int = 0
    completion_tokens: int = 0
    finish_reason: str | None = None


class LLMClient(Protocol):
    def chat(self, messages: list[dict], tools: list[dict] | None, *, run_ctx: RunCtx) -> LLMResult: ...


def prompt_hash(messages: list[dict]) -> str:
    return hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest()[:16]


def log_call(run_ctx: RunCtx, model: str, messages: list[dict], result: LLMResult | None,
             latency_ms: float, status: str, headers: dict | None = None,
             cost_usd: float | None = None) -> None:
    run_ctx.log.emit("llm_call", run_ctx.ctx, model=model, prompt_hash=prompt_hash(messages),
                     prompt_tokens=result.prompt_tokens if result else 0,
                     completion_tokens=result.completion_tokens if result else 0,
                     latency_ms=latency_ms, status=status, ratelimit_headers=headers or {},
                     cost_usd=cost_usd,
                     finish_reason=result.finish_reason if result else None)


class ScriptedClient:
    """Plays a script per role. An entry is a list of actions or a generator function.

    A generator yields {"name", "args"} actions and receives each tool observation.
    Calls without tools are verifier calls and go to script["verifier"](messages).
    """

    model = "scripted"

    def __init__(self, script: dict):
        self.script = script
        self._running: dict[str, object] = {}
        self._calls = 0

    def chat(self, messages: list[dict], tools: list[dict] | None, *, run_ctx: RunCtx) -> LLMResult:
        self._calls += 1
        if tools is None:
            result = LLMResult(content=self.script["verifier"](messages), finish_reason="stop")
        else:
            action = self._next_action(messages, run_ctx.ctx)
            result = LLMResult(tool_calls=[{"id": f"call_{self._calls}", "name": action["name"],
                                            "args": action["args"]}], finish_reason="tool_calls")
        log_call(run_ctx, self.model, messages, result, 0.0, "ok")
        return result

    def _next_action(self, messages: list[dict], ctx: AgentCtx) -> dict:
        finish = {"name": "finish", "args": {"summary": "script ended"}}
        running = self._running.get(ctx.invocation)
        try:
            if running is None:
                entry = self.script[ctx.agent]
                running = entry() if callable(entry) else iter(entry)
                self._running[ctx.invocation] = running
                return next(running)
            if hasattr(running, "send"):
                return running.send(messages[-1].get("content"))
            return next(running)
        except StopIteration:
            return finish


class TritonAIClient:
    """OpenAI-compatible client. The SDK retries 429, 5xx and connection errors."""

    def __init__(self, model: str, temperature: float = 0.0, max_tokens: int = 1024,
                 timeout_s: float = 120.0, max_retries: int = 4, use_seed: bool = False):
        from openai import OpenAI

        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.use_seed = use_seed
        self.client = OpenAI(api_key=os.environ["TRITONAI_API_KEY"], base_url=BASE_URL,
                             timeout=timeout_s, max_retries=max_retries)

    def chat(self, messages: list[dict], tools: list[dict] | None, *, run_ctx: RunCtx) -> LLMResult:
        import openai

        kwargs: dict = {"model": self.model, "messages": messages, "temperature": self.temperature,
                        "max_tokens": self.max_tokens}
        if tools:
            kwargs["tools"] = tools
        if self.use_seed and run_ctx.seed is not None:
            kwargs["seed"] = run_ctx.seed
        start = time.perf_counter()
        try:
            raw = self.client.chat.completions.with_raw_response.create(**kwargs)
        except openai.APITimeoutError as e:
            log_call(run_ctx, self.model, messages, None, _ms(start), "timeout")
            raise LLMTimeout(str(e)) from e
        except openai.OpenAIError:
            log_call(run_ctx, self.model, messages, None, _ms(start), "error")
            raise
        response = raw.parse()
        choice = response.choices[0]
        result = LLMResult(content=choice.message.content, finish_reason=choice.finish_reason,
                           prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
                           completion_tokens=response.usage.completion_tokens if response.usage else 0)
        for call in choice.message.tool_calls or []:
            result.tool_calls.append({"id": call.id, "name": call.function.name,
                                      "args": _parse_args(call.function.arguments)})
        headers = {k: v for k, v in raw.headers.items() if k.startswith("x-ratelimit")}
        # The proxy reports what the call cost, reasoning tokens included.
        cost = header_float(raw.headers, "x-litellm-response-cost")
        log_call(run_ctx, response.model, messages, result, _ms(start), "ok", headers, cost)
        return result


def header_float(headers, name: str) -> float | None:
    try:
        return float(headers.get(name))
    except (TypeError, ValueError):
        return None


def _ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000


def _parse_args(text: str | None) -> dict:
    try:
        parsed = json.loads(text or "{}")
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
