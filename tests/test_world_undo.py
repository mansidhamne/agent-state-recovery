import pytest

from mccr.logging import EventLog
from mccr.world import PathEscape, World


def test_undo_n_writes_restores_tree_hash(world):
    before = world.tree_hash()
    ids = [world.write("outputs/a.json", "1")["event_id"],
           world.write("outputs/a.json", "2")["event_id"],
           world.write("outputs/b.json", "3")["event_id"],
           world.write("inputs/mel/mel.json", "tampered")["event_id"]]
    assert world.tree_hash() != before
    assert world.undo_writes(ids) == []
    assert world.tree_hash() == before


def test_undo_order_independent_of_argument_order(world):
    before = world.tree_hash()
    ids = [world.write("outputs/a.json", str(i))["event_id"] for i in range(3)]
    assert world.undo_writes(list(reversed(ids))) == []
    assert world.tree_hash() == before


def test_partial_undo_keeps_other_files(world):
    keep = world.write("outputs/keep.json", "k")
    drop = world.write("outputs/drop.json", "d")
    assert world.undo_writes([drop["event_id"]]) == []
    assert world.read("outputs/keep.json") == "k"
    assert not (world.root / "outputs/drop.json").exists()
    assert keep["post_hash"]


def test_undo_does_not_clobber_later_write(world):
    first = world.write("outputs/a.json", "tainted")
    world.write("outputs/a.json", "valid later write")
    assert world.undo_writes([first["event_id"]]) == ["conflict:outputs/a.json"]
    assert world.read("outputs/a.json") == "valid later write"


def test_external_send_is_irreversible_leftover(world):
    sent = world.send_external("hello", contains_canary=False)
    assert world.undo_writes([sent["event_id"]]) == [f"notify_vendor:{sent['msg_id']}"]
    assert "hello" in world.read("outbox/vendor_messages.jsonl")


def test_unknown_event_reported(world):
    assert world.undo_writes(["m_999999"]) == ["unknown:m_999999"]


def test_snapshot_restore_round_trip(world):
    ref = world.snapshot()
    world.write("outputs/a.json", "1")
    world.write("inputs/mel/mel.json", "tampered")
    (world.root / "inputs/fim/fim.md").unlink()
    assert world.tree_hash() != ref.tree_hash
    world.restore(ref)
    assert world.tree_hash() == ref.tree_hash


def test_restore_does_not_unsend_messages(world):
    ref = world.snapshot()
    world.send_external("gone", contains_canary=False)
    world.restore(ref)
    assert "gone" in world.read("outbox/vendor_messages.jsonl")
    assert world.tree_hash() == ref.tree_hash


def test_second_snapshot_gets_new_id(world):
    assert world.snapshot().snapshot_id != world.snapshot().snapshot_id


def test_undo_from_logged_events_in_new_process(tmp_path, world, log):
    before = world.tree_hash()
    event = world.write("outputs/a.json", "1")
    recovery_log = EventLog(tmp_path / "events_recovery.jsonl", "r1", "recovery")
    fresh = World(world.root, recovery_log, store=world.store)
    fresh.index_writes(log.events)
    assert fresh.undo_writes([event["event_id"]]) == []
    assert fresh.tree_hash() == before


@pytest.mark.parametrize("path", ["../evil", "outputs/../../evil", "/etc/passwd"])
def test_path_escape_rejected(world, path):
    with pytest.raises(PathEscape):
        world.write(path, "x")


def test_symlink_escape_rejected(tmp_path, world):
    (world.root / "link").symlink_to(tmp_path)
    with pytest.raises(PathEscape):
        world.read("link/events.jsonl")
