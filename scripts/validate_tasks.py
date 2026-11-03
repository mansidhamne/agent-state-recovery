"""Dependence validation in scripted mode (doc section 7.3). Exits non-zero on failure."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mccr.faults import CELLS  # noqa: E402
from mccr.llm import ScriptedClient  # noqa: E402
from mccr.orchestrator import run_task  # noqa: E402
from mccr.scripted_crew import SCRIPT  # noqa: E402

TASKS = ROOT / "tasks"
WITHHELD_TOPICS = ("diagnosis.cause", "parts.availability", "plan.disposition")


class WithholdBoard:
    """Drops posts on one topic, as if the writer never posted."""

    def __init__(self, board, topic: str):
        self._board, self._topic = board, topic

    def __getattr__(self, name):
        return getattr(self._board, name)

    def add(self, topic, text, *, ctx):
        return "withheld" if topic == self._topic else self._board.add(topic, text, ctx=ctx)


def exempt(truth: dict, topic_or_cell: str) -> str | None:
    """Combinations where the procedure itself gives no dependence (doc section 17)."""
    no_go = truth["disposition"] == "HOLD"
    if no_go and topic_or_cell in ("parts.availability", "FA2xseed"):
        return "NO_GO decides HOLD before stock is consulted"
    if no_go and topic_or_cell == "FA3xA2" and not truth["reliability_review"]:
        return "NO_GO, and no recurrence to lose"
    if topic_or_cell == "FA6xA1":
        return "the scripted crew takes the top-ranked post and does not model recency; FA6 tests the real model"
    return None


def validate(task_dir: Path, runs_root: Path) -> list[str]:
    failures: list[str] = []
    truth = json.loads((task_dir / "oracle.json").read_text())["truth"]

    def run(**kwargs) -> dict:
        run_dir = run_task(task_dir, runs_root, ScriptedClient(SCRIPT), **kwargs)
        return json.loads((run_dir / "oracle.json").read_text())

    if not run()["pass"]:
        failures.append("clean run does not pass the oracle")
    for topic in WITHHELD_TOPICS:
        result = run(board_wrapper=lambda b, t=topic: WithholdBoard(b, t), run_suffix=f"__no_{topic}")
        if result["pass"] and not exempt(truth, topic):
            failures.append(f"withholding {topic} does not fail the oracle")
    for cell in CELLS:
        result = run(cell=cell)
        if result["pass"] and not exempt(truth, cell.name):
            failures.append(f"fault {cell.name} does not change the oracle result")
    return failures


def main() -> int:
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        for task_dir in sorted(TASKS.glob("T0*")):
            failures = validate(task_dir, Path(tmp) / task_dir.name)
            print(f"{task_dir.name}: {'OK' if not failures else 'FAIL'}")
            for failure in failures:
                print(f"  {failure}")
            bad += bool(failures)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
