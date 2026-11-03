"""Inline SVG diagrams for docs/PROJECT_GUIDE.html. Plain strings, no libraries."""
from __future__ import annotations

from html import escape as esc

_n = [0]
AG = ["A1", "A2", "A3", "A4", "A5"]


def _svg(w, h, label, body):
    _n[0] += 1
    mid = f"ah{_n[0]}"
    return (f'<svg class="fig" viewBox="0 0 {w} {h}" role="img" aria-label="{esc(label)}">'
            f'<defs><marker id="{mid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
            f'<path d="M0 0L10 5L0 10z" fill="currentColor"/></marker></defs>{body.replace("@@M@@", mid)}</svg>')


def _t(x, y, s, anchor="middle", cls=""):
    spans = "".join(f'<tspan x="{x}" dy="{0 if i == 0 else 14}">{esc(p)}</tspan>' for i, p in enumerate(s.split("\n")))
    return f'<text x="{x}" y="{y}" text-anchor="{anchor}" class="{cls}">{spans}</text>'


def _box(x, y, w, h, s, cls="nd"):
    n = len(s.split("\n"))
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" class="{cls}"/>' + _t(x + w / 2, y + h / 2 + 4 - (n - 1) * 7, s)


def _ln(x1, y1, x2, y2, cls="ln", arrow=True):
    m = ' marker-end="url(#@@M@@)"' if arrow else ""
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" class="{cls}"{m}/>'


def _path(d, cls="ln", arrow=True):
    m = ' marker-end="url(#@@M@@)"' if arrow else ""
    return f'<path d="{d}" class="{cls}"{m}/>'


def _fig(svg, caption):
    return f"<figure>{svg}<figcaption>{esc(caption)}</figcaption></figure>"


_MODES = {
    "M0": ("M0 no recovery", set(), "nothing is redone: this shows how far the fault spread"),
    "M1": ("M1 restart,\nkeep board", set(AG), "the board keeps the wrong post, so the rerun can read it again"),
    "M2": ("M2 restart,\nwipe all", set(AG), "board emptied and files restored: correct, but everything is redone"),
    "M3": ("M3 always-\nverify", set(AG), "a fresh run with the fault active and a check before every write"),
    "M4": ("M4 selective\n(Phase 2)", {"A1", "A3", "A4", "A5"}, "redo only what read the wrong post; A2 is kept. Not built yet"),
}


def _modes(keys, label):
    xs = [150 + 100 * i for i in range(5)]
    top, step = 104, 78
    h = top + step * len(keys) + 20
    b = _t(8, 44, "Faulty run", "start", "b")
    for i, a in enumerate(AG):
        b += _box(xs[i], 28, 80, 30, a, "nd-bad" if a == "A1" else "nd")
    for t in (2, 3, 4):
        b += _path(f"M{xs[0] + 40} 28 V10 H{xs[t] + 40} V26", "ln ln-bad")
    b += _t(xs[0], 76, "A1's wrong post is read by A3, A4 and A5", "start", "sm")
    for idx, k in enumerate(keys):
        name, redo, note = _MODES[k]
        y = top + idx * step
        b += _t(8, y + 18, name, "start", "b")
        for i, a in enumerate(AG):
            b += _box(xs[i], y + 6, 80, 30, a, "nd-ac" if a in redo else "nd nd-dash")
        b += _t(xs[0], y + 58, note, "start", "sm")
    b += _box(150, h - 18, 14, 12, "", "nd-ac") + _t(170, h - 8, "redone", "start", "sm")
    b += _box(240, h - 18, 14, 12, "", "nd nd-dash") + _t(260, h - 8, "kept as it was", "start", "sm")
    return _svg(720, h, label, b)


def fig_plans():
    return _fig(_modes(["M1", "M2", "M4"], "What each recovery plan redoes after A1 posts a wrong claim"),
                "After A1 posts a wrong claim, restart-and-keep and wipe-all both redo all five agents. "
                "Selective recovery (Phase 2, not built) would redo only the four that depended on the wrong post.")


def fig_modes():
    return _fig(_modes(["M0", "M1", "M2", "M3", "M4"], "What each mode M0 to M4 redoes"),
                "The five modes on the same faulty run. M0 changes nothing. M1 and M2 rerun everyone. "
                "M3 is a new run with a check before every write. M4 reruns only the dependent agents.")


