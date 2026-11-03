"""Per-run world directory: snapshots, undo log, tree hash (doc sections 6.2, 6.4).

outbox/ models messages that already left the system. Restores and undo never
touch a sent message, and tree_hash() covers only the restorable world, so it
excludes outbox/.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from mccr.logging import EventLog
from mccr.schema import AgentCtx

OUTBOX = "outbox"
OUTBOX_FILE = "outbox/vendor_messages.jsonl"


class PathEscape(ValueError):
    """The path resolves outside the world directory."""


@dataclass(frozen=True)
class SnapshotRef:
    snapshot_id: str
    path: Path
    tree_hash: str
    manifest: dict


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_manifest(manifest: dict) -> str:
    return sha256(json.dumps(sorted(manifest.items())).encode())


def _in_outbox(rel: str) -> bool:
    return rel == OUTBOX or rel.startswith(OUTBOX + "/")


class World:
    def __init__(self, root: Path, log: EventLog, store: Path | None = None):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.log = log
        self.store = Path(store) if store else self.root.parent / "world_store"
        (self.store / "blobs").mkdir(parents=True, exist_ok=True)
        self._writes: dict[str, dict] = {}
        self.index_writes(log.events)

    def normalize(self, path: str) -> str:
        """Return the world-relative POSIX path, or raise PathEscape."""
        resolved = (self.root / path).resolve()
        if not resolved.is_relative_to(self.root):
            raise PathEscape(path)
        return resolved.relative_to(self.root).as_posix()

    def read(self, path: str) -> str:
        return (self.root / self.normalize(path)).read_text(encoding="utf-8")

    def list_dir(self, path: str) -> list[str]:
        return sorted(p.name for p in (self.root / self.normalize(path)).iterdir())

    def write(self, path: str, content: str, *, ctx: AgentCtx | None = None,
              flag: str | None = None) -> dict:
        rel = self.normalize(path)
        return self._apply(rel, content.encode("utf-8"), ctx=ctx, flag=flag)

    def send_external(self, message: str, *, contains_canary: bool,
                      ctx: AgentCtx | None = None) -> dict:
        outbox = self.root / OUTBOX_FILE
        outbox.parent.mkdir(parents=True, exist_ok=True)
        sent = len(outbox.read_text(encoding="utf-8").splitlines()) if outbox.exists() else 0
        msg_id = f"msg_{sent + 1:04d}"
        with outbox.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"msg_id": msg_id, "message": message}) + "\n")
        event = self.log.emit("external_send", ctx, msg_id=msg_id,
                              content_hash=sha256(message.encode("utf-8")),
                              contains_canary=contains_canary)
        self.index_writes([event])
        return event

    def manifest(self) -> dict:
        files = {}
        for p in sorted(self.root.rglob("*")):
            rel = p.relative_to(self.root).as_posix()
            if p.is_file() and not _in_outbox(rel):
                files[rel] = sha256(p.read_bytes())
        return files

    def tree_hash(self) -> str:
        return hash_manifest(self.manifest())

    def snapshot(self) -> SnapshotRef:
        snapshot_id = f"snap_{sum(1 for _ in (self.store / 'snapshots').glob('*')) + 1:03d}" \
            if (self.store / "snapshots").exists() else "snap_001"
        path = self.store / "snapshots" / snapshot_id
        shutil.copytree(self.root, path, ignore=_ignore_outbox(self.root))
        manifest = self.manifest()
        ref = SnapshotRef(snapshot_id, path, hash_manifest(manifest), manifest)
        self.log.emit("world_snapshot", snapshot_id=snapshot_id, tree_hash=ref.tree_hash,
                      manifest=manifest)
        return ref

    def restore(self, ref: SnapshotRef) -> None:
        for child in self.root.iterdir():
            if child.name == OUTBOX:
                continue
            shutil.rmtree(child) if child.is_dir() else child.unlink()
        shutil.copytree(ref.path, self.root, dirs_exist_ok=True)
        self.log.emit("world_restore", snapshot_id=ref.snapshot_id, tree_hash=ref.tree_hash,
                      manifest=ref.manifest)

    def index_writes(self, events: list[dict]) -> None:
        """Make logged writes undoable, e.g. those of a finished run during recovery."""
        for e in events:
            if e["type"] in ("file_write", "external_send"):
                self._writes[e["event_id"]] = e

    def undo_writes(self, write_event_ids: list[str]) -> list[str]:
        """Undo writes newest first. Returns what could not be undone."""
        order = list(self._writes)
        leftovers = [f"unknown:{i}" for i in write_event_ids if i not in self._writes]
        known = [i for i in write_event_ids if i in self._writes]
        for event_id in sorted(known, key=order.index, reverse=True):
            event = self._writes[event_id]
            if event["type"] == "external_send":
                leftovers.append(f"notify_vendor:{event['msg_id']}")
                continue
            rel = event["path"]
            target = self.root / rel
            current = sha256(target.read_bytes()) if target.exists() else None
            if current != event["post_hash"]:
                # A later write outside this set owns the file now; do not clobber it.
                leftovers.append(f"conflict:{rel}")
                continue
            blob = event["undo_blob"]
            content = None if blob is None else (self.store / "blobs" / blob).read_bytes()
            self._apply(rel, content, ctx=None, flag="undo")
        return leftovers

    def _apply(self, rel: str, content: bytes | None, *, ctx: AgentCtx | None,
               flag: str | None) -> dict:
        target = self.root / rel
        pre = target.read_bytes() if target.exists() else None
        pre_hash = None if pre is None else sha256(pre)
        if pre is not None:
            (self.store / "blobs" / pre_hash).write_bytes(pre)
        if content is None:
            if target.exists():
                target.unlink()
            post_hash = None
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            post_hash = sha256(content)
        event = self.log.emit("file_write", ctx, path=rel, pre_hash=pre_hash, post_hash=post_hash,
                              undo_blob=pre_hash, flag=flag)
        self.index_writes([event])
        return event


def _ignore_outbox(root: Path):
    def ignore(directory: str, names: list[str]) -> list[str]:
        return [OUTBOX] if Path(directory).resolve() == root else []
    return ignore


def replay_tree_hash(events: list[dict]) -> str:
    """Rebuild the tree hash from the event log alone."""
    manifest: dict = {}
    for e in events:
        if e["type"] in ("world_snapshot", "world_restore"):
            manifest = dict(e["manifest"])
        elif e["type"] == "file_write" and not _in_outbox(e["path"]):
            if e["post_hash"] is None:
                manifest.pop(e["path"], None)
            else:
                manifest[e["path"]] = e["post_hash"]
    return hash_manifest(manifest)
