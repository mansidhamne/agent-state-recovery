"""Plain ReAct loop over the LLM client (doc section 9.6)."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path

from mccr.llm import LLMClient, LLMTimeout, RunCtx
from mccr.schema import AgentCtx
from mccr.tools import ToolRunner

PROMPTS = Path(__file__).resolve().parents[2] / "prompts"
ROLES = ("A1", "A2", "A3", "A4", "A5")
_REPAIR = 'Respond with a tool call, or with JSON: {"thought": "...", "action": "<tool>", "args": {...}}.'
_JSON = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class InvocationResult:
    status: str  # finished, step_cap, timeout or error
    steps: int


def role_prompt(role: str) -> str:
    return next(PROMPTS.glob(f"{role}_*.md")).read_text(encoding="utf-8")


def prompt_hashes() -> dict:
    hashes = {role: hashlib.sha256(role_prompt(role).encode()).hexdigest()[:16] for role in ROLES}
    verifier = (PROMPTS / "verifier.md").read_text(encoding="utf-8")
    hashes["verifier"] = hashlib.sha256(verifier.encode()).hexdigest()[:16]
    return hashes


def parse_json_action(text: str | None) -> dict | None:
    match = _JSON.search(text or "")
    if not match:
        return None
    try:
        parsed = json.loads(match.group())
    except ValueError:
        return None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("action"), str):
        return None
    args = parsed.get("args")
    return {"id": None, "name": parsed["action"], "args": args if isinstance(args, dict) else {}}


def run_agent(role: str, task_spec: str, llm: LLMClient, tools: ToolRunner,
              *, step_cap: int, ctx: AgentCtx, seed: int | None = None) -> InvocationResult:
    log = tools.log
    messages = [{"role": "system", "content": f"{role_prompt(role)}\n\n{task_spec}"},
                {"role": "user", "content": "Do your part of the task now. Call finish when done."}]
    specs = tools.specs_for(role)
    steps, repaired = 0, False

    def end(status: str) -> InvocationResult:
        log.emit("invocation_end", replace(ctx, step=steps), status=status, steps=steps)
        return InvocationResult(status, steps)

    while steps < step_cap:
        step_ctx = replace(ctx, step=steps)
        try:
            result = llm.chat(messages, specs, run_ctx=RunCtx(log, step_ctx, seed))
        except LLMTimeout:
            return end("timeout")
        except Exception:  # a failed call must end this invocation with a status, not lose the run
            return end("error")

        calls = result.tool_calls
        native = bool(calls)
        if not calls:
            action = parse_json_action(result.content)
            if action is None:
                if repaired:
                    return end("error")
                repaired = True
                messages += [{"role": "assistant", "content": result.content or ""},
                             {"role": "user", "content": _REPAIR}]
                continue
            calls = [action]
        repaired = False

        if native:
            messages.append({"role": "assistant", "content": result.content or "", "tool_calls": [
                {"id": c["id"], "type": "function",
                 "function": {"name": c["name"], "arguments": json.dumps(c["args"])}} for c in calls]})
        else:
            messages.append({"role": "assistant", "content": result.content or ""})

        for call in calls:
            call_ctx = replace(ctx, step=steps)
            observation = tools.run(role, call["name"], call["args"], ctx=call_ctx)
            log.emit("react_step", call_ctx, thought=result.content, action=call["name"],
                     args=call["args"],
                     observation_digest=hashlib.sha256(observation.encode()).hexdigest()[:16])
            steps += 1
            if native:
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": observation})
            else:
                messages.append({"role": "user", "content": f"Observation: {observation}"})
            if call["name"] == "finish":
                return end("finished")
            if steps >= step_cap:
                return end("step_cap")
    return end("step_cap")
