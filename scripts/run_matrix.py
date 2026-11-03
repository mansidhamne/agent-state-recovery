"""Run the Phase 1 matrix (doc section 12.3). Finished runs are skipped, so reruns resume.

Example: run_matrix.py --backend scripted --tasks dev --reps 1 --blocks clean,M0,M2
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mccr.faults import CELLS_BY_NAME  # noqa: E402
from mccr.llm import ScriptedClient, TritonAIClient  # noqa: E402
from mccr.orchestrator import RunConfig, run_task  # noqa: E402
from mccr.recovery import recover  # noqa: E402
from mccr.scripted_crew import SCRIPT  # noqa: E402

TASKS = ROOT / "tasks"


def make_llm(backend: str, model_cfg: dict):
    if backend == "scripted":
        return ScriptedClient(SCRIPT)
    return TritonAIClient(model_cfg["model"], model_cfg["temperature"], model_cfg["max_tokens"],
                          model_cfg["timeout_s"], model_cfg["max_retries"], model_cfg["use_seed"])


def jobs_for(block: str, tasks: list[str], cfg: dict, reps: int) -> list[dict]:
    cells = cfg["cells"]
    grid = [(t, c, r) for t in tasks for c in cells for r in range(reps)]
    if block == "clean":
        total = reps + cfg["noise_floor_reps"]
        return [{"kind": "run", "task": t, "cell": None, "rep": r} for t in tasks for r in range(total)]
    if block == "M0":
        return [{"kind": "run", "task": t, "cell": c, "rep": r} for t, c, r in grid]
    if block in ("M1", "M2"):
        return [{"kind": "recover", "mode": block, "task": t, "cell": c, "rep": r} for t, c, r in grid]
    if block == "M3":
        clean = [{"kind": "m3", "task": t, "cell": None, "rep": r} for t in tasks for r in range(reps)]
        return [{"kind": "m3", "task": t, "cell": c, "rep": r} for t, c, r in grid] + clean
    if block == "enforce":
        return [{"kind": "run", "task": t, "cell": c, "rep": r, "policy": "enforce"}
                for t in tasks for c in cfg["adversarial_cells"] for r in range(reps)]
    raise ValueError(f"unknown block: {block}")


def already_done(run_dir: Path) -> bool:
    """True if the run finished. A folder that did not finish is an error, never a silent skip."""
    if not run_dir.exists():
        return False
    log = run_dir / ("events_recovery.jsonl" if "__recovered_" in run_dir.name else "events.jsonl")
    lines = log.read_text().splitlines() if log.exists() else []
    if lines and json.loads(lines[-1])["type"] == "run_end" and (run_dir / "oracle.json").exists():
        return True
    raise RuntimeError(f"{run_dir.name} exists but did not finish (interrupted run). "
                       f"Move it out of the runs folder, never delete it, then rerun")


def execute(job: dict, runs_root: Path, base: RunConfig, backend: str, model_cfg: dict) -> str:
    cell = CELLS_BY_NAME[job["cell"]] if job["cell"] else None
    cell_name = job["cell"] or "clean"
    policy = job.get("policy", "observe")
    config = RunConfig(base.model, base.temperature, base.max_tokens, base.step_cap, base.bm25_k, policy)
    name = f"{job['task']}__{cell_name}__{'M3' if job['kind'] == 'm3' else 'M0'}__{policy}__r{job['rep']}"
    llm = make_llm(backend, model_cfg)  # one client per job: scripted state is per run
    if job["kind"] == "run":
        if already_done(runs_root / name):
            return f"skip {name}"
        run_task(TASKS / job["task"], runs_root, llm, cell=cell, rep=job["rep"], config=config)
    elif job["kind"] == "m3":
        if already_done(runs_root / name):
            return f"skip {name}"
        run_task(TASKS / job["task"], runs_root, llm, mode="M3", cell=cell, rep=job["rep"], config=config)
    else:
        name = f"{name}__recovered_{job['mode']}"
        if already_done(runs_root / name):
            return f"skip {name}"
        faulted = runs_root / name.split("__recovered_")[0]
        F = set(json.loads((faulted / "manifest.json").read_text())["F"])
        recover(job["mode"], faulted, F, llm=llm, tasks_root=TASKS, config=config)
    return f"done {name}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["scripted", "tritonai"], required=True)
    parser.add_argument("--tasks", choices=["dev", "eval"], default="eval")
    parser.add_argument("--blocks", help="comma separated; default is the priority order in the config")
    parser.add_argument("--reps", type=int)
    parser.add_argument("--cells", help="comma separated cell names, or a list name in the config "
                                        "(cells, stress_cells); default: cells")
    parser.add_argument("--slice", default="0/1", help="i/n: run every n-th job, for two API keys")
    parser.add_argument("--runs", type=Path, default=ROOT / "runs")
    args = parser.parse_args()

    cfg = yaml.safe_load((ROOT / "config/phase1.yaml").read_text())
    if args.cells:
        cfg["cells"] = cfg[args.cells] if args.cells in cfg else args.cells.split(",")
        unknown = [c for c in cfg["cells"] if c not in CELLS_BY_NAME]
        if unknown:
            parser.error(f"unknown cells: {unknown}")
    model_cfg = yaml.safe_load((ROOT / "config/model.yaml").read_text())
    tasks = cfg[f"{args.tasks}_tasks"]
    reps = args.reps or cfg["reps"]
    model = "scripted" if args.backend == "scripted" else model_cfg["model"]
    base = RunConfig(model, model_cfg["temperature"], model_cfg["max_tokens"], cfg["step_cap"], cfg["bm25_k"])
    args.runs.mkdir(parents=True, exist_ok=True)
    index, total = map(int, args.slice.split("/"))

    failed = 0
    # Blocks run in order, because recoveries need the M0 runs to exist.
    for block in (args.blocks.split(",") if args.blocks else cfg["priority"]):
        jobs = jobs_for(block, tasks, cfg, reps)[index::total]
        concurrency = 1 if args.backend == "scripted" else cfg["concurrency"]
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {pool.submit(execute, j, args.runs, base, args.backend, model_cfg): j for j in jobs}
            for future in as_completed(futures):
                try:
                    print(future.result(), flush=True)
                except Exception as e:  # keep going: one failed job must not stop the matrix
                    failed += 1
                    print(f"FAILED {futures[future]}: {type(e).__name__}: {e}", flush=True)
    print(f"failed jobs: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
