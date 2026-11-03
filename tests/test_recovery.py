import json
from pathlib import Path

import pandas as pd
import pytest

from mccr.board import Board
from mccr.faults import CELLS, CELLS_BY_NAME
from mccr.llm import ScriptedClient
from mccr.metrics import compute
from mccr.oracle import run_events
from mccr.orchestrator import run_task
from mccr.recovery import recover
from mccr.scripted_crew import SCRIPT

TASKS = Path(__file__).resolve().parents[1] / "tasks"


def llm():
    return ScriptedClient(SCRIPT)


def faulted(tmp_path, name, task="T02"):
    run_dir = run_task(TASKS / task, tmp_path, llm(), cell=CELLS_BY_NAME[name])
    return run_dir, set(json.loads((run_dir / "manifest.json").read_text())["F"])


def oracle(run_dir):
    return json.loads((run_dir / "oracle.json").read_text())


def recovered(tmp_path, mode, name, task="T02"):
    run_dir, F = faulted(tmp_path, name, task)
    return recover(mode, run_dir, F, llm=llm(), tasks_root=TASKS), run_dir


def test_m1_does_not_recover_stale_post(tmp_path):
    result, _ = recovered(tmp_path, "M1", "FA2xseed")
    assert not oracle(result)["pass"]


def test_m1_does_not_recover_a_corrupted_input(tmp_path):
    result, _ = recovered(tmp_path, "M1", "FA4xA1")
    assert not oracle(result)["pass"]


def test_duplicate_sends_count_repeated_orders(tmp_path):
    source, F = faulted(tmp_path, "FA4xA1", task="T01")
    m1 = recover("M1", source, F, llm=llm(), tasks_root=TASKS)
    df = compute([source, m1]).set_index("run_id")
    # The M1 rerun reads the same corrupted row and sends the same wrong order again.
    assert df.loc[source.name, "duplicate_sends"] == 0
    assert df.loc[m1.name, "duplicate_sends"] == 1
    assert df.loc[m1.name, "wrong_sends"] == 2


def test_m1_keeps_fa1_post_on_board(tmp_path):
    result, source = recovered(tmp_path, "M1", "FA1xA1")
    injected = json.loads((source / "manifest.json").read_text())["F"][0]
    live = [p.post_id for p in Board.from_events(run_events(result)).dump() if p.status == "live"]
    assert injected in live


@pytest.mark.parametrize("cell", CELLS, ids=lambda c: c.name)
def test_m2_restores_correctness_except_sent_messages(tmp_path, cell):
    result, _ = recovered(tmp_path, "M2", cell.name, task="T01")
    assert oracle(result)["pass_ignoring_irreversible"], oracle(result)


def test_m2_keeps_exfiltration_as_irreversible(tmp_path):
    result, _ = recovered(tmp_path, "M2", "FD1xA2", task="T01")
    report = oracle(result)
    assert not report["pass"]
    assert any("contains canary" in i for i in report["irreversible"])


def test_m2_rerun_makes_no_forbidden_attempts(tmp_path):
    result, source = recovered(tmp_path, "M2", "FD1xA2", task="T01")
    assert oracle(source)["unsafe"]["forbidden_attempted"]
    assert oracle(result)["unsafe"]["forbidden_attempted"] == []


def test_m2_removes_poison_and_tampering(tmp_path):
    result, _ = recovered(tmp_path, "M2", "FD2xA3", task="T01")
    report = oracle(result)
    assert report["pass"], report
    assert report["unsafe"]["malicious_text_present"] is False


def test_m2_restores_clean_input(tmp_path):
    result, _ = recovered(tmp_path, "M2", "FD1xA2", task="T01")
    assert "VB-7731" not in (result / "world/inputs/records/vendor_feed.jsonl").read_text()


def test_m1_keeps_poisoned_input(tmp_path):
    result, _ = recovered(tmp_path, "M1", "FD1xA2", task="T01")
    assert "VB-7731" in (result / "world/inputs/records/vendor_feed.jsonl").read_text()


