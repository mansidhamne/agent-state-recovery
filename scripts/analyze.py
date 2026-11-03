"""Build Phase 1 tables from run logs (doc section 18). Figures are not built yet."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mccr.metrics import compute  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=Path, default=ROOT / "runs")
    parser.add_argument("--out", type=Path, default=ROOT / "results")
    parser.add_argument("--include-dev", action="store_true")
    args = parser.parse_args()

    run_dirs = sorted(p.parent for p in args.runs.glob("*/oracle.json"))
    df = compute(run_dirs)
    if df.empty:
        print("no finished runs")
        return 1
    if not args.include_dev:
        df = df[df["split"] == "eval"]
    # Stress cells are a separate experiment (doc section 7.4); never pool them with the matrix.
    stress = yaml.safe_load((ROOT / "config/phase1.yaml").read_text())["stress_cells"]
    df = df.assign(fault_set=df["cell"].isin(stress).map({True: "stress", False: "base"}))
    args.out.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out / "runs.csv", index=False)

    faulted = df[df["cell"] != "clean"]
    tables = {
        "clean_success": df[(df["cell"] == "clean") & (df["mode"] == "M0")]
        .groupby("task_id")[["pass", "score"]].mean(),
        # Clean runs in every mode, to see what a mode costs or breaks when nothing is wrong.
        "clean_by_mode": df[df["cell"] == "clean"].groupby("mode").agg(
            runs=("pass", "size"), passed=("pass", "mean"), score=("score", "mean"),
            llm_calls=("llm_calls", "mean"), verify_calls=("verify_calls", "mean"),
            cost_usd=("cost_usd", "mean")),
        "propagation": faulted[faulted["mode"] == "M0"]
        .groupby(["fault_set", "fault_class", "cell"])[["dependent", "affected_static", "pass"]].mean(),
        "unsafe_ops": faulted[faulted["fault_class"] == "adversarial"]
        .groupby(["cell", "mode", "policy_mode"])[
            ["malicious_text_present", "forbidden_attempted", "forbidden_applied",
             "model_declined", "canary_sent"]].mean(),
        "recovery_by_mode": faulted[faulted["policy_mode"] == "observe"].groupby(
            ["fault_set", "fault_class", "mode"]).agg(
            runs=("pass", "size"), passed=("pass", "mean"),
            correct_ignoring_irreversible=("pass_ignoring_irreversible", "mean"),
            recomputed_stages=("recomputed_stages", "mean"),
            llm_calls=("llm_calls", "mean"), verify_calls=("verify_calls", "mean"),
            cost_usd=("cost_usd", "mean"),
            irreversible=("irreversible", "mean"),
            # pass does not see these two: a wrong order already sent, and tainted posts left live.
            wrong_sends=("wrong_sends", "mean"),
            runs_with_wrong_send=("wrong_sends", lambda s: (s > 0).mean()),
            duplicate_sends=("duplicate_sends", "mean"),
            valid_agents=("valid_agents", "mean"), retained_valid=("retained_valid", "mean"),
            wasted_calls=("wasted_calls", "mean"), wasted_tokens=("wasted_tokens", "mean"),
            tainted_live_posts=("tainted_live_posts", "mean"),
            recovery_wall_ms=("recovery_wall_ms", "mean")),
        "run_status": df.groupby(["mode", "status"]).size().to_frame("runs"),
    }
    for name, table in tables.items():
        table.to_csv(args.out / f"{name}.csv")
        print(f"\n== {name} ==\n{table.round(3).to_string()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
