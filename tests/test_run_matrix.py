import json

import pytest

from run_matrix import already_done


def make_run(path, last_event, oracle=True, log="events.jsonl"):
    path.mkdir()
    events = [{"type": "run_start"}, {"type": last_event}]
    (path / log).write_text("\n".join(json.dumps(e) for e in events) + "\n")
    if oracle:
        (path / "oracle.json").write_text("{}")


def test_missing_run_is_not_done(tmp_path):
    assert already_done(tmp_path / "T01__clean__M0__observe__r0") is False


def test_finished_run_is_done(tmp_path):
    run = tmp_path / "T01__clean__M0__observe__r0"
    make_run(run, "run_end")
    assert already_done(run) is True


@pytest.mark.parametrize("last_event,oracle", [("invocation_end", True), ("run_end", False)])
def test_interrupted_run_is_an_error(tmp_path, last_event, oracle):
    run = tmp_path / "T01__clean__M0__observe__r0"
    make_run(run, last_event, oracle)
    with pytest.raises(RuntimeError):
        already_done(run)


def test_folder_without_log_is_an_error(tmp_path):
    run = tmp_path / "T01__clean__M0__observe__r0"
    run.mkdir()
    with pytest.raises(RuntimeError):
        already_done(run)


def test_recovery_checks_the_recovery_log(tmp_path):
    run = tmp_path / "T01__FA1xA1__M0__observe__r0__recovered_M2"
    make_run(run, "invocation_end", log="events_recovery.jsonl")
    (run / "events.jsonl").write_text(json.dumps({"type": "run_end"}) + "\n")
    with pytest.raises(RuntimeError):
        already_done(run)
