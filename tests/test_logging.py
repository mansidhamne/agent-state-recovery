import json

import pytest

from mccr.logging import EventLog, read_events
from mccr.schema import SCHEMA_VERSION, AgentCtx


def test_envelope_fields(log):
    e = log.emit("run_end", AgentCtx("A1", "inv_A1_0", 2), status="ok", wall_ms=5)
    assert e["schema"] == SCHEMA_VERSION
    assert e["run_id"] == "r1"
    assert e["phase"] == "main"
    assert (e["agent"], e["invocation"], e["step"]) == ("A1", "inv_A1_0", 2)
    assert set(e["ts"]) == {"mono_ns", "wall"}


def test_append_only_round_trip_and_resume(tmp_path):
    path = tmp_path / "events.jsonl"
    first = EventLog(path, "r1")
    first.emit("run_end", status="ok")
    resumed = EventLog(path, "r1")
    resumed.emit("run_end", status="ok")
    events = read_events(path)
    assert [e["event_id"] for e in events] == ["m_000001", "m_000002"]


def test_phases_have_distinct_event_ids(tmp_path):
    main = EventLog(tmp_path / "events.jsonl", "r1").emit("run_end")
    recovery = EventLog(tmp_path / "events_recovery.jsonl", "r1", "recovery").emit("run_end")
    assert main["event_id"] != recovery["event_id"]


def test_reserved_field_rejected(log):
    with pytest.raises(ValueError):
        log.emit("run_end", run_id="other")


def test_mixed_schema_refused(tmp_path, log):
    log.emit("run_end")
    bad = dict(log.events[0], schema=SCHEMA_VERSION + 1)
    with log.path.open("a") as f:
        f.write(json.dumps(bad) + "\n")
    with pytest.raises(ValueError):
        read_events(log.path)