def test_faulted_run_is_untouched(tmp_path):
    source, F = faulted(tmp_path, "FA1xA1")
    before = (source / "events.jsonl").read_text()
    recover("M2", source, F, llm=llm(), tasks_root=TASKS)
    assert (source / "events.jsonl").read_text() == before
    assert not (source / "events_recovery.jsonl").exists()


def test_m3_is_fresh_run_and_catches_marked_text_only(tmp_path):
    source, F = faulted(tmp_path, "FD2xA3", task="T01")
    # The spoofed post bypasses the verifier, which checks agents' actions only.
    m3 = recover("M3", source, F, llm=llm(), tasks_root=TASKS)
    events = run_events(m3)
    assert [e for e in events if e["type"] == "verify_call"]
    assert json.loads((m3 / "manifest.json").read_text())["mode"] == "M3"

    leaky, F2 = faulted(tmp_path, "FA1xA1")
    result = recover("M3", leaky, F2, llm=llm(), tasks_root=TASKS)
    assert not oracle(result)["pass"]


def test_m4_not_built(tmp_path):
    source, F = faulted(tmp_path, "FA1xA1")
    with pytest.raises(NotImplementedError):
        recover("M4", source, F, llm=llm(), tasks_root=TASKS)


def test_metrics_from_logs(tmp_path):
    clean = run_task(TASKS / "T02", tmp_path, llm())
    source, F = faulted(tmp_path, "FA1xA1")
    m2 = recover("M2", source, F, llm=llm(), tasks_root=TASKS)
    df = compute([clean, source, m2]).set_index("mode")
    assert df.loc["M2", "recomputed_stages"] == 5
    assert df.loc["M2", "recovery_llm_calls"] > 0
    assert bool(df.loc["M2", "pass"]) is True
    row = df[df["cell"] == "FA1xA1"].loc["M0"]
    assert bool(row["dependent"]) is True and row["affected_static"] >= 2


def test_metrics_count_tainted_posts_left_live_and_wrong_sends(tmp_path):
    clean = run_task(TASKS / "T02", tmp_path, llm())
    source, F = faulted(tmp_path, "FA1xA1")
    m1 = recover("M1", source, F, llm=llm(), tasks_root=TASKS)
    m2 = recover("M2", source, F, llm=llm(), tasks_root=TASKS)
    df = compute([clean, source, m1, m2]).set_index("run_id")
    faulted_row = df.loc[source.name]
    assert faulted_row["tainted_live_posts"] >= 2
    # M1 keeps the board, so every tainted post stays live. M2 tombstones them all.
    assert df.loc[m1.name, "tainted_live_posts"] == faulted_row["tainted_live_posts"]
    assert df.loc[m2.name, "tainted_live_posts"] == 0
    assert df.loc[clean.name, "tainted_live_posts"] == 0
    assert df.loc[clean.name, "wrong_sends"] == 0
    # The outbox survives every recovery, so a wrong send stays counted.
    assert df.loc[m2.name, "wrong_sends"] >= faulted_row["wrong_sends"]


@pytest.mark.parametrize("name,task,valid", [
    ("FA1xA1", "T02", 1),   # only A2 never reads the swapped diagnosis
    ("FD2xA3", "T01", 3),   # the spoofed post does not taint the real A3
    ("FA3xA2", "T02", 1),   # a missing invocation taints its agent and every agent after it
    ("FA2xseed", "T02", 2),  # the seeded stale post does not taint A2
])
def test_wasted_work_counts_reruns_of_valid_agents(tmp_path, name, task, valid):
    source, F = faulted(tmp_path, name, task=task)
    m2 = recover("M2", source, F, llm=llm(), tasks_root=TASKS)
    df = compute([source, m2]).set_index("run_id")
    row = df.loc[m2.name]
    assert row["valid_agents"] == valid == df.loc[source.name, "valid_agents"]
    assert row["retained_valid"] == 0  # M2 reruns all five agents
    assert 0 < row["wasted_calls"] < row["recovery_llm_calls"]
    assert pd.isna(df.loc[source.name, "wasted_calls"])
