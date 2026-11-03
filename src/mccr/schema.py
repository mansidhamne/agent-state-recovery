"""Shared record types and the log schema version (doc section 9.3)."""
from __future__ import annotations

from dataclasses import dataclass, field

SCHEMA_VERSION = 1


@dataclass
class AgentCtx:
    """Who is acting. Set by the harness, never by the agent."""

    agent: str | None = None
    invocation: str | None = None
    step: int | None = None
    # Set only by the injector; the board records them without interpreting them.
    injected: bool = False
    spoofed_writer: bool = False
    ts_override: str | None = None


@dataclass
class Post:
    post_id: str
    topic: str
    text: str
    writer: str | None
    invocation: str | None
    step: int | None
    ts: str
    parents_run: list[str] = field(default_factory=list)
    parents_window: list[str] = field(default_factory=list)
    status: str = "live"
    injected: bool = False