def fig_arch():
    b = ""
    xs = [15, 165, 315, 465, 615]
    names = ["A1 Fault\nAnalyst", "A2 Records\nClerk", "A3 MCC\nPlanner", "A4 Work-Order\nWriter", "A5 Dispatch\n& Parts"]
    b += _box(15, 14, 125, 44, "inputs/fault\ninputs/fim") + _box(165, 14, 125, 44, "inputs/records\n(incl. vendor_feed)")
    b += _box(315, 14, 125, 44, "inputs/mel") + _t(527, 40, "A4 and A5 read no input files", "middle", "sm")
    b += _box(615, 14, 125, 44, "secrets/\n(fake canary)", "nd-bad nd-dash")
    for cx in (77, 227, 377):
        b += _ln(cx, 58, cx, 110)
    b += _t(86, 90, "may read", "start", "sm")
    b += _ln(677, 58, 677, 110, "ln ln-bad nd-dash") + _t(668, 90, "readable by all, logged as forbidden", "end", "sm")
    for x, n in zip(xs, names):
        b += _box(x, 110, 125, 44, n, "nd-ac")
        b += _ln(x + 62, 154, x + 62, 178)
    b += _box(15, 178, 725, 28, "tools.py: logs every call, checks access rules, applies policy, records undo", "nd nd-band")
    b += _box(15, 240, 480, 44, "Shared board: posts, search results, who read what")
    b += _box(530, 240, 210, 44, "world files\noutputs/   outbox/")
    b += _ln(200, 206, 200, 240) + _t(208, 226, "board_add", "start", "sm")
    b += _ln(330, 240, 330, 206) + _t(338, 226, "board_search", "start", "sm")
    b += _ln(635, 206, 635, 240) + _t(627, 226, "write_file, notify_vendor", "end", "sm")
    b += _box(15, 330, 215, 44, "events.jsonl\n(append-only log)") + _ln(120, 284, 120, 330) + _t(128, 312, "every event", "start", "sm")
    b += _box(530, 330, 210, 44, "oracle.py\ngrades files and logs", "nd-ok") + _ln(635, 284, 635, 330) + _t(643, 312, "graded", "start", "sm")
    b += _ln(230, 352, 530, 352) + _t(380, 346, "the oracle also reads the log and the board", "middle", "sm")
    return _fig(_svg(760, 392, "Architecture: five agents, tools layer, shared board, world files, log, oracle", b),
                "Agents only reach files and the board through tools.py. Every event goes to an append-only log. "
                "The oracle grades the final files and logs and never calls a model. Agents run in a fixed order, A1 to A5.")


def fig_acl():
    cols = ["inputs/\nfault", "inputs/\nfim", "inputs/\nmel", "inputs/\nrecords", "secrets/\n(canary)"]
    allow = {"A1": {0, 1}, "A2": {3}, "A3": {2}, "A4": set(), "A5": set()}
    roles = ["A1 Fault Analyst", "A2 Records Clerk", "A3 MCC Planner", "A4 Work-Order Writer", "A5 Dispatch & Parts"]
    x0, dx = 250, 90
    b = ""
    for j, c in enumerate(cols):
        b += _t(x0 + j * dx, 20, c, "middle", "sm b")
    for i, r in enumerate(roles):
        y = 66 + i * 38
        b += _ln(10, y - 22, 700, y - 22, "ln-soft", False) + _t(10, y, r, "start", "")
        for j in range(5):
            cx = x0 + j * dx
            if j == 4:
                b += f'<circle cx="{cx}" cy="{y - 4}" r="11" class="dot-warn"/>' + _t(cx, y, "!", "middle", "b")
            elif j in allow[AG[i]]:
                b += f'<circle cx="{cx}" cy="{y - 4}" r="11" class="dot-ok"/>' + _t(cx, y, "✓", "middle", "b")
            else:
                b += _t(cx, y, "–", "middle", "mut")
    b += _t(10, 270, "✓ may read     – access denied     ! can be read, but the read is logged as a forbidden attempt", "start", "sm")
    return _fig(_svg(700, 284, "Which agent may read which folder", b),
                "The routing rule is always on. Information has to travel through the board because A4 and A5 "
                "can read no input files. Everyone can read secrets/ on purpose, and that read is always flagged.")


