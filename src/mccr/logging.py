"""Append-only JSONL event log (doc section 9.3, invariant I4)."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from mccr.schema import SCHEMA_VERSION, AgentCtx

_ENVELOPE = {"schema", "event_id", "run_id", "ts", "phase", "agent", "invocation", "step", "type"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class EventLog:
    def __init__(self, path: Path, run_id: str, phase: str = "main"):
        self.path = Path(path)
        self.run_id = run_id
        self.phase = phase
        self.events: list[dict] = read_events(self.path) if self.path.exists() else []
        self.overhead_ns = 0  # time spent logging, for the tracking overhead metric
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, type: str, ctx: AgentCtx | None = None, **fields) -> dict:
        start = time.perf_counter_ns()
        reserved = _ENVELOPE & fields.keys()
        if reserved:
            raise ValueError(f"reserved event fields: {sorted(reserved)}")
        event = {
            "schema": SCHEMA_VERSION,
            # Prefixed by phase: main and recovery logs are separate files with separate counters.
            "event_id": f"{self.phase[0]}_{len(self.events) + 1:06d}",
            "run_id": self.run_id,
            "ts": {"mono_ns": time.monotonic_ns(), "wall": now_iso()},
            "phase": self.phase,
            "agent": ctx.agent if ctx else None,
            "invocation": ctx.invocation if ctx else None,
            "step": ctx.step if ctx else None,
            "type": type,
            **fields,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
        self.events.append(event)
        self.overhead_ns += time.perf_counter_ns() - start
        return event


def read_events(path: Path) -> list[dict]:
    """Load a log, refusing mixed schema versions (invariant I7)."""
    with Path(path).open(encoding="utf-8") as f:
        events = [json.loads(line) for line in f if line.strip()]
    versions = {e["schema"] for e in events}
    if versions - {SCHEMA_VERSION}:
        raise ValueError(f"{path}: schema versions {sorted(versions)}, expected {SCHEMA_VERSION}")
    return events
