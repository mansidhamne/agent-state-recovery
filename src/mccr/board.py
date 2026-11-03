"""Shared board with system-recorded provenance (doc sections 9.3, 9.5)."""
from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime

from rank_bm25 import BM25Okapi

from mccr.logging import EventLog, now_iso
from mccr.schema import AgentCtx, Post

_TOKEN = re.compile(r"[a-z0-9]+")
_WRITE_EVENTS = ("board_add", "file_write", "external_send")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _read_refs(event: dict) -> list[str]:
    if event["type"] == "board_search":
        return list(event["returned_post_ids"])
    if event["type"] == "file_read" and event["acl"] == "allowed" and event["content_hash"]:
        return [f"file:{event['path']}@{event['content_hash'][:4]}"]
    return []


class Board:
    def __init__(self, log: EventLog | None):
        self.log = log
        self._posts: dict[str, Post] = {}

    def add(self, topic: str, text: str, *, ctx: AgentCtx) -> str:
        post_id = f"p_{len(self._posts) + 1:06d}"
        parents_run, parents_window = self._parents(ctx.invocation)
        ts = ctx.ts_override or now_iso()
        self._posts[post_id] = Post(post_id, topic, text, ctx.agent, ctx.invocation, ctx.step, ts,
                                    parents_run, parents_window, "live", ctx.injected)
        self.log.emit("board_add", ctx, post_id=post_id, topic=topic, text=text, post_ts=ts,
                      parents_run=parents_run, parents_window=parents_window,
                      injected=ctx.injected, spoofed_writer=ctx.spoofed_writer)
        return post_id

    def search(self, query: str, k: int, *, ctx: AgentCtx) -> list[Post]:
        ranked = self._rank(query)[:k]
        self.log.emit("board_search", ctx, query=query, k=k,
                      returned_post_ids=[p.post_id for _, p in ranked],
                      scores=[score for score, _ in ranked])
        return [replace(p) for _, p in ranked]

    def tombstone(self, post_ids: set[str], *, reason: str) -> None:
        for post_id in post_ids:
            self._posts[post_id].status = "tombstoned"
        self.log.emit("board_tombstone", post_ids=sorted(post_ids), reason=reason)

    def dump(self) -> list[Post]:
        return [replace(p) for p in self._posts.values()]

    @classmethod
    def from_events(cls, events: list[dict]) -> "Board":
        """Rebuild a read-only board from the event log alone."""
        board = cls(log=None)
        for e in events:
            if e["type"] == "board_add":
                board._posts[e["post_id"]] = Post(
                    e["post_id"], e["topic"], e["text"], e["agent"], e["invocation"], e["step"],
                    e["post_ts"], e["parents_run"], e["parents_window"], "live", e["injected"])
            elif e["type"] == "board_tombstone":
                for post_id in e["post_ids"]:
                    board._posts[post_id].status = "tombstoned"
        return board

    def _rank(self, query: str) -> list[tuple[float, Post]]:
        live = [p for p in self._posts.values() if p.status == "live"]
        if not live:
            return []
        bm25 = BM25Okapi([tokenize(f"{p.topic} {p.text}") for p in live])
        scores = [float(s) for s in bm25.get_scores(tokenize(query))]
        # Ties: newer timestamp, then post_id, so results are deterministic.
        return sorted(zip(scores, live),
                      key=lambda sp: (-sp[0], -datetime.fromisoformat(sp[1].ts).timestamp(),
                                      sp[1].post_id))

    def _parents(self, invocation: str | None) -> tuple[list[str], list[str]]:
        parents_run: list[str] = []
        parents_window: list[str] = []
        for event in self.log.events:
            if event["invocation"] != invocation:
                continue
            if event["type"] in _WRITE_EVENTS:
                parents_window = []
            for ref in _read_refs(event):
                if ref not in parents_run:
                    parents_run.append(ref)
                if ref not in parents_window:
                    parents_window.append(ref)
        return parents_run, parents_window