def fig_faults():
    xs = [20, 160, 300, 440, 580]
    names = ["A1", "A2", "A3", "A4", "A5"]
    b = _box(140, 12, 150, 40, "vendor_feed.jsonl\n(poisoned)", "nd-bad") + _ln(215, 52, 215, 120, "ln ln-bad")
    b += _t(223, 90, "A2 reads it", "start", "sm")
    for x, n in zip(xs, names):
        b += _box(x, 120, 110, 40, n, "nd-ac") + _ln(x + 55, 160, x + 55, 214)
    b += _box(20, 214, 670, 34, "Shared board")
    for x in xs[:3]:
        b += f'<circle cx="{x + 100}" cy="120" r="13" class="dot-acc"/>' + _t(x + 100, 124, "FA3", "middle", "sm b")
    b += _t(20, 104, "FA3: the agent times out after its first call (A1, A2 or A3)", "start", "sm")
    b += f'<circle cx="62" cy="188" r="15" class="dot-acc"/>' + _t(62, 192, "FA1", "middle", "sm b") + _t(84, 192, "component swapped in A1's post", "start", "sm")
    b += f'<circle cx="62" cy="282" r="15" class="dot-acc"/>' + _t(62, 286, "FA2", "middle", "sm b") + _t(84, 286, "stale post seeded before the run", "start", "sm")
    b += _ln(62, 267, 62, 248)
    b += f'<circle cx="452" cy="282" r="15" class="dot-adv"/>' + _t(452, 286, "FD2", "middle", "sm b") + _t(474, 286, "post inserted, spoofed as A3", "start", "sm")
    b += _ln(452, 267, 452, 248, "ln ln-bad")
    b += _t(450, 20, "FD1 (red): the poisoned file enters through A2", "start", "sm")
    return _fig(_svg(720, 306, "Where each of the five faults enters the system", b),
                "Amber is accidental, red is adversarial. FA1 changes A1's post. FA2 is a stale post on the board. "
                "FA3 is a timeout. FD1 is a poisoned input file. FD2 is a post from outside the agents.")


def fig_taint():
    b = _box(10, 70, 120, 46, "faulty artifact F\n(post or file)", "nd-bad")
    b += _box(170, 70, 120, 46, "invocation that\nread F", "nd-bad") + _ln(130, 93, 170, 93) + _t(150, 64, "read", "middle", "sm")
    b += _box(330, 70, 110, 46, "post it wrote\nafter that read", "nd-bad") + _ln(290, 93, 330, 93) + _t(310, 64, "writes", "middle", "sm")
    b += _box(480, 70, 110, 46, "invocation that\nread that post", "nd-bad") + _ln(440, 93, 480, 93) + _t(460, 64, "read", "middle", "sm")
    b += _box(630, 30, 100, 40, "file write\n(undo from log)", "nd-bad") + _ln(590, 82, 630, 56) + _t(612, 56, "", "middle", "sm")
    b += _box(630, 110, 100, 40, "message sent\n(cannot undo)", "nd-bad nd-dash") + _ln(590, 104, 630, 128)
    b += _box(170, 170, 120, 46, "invocation that\nnever read F", "nd-ok") + _t(310, 196, "kept, not rerun", "start", "sm")
    b += _t(10, 236, "red = tainted: tombstone the post, undo the file write, rerun the invocation. A sent message can only be reported.", "start", "sm")
    return _fig(_svg(740, 250, "How taint spreads from a faulty artifact to everything that depended on it", b),
                "Phase 2 idea. Starting from F, mark every invocation that read a tainted item and everything it wrote. "
                "Finer lineage (read windows) marks only what was written after the tainted read.")


def fig_m3():
    b = _t(8, 24, "Before (found in E15): the fault was applied after the check", "start", "b")
    b += _box(10, 40, 130, 40, "A1 proposes\ncorrect text") + _ln(140, 60, 210, 60) + _t(175, 54, "correct", "middle", "sm")
    b += _box(210, 40, 130, 40, "verifier sees\nthe correct text") + _ln(340, 60, 410, 60) + _t(375, 54, "OK", "middle", "sm")
    b += _box(410, 40, 120, 40, "board stores") + _ln(530, 60, 580, 60)
    b += _box(580, 40, 150, 40, "fault swap here,\nwrong text kept", "nd-bad")
    b += _t(8, 124, "After (E18): the fault is applied before the check", "start", "b")
    b += _box(10, 140, 130, 40, "A1 proposes\ncorrect text") + _ln(140, 160, 210, 160)
    b += _box(210, 140, 130, 40, "fault swap\nhere", "nd-bad") + _ln(340, 160, 410, 160) + _t(375, 154, "wrong", "middle", "sm")
    b += _box(410, 140, 130, 40, "verifier sees\nthe wrong text") + _ln(540, 160, 590, 160)
    b += _box(590, 140, 140, 40, "board stores,\nor the post is rejected")
    return _fig(_svg(740, 200, "Where the FA1 fault sits relative to the M3 verifier, before and after the fix", b),
                "The only change is the order of two steps. Before, the check could never see the wrong text. "
                "After, it sees what a real wrong claim would look like.")


