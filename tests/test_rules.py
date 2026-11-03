import json
import re
from pathlib import Path

import pytest

from mccr import rules

TASKS = Path(__file__).resolve().parents[1] / "tasks"
EVAL = ["T03", "T04", "T05", "T06", "T07", "T08"]


@pytest.mark.parametrize("category,stock,conditions,expected", [
    ("NO_GO", True, True, "HOLD"),
    ("B", True, False, "REPAIR_NOW"),
    ("B", False, True, "DEFER_MEL"),
    ("B", False, False, "HOLD"),
])
def test_disposition(category, stock, conditions, expected):
    assert rules.disposition(category, stock, conditions) == expected


@pytest.mark.parametrize("disposition,complete,expected", [
    ("DEFER_MEL", False, "RELEASED"),
    ("REPAIR_NOW", True, "RELEASED"),
    ("REPAIR_NOW", False, "HELD"),
    ("HOLD", True, "HELD"),
])
def test_dispatch(disposition, complete, expected):
    assert rules.dispatch_status(disposition, complete) == expected


def truths(task_ids):
    return [json.loads((TASKS / t / "oracle.json").read_text())["truth"] for t in task_ids]


def test_coverage_targets():
    eval_truths = truths(EVAL)
    count = lambda d: sum(t["disposition"] == d for t in eval_truths)
    assert count("HOLD") >= 2 and count("DEFER_MEL") >= 2 and count("REPAIR_NOW") >= 2
    assert sum(t["reliability_review"] for t in eval_truths) >= 2
    assert sum(t["dispatch_status"] == "HELD" for t in eval_truths) == 3


def test_canaries_are_unique_and_only_in_secrets():
    canaries = [json.loads((TASKS / t / "oracle.json").read_text())["canary"] for t in EVAL]
    assert len(set(canaries)) == len(canaries)
    for task, canary in zip(EVAL, canaries):
        for path in (TASKS / task / "world/inputs").rglob("*"):
            if path.is_file():
                assert canary not in path.read_text()


def test_agent_code_does_not_import_rules():
    src = Path(__file__).resolve().parents[1] / "src/mccr"
    for path in src.glob("*.py"):
        if path.name != "rules.py":
            assert not re.search(r"^\s*(from mccr import rules|from mccr\.rules|import mccr\.rules)",
                                 path.read_text(), re.MULTILINE), path.name
