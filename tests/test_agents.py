import pytest

from mccr.agents import parse_json_action, prompt_hashes, run_agent
from mccr.llm import LLMResult, LLMTimeout, ScriptedClient
from mccr.schema import AgentCtx

CTX = AgentCtx("A1", "inv_A1_0", 0)


class Canned:
    def __init__(self, results):
        self.results = iter(results)
        self.messages = []

    def chat(self, messages, tools, *, run_ctx):
        self.messages = list(messages)
        item = next(self.results)
        if isinstance(item, Exception):
            raise item
        return item


def end_event(log):
    return [e for e in log.events if e["type"] == "invocation_end"][-1]


def test_finish_ends_invocation(make_runner, log):
    llm = ScriptedClient({"A1": [{"name": "finish", "args": {"summary": "x"}}]})
    result = run_agent("A1", "spec", llm, make_runner(), step_cap=8, ctx=CTX)
    assert (result.status, result.steps) == ("finished", 1)
    assert end_event(log)["status"] == "finished"


def test_step_cap_ends_invocation(make_runner):
    action = {"name": "list_dir", "args": {"path": "inputs/fim"}}
    llm = ScriptedClient({"A1": [action] * 10})
    result = run_agent("A1", "spec", llm, make_runner(), step_cap=3, ctx=CTX)
    assert (result.status, result.steps) == ("step_cap", 3)


def test_timeout_recorded_not_raised(make_runner):
    result = run_agent("A1", "spec", Canned([LLMTimeout("t")]), make_runner(), step_cap=3, ctx=CTX)
    assert result.status == "timeout"


def test_other_llm_error_recorded_not_raised(make_runner):
    result = run_agent("A1", "spec", Canned([RuntimeError("boom")]), make_runner(), step_cap=3, ctx=CTX)
    assert result.status == "error"


def test_json_action_fallback(make_runner, board):
    text = '{"thought": "post", "action": "board_add", "args": {"topic": "t", "text": "x"}}'
    done = '{"thought": "done", "action": "finish", "args": {"summary": "s"}}'
    llm = Canned([LLMResult(content=text), LLMResult(content=done)])
    assert run_agent("A1", "spec", llm, make_runner(), step_cap=5, ctx=CTX).status == "finished"
    assert board.dump()[0].text == "x"


def test_bad_output_gets_one_repair_then_error(make_runner):
    llm = Canned([LLMResult(content="no json"), LLMResult(content="still none")])
    assert run_agent("A1", "spec", llm, make_runner(), step_cap=5, ctx=CTX).status == "error"


def test_native_tool_messages_are_paired(make_runner):
    call = {"id": "c1", "name": "list_dir", "args": {"path": "inputs/fim"}}
    finish = {"id": "c2", "name": "finish", "args": {}}
    llm = Canned([LLMResult(tool_calls=[call]), LLMResult(tool_calls=[finish])])
    run_agent("A1", "spec", llm, make_runner(), step_cap=5, ctx=CTX)
    assert llm.messages[2]["tool_calls"][0]["id"] == "c1"
    assert llm.messages[3] ["role"] == "tool" and llm.messages[3]["tool_call_id"] == "c1"


@pytest.mark.parametrize("text", [None, "", "text", '{"a": 1}', "{bad"])
def test_parse_json_action_rejects(text):
    assert parse_json_action(text) is None


def test_prompt_hashes_cover_roles_and_verifier():
    hashes = prompt_hashes()
    assert set(hashes) == {"A1", "A2", "A3", "A4", "A5", "verifier"}
    assert hashes == prompt_hashes()
    assert len(set(hashes.values())) == 6


def test_thoughts_logged(make_runner, log):
    llm = Canned([LLMResult(content="thinking", tool_calls=[{"id": "c", "name": "finish", "args": {}}])])
    run_agent("A1", "spec", llm, make_runner(), step_cap=5, ctx=CTX)
    assert [e for e in log.events if e["type"] == "react_step"][0]["thought"] == "thinking"
