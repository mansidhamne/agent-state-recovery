from mccr.board import Board
from mccr.schema import AgentCtx

CTX = AgentCtx("A1", "inv_A1_0", 1)


def seed(board):
    return [
        board.add("diagnosis.cause", "Component BLEED-PRV-1 failed, ATA 36", ctx=CTX),
        board.add("parts.availability", "PN-36-1187 in stock at station", ctx=CTX),
        board.add("history.recurrence", "two prior defects on this tail", ctx=CTX),
        board.add("plan.logistics", "ship from main warehouse", ctx=CTX),
    ]


def test_add_and_search_ranks_relevant_first(board):
    ids = seed(board)
    assert board.search("bleed diagnosis", 4, ctx=CTX)[0].post_id == ids[0]
    assert board.search("parts stock", 4, ctx=CTX)[0].post_id == ids[1]


def test_k_limits_results(board):
    seed(board)
    assert len(board.search("parts", 2, ctx=CTX)) == 2


def test_search_empty_board(board):
    assert board.search("anything", 4, ctx=CTX) == []


def test_tombstoned_posts_never_returned(board):
    ids = seed(board)
    board.tombstone({ids[0]}, reason="faulty")
    returned = [p.post_id for p in board.search("bleed diagnosis", 4, ctx=CTX)]
    assert ids[0] not in returned
    assert {p.post_id: p.status for p in board.dump()}[ids[0]] == "tombstoned"


def test_ranking_deterministic(board):
    seed(board)
    runs = [[p.post_id for p in board.search("component stock", 4, ctx=CTX)] for _ in range(5)]
    assert all(r == runs[0] for r in runs)


def test_ties_break_to_newer_timestamp(board):
    old = AgentCtx("A2", "seed", 0, ts_override="2020-01-01T00:00:00+00:00")
    stale = board.add("parts", "same words", ctx=old)
    fresh = board.add("parts", "same words", ctx=CTX)
    board.add("other", "unrelated", ctx=CTX)
    returned = [p.post_id for p in board.search("parts", 3, ctx=CTX)]
    assert returned.index(fresh) < returned.index(stale)


def test_term_in_half_of_posts_scores_zero_and_falls_back_to_recency(board):
    # BM25Okapi IDF is 0 for a term in exactly half the documents (doc section 17).
    match = board.add("first", "alpha", ctx=CTX)
    newer = board.add("second", "beta", ctx=CTX)
    results = board.search("first", 1, ctx=CTX)
    assert [p.post_id for p in results] == [newer]
    assert match != newer


def test_search_logs_retrieve_edge(board, log):
    ids = seed(board)
    board.search("bleed", 1, ctx=CTX)
    event = log.events[-1]
    assert event["type"] == "board_search"
    assert event["returned_post_ids"] == [ids[0]]
    assert len(event["scores"]) == 1


def test_writer_comes_from_ctx(board):
    pid = board.add("t", "x", ctx=AgentCtx("A3", "inv_A3_0", 4))
    post = board.dump()[0]
    assert (post.post_id, post.writer, post.invocation, post.step) == (pid, "A3", "inv_A3_0", 4)


def test_returned_posts_are_copies(board):
    seed(board)
    board.dump()[0].status = "tombstoned"
    assert board.dump()[0].status == "live"


def test_parents_run_and_window(board, world, make_runner):
    tools = make_runner()
    a1 = AgentCtx("A1", "inv_A1_0", 0)
    tools.run("A1", "read_file", {"path": "inputs/fault/fault_report.json"}, ctx=a1)
    first = board.add("a", "first", ctx=a1)
    tools.run("A1", "read_file", {"path": "inputs/fim/fim.md"}, ctx=a1)
    board.add("b", "second", ctx=a1)
    board.add("z", "unrelated", ctx=AgentCtx("A2", "inv_A2_0", 0))
    other = AgentCtx("A3", "inv_A3_0", 0)
    tools.run("A3", "board_search", {"query": "first", "k": 1}, ctx=other)
    board.add("c", "third", ctx=other)

    posts = board.dump()
    third = posts[3]
    assert len(posts[0].parents_run) == 1 and posts[0].parents_run[0].startswith("file:inputs/fault/")
    assert len(posts[1].parents_run) == 2
    assert len(posts[1].parents_window) == 1 and posts[1].parents_window[0].startswith("file:inputs/fim/")
    assert third.parents_run == [first]


def test_denied_read_is_not_a_parent(board, make_runner):
    ctx = AgentCtx("A1", "inv_A1_0", 0)
    make_runner().run("A1", "read_file", {"path": "inputs/mel/mel.json"}, ctx=ctx)
    board.add("a", "x", ctx=ctx)
    assert board.dump()[0].parents_run == []


def test_injector_flags_recorded(board, log):
    ctx = AgentCtx("A3", "injected", 0, injected=True, spoofed_writer=True)
    board.add("plan.logistics", "release", ctx=ctx)
    assert board.dump()[0].injected is True
    assert log.events[-1]["spoofed_writer"] is True
    assert Board.from_events(log.events).dump()[0].writer == "A3"
