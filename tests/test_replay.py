from mccr.board import Board
from mccr.logging import read_events
from mccr.schema import AgentCtx
from mccr.world import replay_tree_hash


def test_events_alone_reproduce_board_and_world(world, board, log, make_runner):
    tools = make_runner()
    ref = world.snapshot()
    a1, a4, a5 = (AgentCtx(r, f"inv_{r}_0", 0) for r in ("A1", "A4", "A5"))

    tools.run("A1", "read_file", {"path": "inputs/fim/fim.md"}, ctx=a1)
    dead = tools.run("A1", "board_add", {"topic": "diagnosis.cause", "text": "BLEED-PRV-1"}, ctx=a1)
    tools.run("A1", "board_add", {"topic": "diagnosis.cause", "text": "corrected"}, ctx=a1)
    tools.run("A4", "board_search", {"query": "diagnosis"}, ctx=a4)
    first = world.write("outputs/work_order.json", "v1", ctx=a4)
    tools.run("A4", "write_file", {"path": "outputs/logbook_entry.md", "content": "N8F01"}, ctx=a4)
    tools.run("A5", "write_file", {"path": "inputs/mel/mel.json", "content": "tampered"}, ctx=a5)
    tools.run("A5", "notify_vendor", {"message": "order"}, ctx=a5)
    board.tombstone({dead}, reason="faulty")
    world.undo_writes([first["event_id"]])

    events = read_events(log.path)
    assert Board.from_events(events).dump() == board.dump()
    assert replay_tree_hash(events) == world.tree_hash()
    assert world.tree_hash() != ref.tree_hash


def test_replay_follows_restore(world, log):
    ref = world.snapshot()
    world.write("outputs/a.json", "1")
    world.restore(ref)
    world.write("outputs/b.json", "2")
    assert replay_tree_hash(read_events(log.path)) == world.tree_hash()
