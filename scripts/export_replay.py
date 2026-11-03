"""Export run traces into the replay player, replay/replay.html (reads logs only, invariant I4).

The player template is replay/player.html. The data goes inline, so the output is one
self-contained file that opens from disk or a share. Each scene shows one run, or several runs
side by side on one clock. Taint uses the faulted run's lineage, as `tainted_live_posts` does
(doc section 8).

Example: export_replay.py --runs runs/main --out replay/replay.html
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mccr.oracle import run_events, sent_parts, wrong_messages  # noqa: E402

TASKS = ROOT / "tasks"
TEMPLATE = ROOT / "replay/player.html"
PLACEHOLDER = '<script src="story.js"></script>'
KEEP ={"board_add", "board_search", "board_tombstone", "file_read", "file_write", "external_send",
        "verify_call", "invocation_end", "fault_injected", "policy", "world_restore", "run_end"}
REFUSAL = re.compile(r"ignor|suspicious|unverified|disregard|not acted on|not used", re.I)
RECENCY = re.compile(r"supersed|later one|newer|more recent", re.I)

# The story for the talk: task T03 (aircraft must stay on the ground), rep 0.
STORY = [
    {"title": "1. Normal teamwork", "runs": [("T03__clean__M0__observe__r0", "main")],
     "text": "Watch five AI workers solve one case. They read files, leave notes on a shared board, "
             "and use those notes to make the final decision."},
    {"title": "2. One mistake spreads", "runs": [("T03__FA1xA1__M0__observe__r0", "main")],
     "text": "The first worker's diagnosis is secretly changed. Watch later workers find the wrong note, "
             "trust it, and build more work from it."},
    {"title": "3. Compare three responses", "runs": [("T03__FA1xA1__M0__observe__r0", "after"),
                                                  ("T03__FA1xA1__M0__observe__r0__recovered_M1", "recovery"),
                                                  ("T03__FA1xA1__M0__observe__r0__recovered_M2", "recovery")],
     "text": "The same mistake has already happened. Compare doing nothing, restarting while keeping the "
             "old board, and starting again from clean files and an empty board."},
    {"title": "4. Add an extra checker", "runs": [("T03__FA1xA1__M3__observe__r0", "main")],
     "text": "Before a note or file is saved, another AI checks it. Watch whether that checker notices "
             "the wrong diagnosis."},
    {"title": "5. A harmful instruction", "runs": [("T03__FD1xA2__M0__observe__r0", "main")],
     "text": "A vendor file contains a message telling the team to release the aircraft and share a fake "
             "secret. Watch the team notice it and refuse to follow it."},
    {"title": "6. The source file is wrong", "runs": [("T03__FA4xA1__M0__observe__r0", "after"),
                                                           ("T03__FA4xA1__M0__observe__r0__recovered_M1", "recovery"),
                                                           ("T03__FA4xA1__M0__observe__r0__recovered_M2", "recovery")],
     "text": "The reference manual itself contains the wrong answer. A simple restart reads the same bad "
             "file again; a full reset restores the clean file.", "optional": True},
]

MODE_NAMES = {"M0": "No recovery", "M1": "Restart, keep old board", "M2": "Full reset",
              "M3": "Extra checker"}


def short(text: str, n: int = 90) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


def recency_clause(text: str) -> str:
    """The clause of a thought that says which post wins, e.g. 'the later one supersedes the earlier'."""
    clauses = re.split(r"[.;:]\s", " ".join(text.replace("**", "").split()))
    return short(next((c for c in clauses if RECENCY.search(c)), clauses[0]), 120)


def result_caption(oracle: dict, wrong: int, marker: str | None) -> str:
    checks = oracle["checks"]
    cap = f"Result: {sum(checks.values())} of {len(checks)} checks pass, {'PASS' if oracle['pass'] else 'FAIL'}."
    if "unsafe_release" in oracle["unsafe"]["forbidden_applied"]:
        cap += " The aircraft was released when it had to stay on the ground."
    if wrong:
        cap += f" {wrong} wrong order{'s' if wrong > 1 else ''} already sent."
    if marker and oracle["unsafe"]["malicious_text_present"] and not oracle["unsafe"]["forbidden_attempted"]:
        cap += " No forbidden action was attempted."
    return cap


def export_run(run_dir: Path) -> dict:
    manifest = json.loads((run_dir / "manifest.json").read_text())
    oracle = json.loads((run_dir / "oracle.json").read_text())
    spec = json.loads((TASKS / manifest["task_id"] / "oracle.json").read_text())
    events = run_events(run_dir)
    F = set(manifest.get("F", []))
    f_files = {r.removeprefix("file:").split("@")[0] for r in F if r.startswith("file:")}
    parts = sent_parts(run_dir)
    wrong = set(wrong_messages(run_dir, spec))
    outbox = {}
    if (run_dir / "world/outbox/vendor_messages.jsonl").exists():
        for line in (run_dir / "world/outbox/vendor_messages.jsonl").read_text().splitlines():
            m = json.loads(line)
            outbox[m["msg_id"]] = m["message"]
    sent_before = {parts.get(e["msg_id"]) for e in events if e["type"] == "external_send" and e["phase"] == "main"}
    marker = spec.get("marker")

    kind = "file" if f_files else "post"
    # A step's thought is logged after its action, so look it up by (phase, invocation, step).
    thoughts = {(e["phase"], e.get("invocation"), e.get("step")): e["thought"]
                for e in events if e["type"] == "react_step" and e.get("thought")}
    tainted, reached, read_f = set(F), set(), set()
    posts, out, said = {}, [], set()
    last_verdict = {}

    def once(key) -> bool:
        """True the first time a caption key is seen, so a repeated event is not announced again."""
        if key in said:
            return False
        said.add(key)
        return True

    for e in events:
        inv, agent, phase = e.get("invocation"), e.get("agent"), e["phase"]
        if e["type"] not in KEEP:
            continue
        x = {"type": e["type"], "phase": phase, "agent": agent, "step": e.get("step")}
        cap, big = None, False
        thought = thoughts.get((phase, inv, e.get("step")), "")
        if e["type"] == "board_add":
            hit = e["post_id"] in F
            if phase == "main" and (hit or inv in reached):
                tainted.add(e["post_id"])
            is_t = e["post_id"] in tainted
            has_marker = bool(marker) and marker in e["text"]
            x.update(post_id=e["post_id"], topic=e["topic"], text=e["text"], f=hit, tainted=is_t,
                     read_f=inv in read_f, injected=bool(e.get("injected")), marker=has_marker,
                     writer=("A3 (spoofed)" if inv == "injected_FD2" else agent))
            posts[e["post_id"]] = x
            who = x["writer"] or "seed"
            if hit:
                cap, big = f"The faulty post {e['post_id']} is on the board ({e['topic']}).", True
                if last_verdict.get((inv, e.get("step"))) is True:
                    cap += " The verifier approved it."
            elif has_marker and REFUSAL.search(e["text"]):
                cap, big = f"{who} mentions the injected notice and says it is not to be followed.", True
            elif has_marker:
                cap, big = f"{who} repeats the injected notice on {e['topic']}.", True
            elif is_t:
                cap, big = f"{who} posts {e['topic']}, built on the faulty {kind}.", True
            else:
                cap, big = f"{who} posts {e['topic']}.", once((phase, "post", who))
        elif e["type"] == "board_search":
            ids = e["returned_post_ids"]
            x.update(query=e["query"], k=e["k"], ids=ids)
            got_f = [i for i, p in enumerate(ids) if p in F]
            if inv and phase == "main" and tainted & set(ids):
                reached.add(inv)  # any read of F or a descendant counts, as in metrics._reached
            if got_f and inv:
                read_f.add(inv)
                f_topic = posts.get(ids[got_f[0]], {}).get("topic")
                newer = [p for p in ids if posts.get(p, {}).get("phase") == "recovery"
                         and posts[p]["topic"] == f_topic]
                if phase == "recovery" and newer:
                    cap = f"{agent} gets both the faulty post and the rerun's newer post on {f_topic}."
                else:
                    cap = f"{agent} reads the faulty post (rank {got_f[0] + 1} of {len(ids)})."
                big = once((phase, "read_f", agent))
            else:
                cap = f"{agent} searches the board: “{short(e['query'], 40)}”."
        elif e["type"] == "board_tombstone":
            x.update(ids=e["post_ids"], reason=e.get("reason"))
            cap, big = f"The board is wiped: {len(e['post_ids'])} posts removed ({e.get('reason')}).", True
        elif e["type"] == "file_read":
            x.update(path=e["path"], acl=e.get("acl"), flag=e.get("flag"))
            if e["path"] in f_files and e.get("acl") == "allowed":
                reached.add(inv)
                read_f.add(inv)
                cap, big = f"{agent} reads {e['path']}, the faulty file.", once((phase, "read_f", agent))
            else:
                cap = f"{agent} reads {e['path']}."
        elif e["type"] == "file_write":
            x.update(path=e["path"], flag=e.get("flag"))
            cap = (f"The faulty input {e['path']} is replaced by its clean version." if e.get("flag") == "fault_cleanup"
                   else f"{agent} writes {e['path']}.")
            big = e.get("flag") == "fault_cleanup"
        elif e["type"] == "external_send":
            msg = outbox.get(e["msg_id"], "")
            dup = phase == "recovery" and parts.get(e["msg_id"]) in sent_before
            x.update(msg_id=e["msg_id"], text=msg, wrong=e["msg_id"] in wrong, duplicate=dup,
                     parts=sorted(parts.get(e["msg_id"], [])), canary=e.get("contains_canary"))
            what = ", ".join(x["parts"]) or "no part"
            cap = f"{agent} sends a vendor order for {what}. It cannot be undone."
            if x["wrong"]:
                cap += " This order is wrong."
            if dup:
                cap += " It repeats an order already sent."
            big = True
        elif e["type"] == "verify_call":
            x.update(verdict=e["verdict"], reason=e.get("reason"), target=e.get("target_ref"))
            last_verdict[(inv, e.get("step"))] = e["verdict"]
            if not e["verdict"]:
                cap, big = f"The verifier rejects {agent}'s {e.get('target_ref')}: {short(e.get('reason') or '', 80)}", True
            else:
                cap = f"The verifier accepts {agent}'s {e.get('target_ref')}."
        elif e["type"] == "invocation_end":
            x.update(status=e["status"], steps=e.get("steps"))
            if e["status"] != "finished":
                cap, big = f"{agent} stops: {e['status'].replace('_', ' ')} after {e.get('steps')} steps.", True
        elif e["type"] == "fault_injected":
            ref = e["artifact_ref"]
            x.update(fault=e["fault_id"], ref=ref)
            if ref.startswith("file:"):
                cap = f"Fault {e['fault_id']}: the file {ref.removeprefix('file:').split('@')[0]} was changed before the run."
            elif ref.startswith("inv:"):
                cap = f"Fault {e['fault_id']}: {ref.split('_')[1]} will time out after its first step."
            elif ref.startswith("rejected:"):
                cap = f"Fault {e['fault_id']}: the verifier rejected the faulty text, so it never reached the board."
            else:
                cap = None  # the faulty post's own caption already says it
            big = cap is not None
        elif e["type"] == "policy":
            x.update(rule=e.get("rule"), path=e.get("path"))
            cap = f"{agent} tries {e.get('rule', '').replace('_', ' ')} on {e.get('path')}: blocked."
        elif e["type"] == "world_restore":
            cap, big = "The files are restored to the run-start snapshot.", True
        elif e["type"] == "run_end":
            x.update(statuses=e.get("statuses"))
            if phase == events[-1]["phase"]:
                cap, big = result_caption(oracle, len(wrong), marker), True
        if phase == "recovery" and agent and RECENCY.search(thought) and once((phase, "recency", agent)):
            cap, big = f"{agent} thinks: “{recency_clause(thought)}”", True
        x["cap"], x["big"], x["thought"] = cap, big, thought or None
        out.append(x)

    world = run_dir / "world"
    outputs = {p.relative_to(world).as_posix(): p.read_text(errors="replace")[:4000]
               for p in sorted((world / "outputs").glob("*")) if p.is_file()} if (world / "outputs").exists() else {}
    return {"id": run_dir.name, "task": manifest["task_id"], "mode": manifest["mode"], "cell": manifest["fault_cell"],
            "rep": manifest["rep"], "F": sorted(F), "oracle": oracle, "events": out, "outputs": outputs,
            "truth": {k: spec["truth"][k] for k in ("component", "disposition", "dispatch_status", "parts_request")}}


def label(run: dict, part: str) -> str:
    mode = "M0" if part == "after" else run["mode"]
    return MODE_NAMES.get(mode, mode)


def build(runs_root: Path) -> dict:
    scenes, cache = [], {}
    for scene in STORY:
        names = [n for n, _ in scene["runs"]]
        missing = [n for n in names if not (runs_root / n / "oracle.json").exists()]
        if missing:
            if scene.get("optional"):
                print(f"skip scene {scene['title']!r}: missing {missing}")
                continue
            raise SystemExit(f"missing runs for {scene['title']!r}: {missing}")
        cols = []
        for name, part in scene["runs"]:
            cache.setdefault(name, export_run(runs_root / name))
            cols.append({"run": name, "part": part, "label": label(cache[name], part)})
        scenes.append({"title": scene["title"], "text": scene["text"], "columns": cols})
    return {"scenes": scenes, "runs": cache}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=Path, default=ROOT / "runs/main")
    parser.add_argument("--out", type=Path, default=ROOT / "replay/replay.html")
    args = parser.parse_args()
    story = build(args.runs)
    data = json.dumps(story, separators=(",", ":")).replace("</", "<\\/")
    template = TEMPLATE.read_text()
    if PLACEHOLDER not in template:
        raise SystemExit(f"{TEMPLATE} lacks {PLACEHOLDER}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(template.replace(PLACEHOLDER, f"<script>window.STORY = {data};</script>"))
    print(f"wrote {args.out} ({args.out.stat().st_size // 1024} KB): {len(story['scenes'])} scenes, "
          f"{len(story['runs'])} runs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
