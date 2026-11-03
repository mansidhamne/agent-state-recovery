import pytest

from mccr.llm import RunCtx, header_float, log_call
from mccr.schema import AgentCtx


@pytest.mark.parametrize("value,expected", [
    ("1.195e-05", 1.195e-05), ("0.0", 0.0), (None, None), ("n/a", None),
])
def test_header_float(value, expected):
    headers = {} if value is None else {"x-litellm-response-cost": value}
    assert header_float(headers, "x-litellm-response-cost") == expected


def test_cost_is_logged_and_defaults_to_none(log):
    run_ctx = RunCtx(log, AgentCtx("A1", "inv_A1_0", 0))
    log_call(run_ctx, "m", [], None, 1.0, "ok", {}, 0.5)
    log_call(run_ctx, "m", [], None, 1.0, "ok")
    assert [e["cost_usd"] for e in log.events] == [0.5, None]
