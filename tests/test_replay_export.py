import json
from pathlib import Path

from export_replay import export_run

from mccr.faults import CELLS_BY_NAME
from mccr.llm import ScriptedClient
from mccr.orchestrator import run_task
from mccr.recovery import recover
from mccr.scripted_crew import SCRIPT

TASKS = Path(__file__).resolve().parents[1] / "tasks"


def test_export_marks_the_fault_its_descendants_and_the_wipe(tmp_path):
    source = run_task(TASKS / "T02", tmp_path, ScriptedClient(SCRIPT), cell=CELLS_BY_NAME["FA1xA1"])
    F = set(json.loads((source / "manifest.json").read_text())["F"])
    m2 = recover("M2", source, F, llm=ScriptedClient(SCRIPT), tasks_root=TASKS)

    faulted = export_run(source)
    posts = [e for e in faulted["events"] if e["type"] == "board_add"]
    assert [p["post_id"] for p in posts if p["f"]] == sorted(F)
    assert any(p["tainted"] and not p["f"] for p in posts)
    assert faulted["events"][-1]["type"] == "run_end" and faulted["events"][-1]["cap"].startswith("Result:")

    wiped = export_run(m2)
    wipe = [e for e in wiped["events"] if e["type"] == "board_tombstone"]
    assert wipe and wipe[0]["phase"] == "recovery" and wipe[0]["big"]
    # Rerun posts are the rerun's own work, never tainted by the faulted run's lineage.
    assert not any(e["tainted"] for e in wiped["events"] if e["type"] == "board_add" and e["phase"] == "recovery")
