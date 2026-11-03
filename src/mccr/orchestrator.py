"""Run lifecycle (doc section 9.2)."""
from __future__ import annotations

import json
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from mccr.agents import ROLES, prompt_hashes, run_agent
from mccr.board import Board
from mccr.faults import FaultCell, Injector
from mccr.llm import LLMClient
from mccr.logging import EventLog
from mccr.oracle import grade
from mccr.schema import SCHEMA_VERSION, AgentCtx
from mccr.tools import Policy, ToolRunner, VerifiedToolRunner
from mccr.world import World

DEFAULT_STEP_CAP = 12
DEFAULT_K = 4
WORLD_DIRS = ("outputs", "outbox")


@dataclass(frozen=True)
class RunConfig:
    model: str = "scripted"
    temperature: float = 0.0
    max_tokens: int = 1024
    step_cap: int = DEFAULT_STEP_CAP
    bm25_k: int = DEFAULT_K
    policy_mode: str = "observe"


def split_of(task_id: str) -> str:
    return "dev" if task_id in ("T01", "T02") else "eval"


def _code_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                              cwd=Path(__file__).parent, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def write_manifest(run_dir: Path, **fields) -> dict:
    path = run_dir / "manifest.json"
    manifest = json.loads(path.read_text()) if path.exists() else {}
    manifest.update(fields)
    path.write_text(json.dumps(manifest, indent=2))
    return manifest


def run_crew(task_spec: str, llm: LLMClient, tools: ToolRunner, config: RunConfig, *,
             attempt: int = 0, seed: int | None = None, roles=ROLES) -> dict:
    statuses = {}
    for role in roles:
        ctx = AgentCtx(role, f"inv_{role}_{attempt}", 0)
        statuses[role] = run_agent(role, task_spec, llm, tools, step_cap=config.step_cap,
                                   ctx=ctx, seed=seed).status
    return statuses


def write_oracle(run_dir: Path, task_dir: Path) -> dict:
    spec = json.loads((Path(task_dir) / "oracle.json").read_text())
    result = grade(run_dir, spec).to_dict()
    (run_dir / "oracle.json").write_text(json.dumps(result, indent=2))
    return result


def run_task(task_dir: Path, runs_root: Path, llm: LLMClient, *, mode: str = "M0",
             cell: FaultCell | None = None, rep: int = 0, config: RunConfig = RunConfig(),
             board_wrapper=None, run_suffix: str = "") -> Path:
    """Prepare and run one crew, then grade it. Failed runs keep their status (I6)."""
    task_dir = Path(task_dir)
    task_id = task_dir.name
    cell_name = cell.name if cell else "clean"
    run_id = f"{task_id}__{cell_name}__{mode}__{config.policy_mode}__r{rep}{run_suffix}"
    run_dir = Path(runs_root) / run_id
    if run_dir.exists():
        raise FileExistsError(f"{run_dir} exists; runs are never overwritten (I6)")
    run_dir.mkdir(parents=True)

    log = EventLog(run_dir / "events.jsonl", run_id)
    world_root = run_dir / "world"
    shutil.copytree(task_dir / "world", world_root)
    for name in WORLD_DIRS:
        (world_root / name).mkdir(exist_ok=True)
    world = World(world_root, log, store=run_dir / "world_store")
    board = Board(log)
    start = time.perf_counter()

    write_manifest(run_dir, run_id=run_id, task_id=task_id, split=split_of(task_id), mode=mode,
                   fault_cell=cell_name, fault_class=cell.fault_class if cell else None, F=[], rep=rep,
                   seed=rep, model=config.model, temperature=config.temperature,
                   max_tokens=config.max_tokens, step_cap=config.step_cap, bm25_k=config.bm25_k,
                   policy_mode=config.policy_mode, prompt_hashes=prompt_hashes(),
                   code_commit=_code_commit(), schema_version=SCHEMA_VERSION,
                   started_at=datetime.now(timezone.utc).isoformat(), host=socket.gethostname())

    injector = Injector(task_dir, log)
    active_board, active_llm = board, llm
    if cell:
        injector.prepare_world(cell, world, board)
        active_board = injector.wrap_board(board, cell)
        active_llm = injector.wrap_llm(llm, cell)
    if board_wrapper:
        active_board = board_wrapper(active_board)
    world.snapshot()

    policy = Policy(config.policy_mode)
    task_spec = (task_dir / "task_spec.md").read_text()
    if mode == "M3":
        tools = VerifiedToolRunner(world, active_board, policy, log, llm=llm, task_spec=task_spec)
    else:
        tools = ToolRunner(world, active_board, policy, log)
    tools.default_k = config.bm25_k
    if cell:
        tools = injector.wrap_tools(tools, cell)  # in front of the verifier, so M3 sees FA1

    statuses = run_crew(task_spec, active_llm, tools, config, seed=rep)
    wall_ms = (time.perf_counter() - start) * 1000
    status = "ok" if all(s == "finished" for s in statuses.values()) else "degraded"
    log.emit("run_end", status=status, wall_ms=wall_ms, statuses=statuses)
    write_manifest(run_dir, F=injector.F, status=status, log_overhead_ns=log.overhead_ns)
    write_oracle(run_dir, task_dir)
    return run_dir
