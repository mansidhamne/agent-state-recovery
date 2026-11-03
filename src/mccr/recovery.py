"""Recovery baselines (doc section 10). M4 is Phase 2 and is not built yet.

The faulted run stays untouched: each recovery works on a copy in a new run directory.
The injector is off for every rerun. A poisoned input stays unless the mode restores it.
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from mccr.board import Board
from mccr.faults import CELLS_BY_NAME
from mccr.llm import LLMClient
from mccr.logging import EventLog, read_events
from mccr.orchestrator import RunConfig, run_crew, run_task, write_manifest, write_oracle
from mccr.tools import Policy, ToolRunner
from mccr.world import SnapshotRef, World


def _copy_run(faulted_run: Path, mode: str) -> Path:
    target = faulted_run.parent / f"{faulted_run.name}__recovered_{mode}"
    if target.exists():
        raise FileExistsError(f"{target} exists; runs are never overwritten (I6)")
    shutil.copytree(faulted_run, target)
    return target


def _run_start_snapshot(events: list[dict], store: Path) -> SnapshotRef:
    e = next(e for e in events if e["type"] == "world_snapshot")
    return SnapshotRef(e["snapshot_id"], store / "snapshots" / e["snapshot_id"], e["tree_hash"],
                       e["manifest"])


def _replace_faulty_inputs(world: World, task_dir: Path, F: set[str]) -> None:
    for ref in F:
        if ref.startswith("file:"):
            rel = ref.removeprefix("file:").split("@")[0]
            clean = (task_dir / "world" / rel).read_text()
            world.write(rel, clean, flag="fault_cleanup")


def recover(mode: str, faulted_run: Path, F: set[str], *, llm: LLMClient, tasks_root: Path,
            config: RunConfig = RunConfig()) -> Path:
    faulted_run = Path(faulted_run)
    manifest = json.loads((faulted_run / "manifest.json").read_text())
    task_dir = Path(tasks_root) / manifest["task_id"]

    if mode == "M3":
        cell = CELLS_BY_NAME[manifest["fault_cell"]] if manifest["fault_cell"] != "clean" else None
        return run_task(task_dir, faulted_run.parent, llm, mode="M3", cell=cell, rep=manifest["rep"],
                        config=config)
    if mode not in ("M1", "M2"):
        raise NotImplementedError(f"{mode} is not built yet (Phase 2)")

    run_dir = _copy_run(faulted_run, mode)
    events = read_events(run_dir / "events.jsonl")
    log = EventLog(run_dir / "events_recovery.jsonl", f"{run_dir.name}", "recovery")
    store = run_dir / "world_store"
    world = World(run_dir / "world", log, store=store)
    world.index_writes(events)
    board = Board.from_events(events)
    board.log = log
    start = time.perf_counter()

    if mode == "M2":
        board.tombstone({p.post_id for p in board.dump() if p.status == "live"}, reason="M2 wipe")
        world.restore(_run_start_snapshot(events, store))
        _replace_faulty_inputs(world, task_dir, F)

    tools = ToolRunner(world, board, Policy(config.policy_mode), log)
    tools.default_k = config.bm25_k
    task_spec = (task_dir / "task_spec.md").read_text()
    statuses = run_crew(task_spec, llm, tools, config, attempt=1, seed=manifest["rep"])
    wall_ms = (time.perf_counter() - start) * 1000
    status = "ok" if all(s == "finished" for s in statuses.values()) else "degraded"
    log.emit("run_end", status=status, wall_ms=wall_ms, statuses=statuses)
    write_manifest(run_dir, run_id=run_dir.name, mode=mode, status=status,
                   recovered_from=faulted_run.name, recovery_wall_ms=wall_ms)
    write_oracle(run_dir, task_dir)
    return run_dir
