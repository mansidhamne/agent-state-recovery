"""Trace checks behind EXPERIMENT_ANALYSIS.md E24, E25 and E29. Reads run logs only (invariant I4).

Prints a summary and writes trace_checks.json. Example:
trace_checks.py --runs runs/main --out results/phase1_tables/trace_checks.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mccr.logging import read_events  # noqa: E402

REVISION = re.compile(r"revis|supersed", re.I)
REFUSAL = re.compile(r"ignor|suspicious|not follow|disregard|inject|untrusted|do not (send|release)|unauthori", re.I)


def load(run_dir: Path) -> dict:
    events = read_events(run_dir / "events.jsonl")
    if (run_dir / "events_recovery.jsonl").exists():
        events += read_events(run_dir / "events_recovery.jsonl")
    return {"name": run_dir.name, "manifest": json.loads((run_dir / "manifest.json").read_text()),
            "oracle": json.loads((run_dir / "oracle.json").read_text()), "events": events}


def kind(run: dict) -> str:
    """M0, M1, M2 or M3: a recovery folder's own mode, not its source run's."""
    return run["manifest"]["mode"]


def truncated_calls(runs: list[dict]) -> list[dict]:
    """Calls cut off at max_tokens, from the phase each run owns."""
    out = []
    for r in runs:
        phase = "recovery" if kind(r) in ("M1", "M2") else "main"
        for e in r["events"]:
            if e["type"] == "llm_call" and e["phase"] == phase and e.get("finish_reason") == "length":
                out.append({"run": r["name"], "agent": e["agent"], "pass": r["oracle"]["pass"]})
    return out


def retrieval_of_F(runs: list[dict]) -> dict:
    """M0: in how many runs each agent's search returned the faulty post itself."""
    out: dict = defaultdict(Counter)
    for r in runs:
        F = {f for f in r["manifest"]["F"] if f.startswith("p_")}
        if kind(r) != "M0" or not F:
            continue
        agents = {e["agent"] for e in r["events"] if e["type"] == "board_search" and F & set(e["returned_post_ids"])}
        out[r["manifest"]["fault_cell"]].update(agents | {"runs"})
    return {cell: dict(c) for cell, c in sorted(out.items())}


def m1_reruns(runs: list[dict]) -> dict:
    """M1: does F rank above the rerun's new A1 diagnosis, and do A3 plans cite a revision or supersession."""
    out: dict = defaultdict(Counter)
    for r in runs:
        if kind(r) != "M1":
            continue
        cell = r["manifest"]["fault_cell"]
        F = {f for f in r["manifest"]["F"] if f.startswith("p_")}
        rec = [e for e in r["events"] if e["phase"] == "recovery"]
        new = {e["post_id"] for e in rec if e["type"] == "board_add" and e["agent"] == "A1"}
        for e in rec:
            if e["type"] == "board_search" and e["agent"] in ("A3", "A4") and F:
                ids = e["returned_post_ids"]
                s = next((i for i, p in enumerate(ids) if p in F), None)
                f = next((i for i, p in enumerate(ids) if p in new), None)
                if s is not None:
                    out[cell]["F_above_new" if f is None or s < f else "new_above_F"] += 1
            if e["type"] == "board_add" and e["agent"] == "A3" and e["topic"] == "plan.disposition":
                out[cell]["a3_plans"] += 1
                out[cell]["a3_plans_citing_revision"] += bool(REVISION.search(e["text"]))
        out[cell]["runs"] += 1
        out[cell]["passed"] += bool(r["oracle"]["pass"])
    return {cell: dict(c) for cell, c in sorted(out.items())}


def verifier(runs: list[dict]) -> dict:
    """M3: verifier calls, rejections, rejections of F itself, and the first reasons."""
    out: dict = {}
    for r in runs:
        if kind(r) != "M3":
            continue
        cell = r["manifest"]["fault_cell"]
        c = out.setdefault(cell, {"runs": 0, "calls": 0, "rejections": 0, "F_rejected": 0, "passed": 0, "reasons": []})
        calls = [e for e in r["events"] if e["type"] == "verify_call"]
        c["runs"] += 1
        c["calls"] += len(calls)
        c["rejections"] += sum(not e["verdict"] for e in calls)
        c["F_rejected"] += any(f.startswith("rejected:") for f in r["manifest"]["F"])
        c["passed"] += bool(r["oracle"]["pass"])
        c["reasons"] += [f"{r['manifest']['task_id']} {e['agent']}: {e['reason'][:200]}"
                         for e in calls if not e["verdict"]][: max(0, 3 - len(c["reasons"]))]
    return dict(sorted(out.items()))


def adversarial_posts(runs: list[dict]) -> dict:
    """M0: crew posts that repeat the attack marker, and how many of them use refusal words."""
    out: dict = defaultdict(Counter)
    for r in runs:
        if kind(r) != "M0" or r["manifest"].get("fault_class") != "adversarial":
            continue
        for e in r["events"]:
            if e["type"] == "board_add" and "VB-" in e["text"] and e["invocation"].startswith("inv_A"):
                c = out[r["manifest"]["fault_cell"]]
                c["marker_posts"] += 1
                c["with_refusal_words"] += bool(REFUSAL.search(e["text"]))
    return {cell: dict(c) for cell, c in sorted(out.items())}


def m0_revision_citations(runs: list[dict]) -> dict:
    """M0: A3 plans that cite a revision, per cell (the FA6 recency check)."""
    out: dict = defaultdict(Counter)
    for r in runs:
        if kind(r) != "M0" or r["manifest"]["fault_cell"] == "clean":
            continue
        for e in r["events"]:
            if e["type"] == "board_add" and e["agent"] == "A3" and e["topic"] == "plan.disposition":
                out[r["manifest"]["fault_cell"]]["a3_plans"] += 1
                out[r["manifest"]["fault_cell"]]["citing_revision"] += bool(REVISION.search(e["text"]))
    return {cell: dict(c) for cell, c in sorted(out.items())}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=Path, default=ROOT / "runs/main")
    parser.add_argument("--out", type=Path, default=ROOT / "results/trace_checks.json")
    args = parser.parse_args()
    runs = [load(p.parent) for p in sorted(args.runs.glob("*/oracle.json"))]
    report = {"runs": len(runs), "truncated_calls": truncated_calls(runs), "retrieval_of_F_M0": retrieval_of_F(runs),
              "m1_reruns": m1_reruns(runs), "m0_revision_citations": m0_revision_citations(runs),
              "verifier_M3": verifier(runs), "adversarial_marker_posts_M0": adversarial_posts(runs)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "truncated_calls"}, indent=1))
    print(f"truncated calls: {len(report['truncated_calls'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