def fig_phases():
    x0, px, top, rh = 215, 12.4, 56, 30
    rows = [("0   environment, probes", 0, 2, "done"), ("1A  harness (scripted)", 1, 3, "done"),
            ("1B  tasks and oracle", 1, 3, "done"), ("1C  live-model gate (PoC)", 2, 3.5, "done"),
            ("1D  matrix, analysis, report", 3, 6, "now"), ("2A  provenance and M4", 6, 20, "todo"),
            ("2B  evaluation, precision", 20, 33, "todo"), ("2C  retractions (optional)", 33, 37, "todo"),
            ("2D  final report, slides", 37, 42, "todo")]
    h = top + rh * len(rows) + 40
    b = ""
    for d, lab in [(0, "Oct 30"), (6, "Nov 5"), (20, "Nov 19"), (33, "Dec 1"), (42, "Dec 10")]:
        x = x0 + d * px
        b += _ln(x, 36, x, h - 30, "ln-soft", False) + _t(x, 30, lab, "middle", "sm")
    for i, (name, a, z, st) in enumerate(rows):
        y = top + i * rh
        b += _t(8, y + 16, name, "start", "") + f'<rect x="{x0 + a * px}" y="{y + 3}" width="{(z - a) * px}" height="20" rx="4" class="bar-{st}"/>'
    b += _t(x0 + 6 * px + 8, top + 4 * rh + 17, "matrix done; stress cells next", "start", "sm")
    xt = x0 + 3 * px
    b += _ln(xt, 40, xt, h - 30, "ln ln-acc", False) + _t(xt + 4, h - 16, "snapshot: 2026-11-02", "start", "sm b")
    for d, lab, anchor, dx in [(6, "Phase 1 due Nov 4", "start", 10), (42, "due Dec 10", "end", -10)]:
        x = x0 + d * px
        b += f'<polygon points="{x},{top - 8} {x + 6},{top - 2} {x},{top + 4} {x - 6},{top - 2}" class="due"/>' + _t(x + dx, top - 2, lab, anchor, "sm")
    return _fig(_svg(760, h, "Phase timeline with due dates and the state on 2026-11-02", b),
                "Dates come from section 13 of the project document. Phases 0 to 1C are done. Phase 1D is in progress: "
                "the matrix ran and was analysed, and the stress block is next. Phase 2 has not started.")


def fig_sync():
    b = _box(20, 70, 150, 60, "Your Mac\nedits code and docs") + _box(305, 70, 150, 60, "GitHub\nbranch main") + _box(590, 70, 150, 60, "EC2 instance\nruns experiments")
    b += _ln(170, 88, 305, 88) + _t(237, 82, "1  push", "middle", "sm b")
    b += _ln(305, 114, 170, 114) + _t(237, 130, "5  pull", "middle", "sm b")
    b += _ln(455, 88, 590, 88) + _t(522, 82, "2  pull", "middle", "sm b")
    b += _ln(590, 114, 455, 114) + _t(522, 130, "4  pull, then push\nresults/ only", "middle", "sm b")
    b += _t(665, 52, "3  run experiments (tmux)", "middle", "sm b")
    b += _path("M665 130 V190 H95 V132", "ln ln-dash") + _t(380, 184, "runs/ never goes through git; copy it with rsync if you want it on the Mac", "middle", "sm")
    b += _t(380, 234, "Pull before every push, on both machines.", "middle", "b")
    return _fig(_svg(760, 250, "The sync routine between the Mac, GitHub and the instance", b),
                "Numbers give the order. Code and docs travel from the Mac. Result files travel from the instance. "
                "Run folders stay out of git.")


def fig_lifecycle():
    b = _box(40, 70, 160, 60, "Running\nabout $0.08 per hour") + _box(320, 70, 160, 60, "Stopped\ndisk about $1.60 per month")
    b += _box(600, 70, 140, 60, "Terminated\ngone for good", "nd-bad")
    b += _ln(200, 88, 320, 88) + _t(260, 82, "stop", "middle", "sm b") + _t(130, 150, "stop: disk kept, IP released,\nrunning jobs end", "middle", "sm")
    b += _ln(320, 114, 200, 114) + _t(260, 130, "start", "middle", "sm b") + _t(400, 150, "start: files are still there,\nthe public IP is new", "middle", "sm")
    b += _ln(480, 100, 600, 100, "ln ln-bad") + _t(540, 94, "terminate", "middle", "sm b")
    b += _path("M120 70 V30 H670 V68", "ln ln-bad") + _t(395, 24, "terminate from running: disk and files are deleted. Cannot be undone.", "middle", "sm")
    b += _t(130, 190, "reboot of a running instance:\nsame disk, same IP", "middle", "sm")
    return _fig(_svg(760, 216,"Instance life cycle: running, stopped, terminated", b),
                "Stop when you are not running experiments. Before you terminate, push code to GitHub "
                "and copy the run folders off the instance.")


FIGS = {"plans": fig_plans, "modes": fig_modes, "arch": fig_arch, "acl": fig_acl, "faults": fig_faults,
        "taint": fig_taint, "m3": fig_m3, "phases": fig_phases, "sync": fig_sync, "lifecycle": fig_lifecycle}
