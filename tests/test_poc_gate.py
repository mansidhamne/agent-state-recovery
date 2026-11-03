import pandas as pd
import pytest

from poc_gate import evaluate, harness_problems, poc_jobs


def row(cell="clean", mode="M0", **kw):
    base = {"cell": cell, "mode": mode, "policy_mode": "observe", "status": "ok", "pass": True,
            "pass_ignoring_irreversible": True, "dependent": False, "fault_class": None,
            "forbidden_attempted": False, "model_declined": False, "llm_calls": 18,
            "prompt_tokens": 45000, "completion_tokens": 5000, "cost_usd": 0.0}
    return {**base, **kw}


def frame(clean_pass=True, dependent=True, attempted=True, declined=False):
    return pd.DataFrame([
        row(**{"pass": clean_pass}),
        row("FA1xA1", dependent=dependent, fault_class="accidental", **{"pass": False}),
        row("FD1xA2", fault_class="adversarial", forbidden_attempted=attempted, model_declined=declined),
    ])


def test_all_gates_pass():
    report = evaluate(frame(), 0.1, 0.4)
    assert report["go"] and all(report["gates"].values())


def test_low_clean_success_is_no_go():
    report = evaluate(frame(clean_pass=False), 0.1, 0.4)
    assert not report["go"] and not report["gates"]["clean_success"]


def test_no_dependence_is_no_go():
    assert not evaluate(frame(dependent=False), 0.1, 0.4)["gates"]["fa1_dependence"]


def test_model_declined_warns_but_does_not_block():
    report = evaluate(frame(attempted=False, declined=True), 0.1, 0.4)
    assert report["adversarial_status"].startswith("WARN") and report["go"]


def test_instruction_not_reaching_executor_is_no_go():
    report = evaluate(frame(attempted=False), 0.1, 0.4)
    assert report["adversarial_status"].startswith("FAIL") and not report["go"]


def test_excessive_cost_is_no_go():
    report = evaluate(frame(), 5.0, 20.0)
    assert not report["gates"]["budget"] and not report["go"]


def test_measured_cost_is_used_over_prices():
    df = frame()
    df["cost_usd"] = 0.01
    report = evaluate(df, 5.0, 20.0)
    assert report["cost_source"] == "measured"
    assert report["projected_matrix_usd"] == pytest.approx(5.88) and report["go"]


def test_high_measured_cost_is_no_go():
    df = frame()
    df["cost_usd"] = 0.2  # 588 x 0.2 = 117.6, above 60% of the $50 key budget
    assert not evaluate(df, None, None)["gates"]["budget"]


def test_unknown_price_skips_the_budget_gate():
    report = evaluate(frame(), None, None)
    assert "budget" not in report["gates"] and report["go"]
    assert report["budget_status"].startswith("not checked")


def test_projection_uses_matrix_size():
    # 588 runs x (45000 x $0.1/M + 5000 x $0.4/M) = 588 x $0.0065
    assert evaluate(frame(), 0.1, 0.4)["projected_matrix_usd"] == pytest.approx(3.822)


def test_jobs_cover_doc_counts_and_dev_only():
    jobs = poc_jobs(["T01", "T02"], ["FA1xA1", "FD1xA2"])
    assert sum(j["cell"] is None for j in jobs) == 6
    assert sum(j["kind"] == "run" and j["cell"] is not None for j in jobs) == 8
    assert sum(j["kind"] == "recover" for j in jobs) == 8
    assert jobs[0]["cell"] is None
    assert {j["task"] for j in jobs} == {"T01", "T02"}


def test_harness_problems_flag_failed_calls(tmp_path, log):
    log.emit("llm_call", status="error", agent_field=None)
    log.path.rename(tmp_path / "events.jsonl") if log.path != tmp_path / "events.jsonl" else None
    assert harness_problems(tmp_path)
