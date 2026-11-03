#!/usr/bin/env python3
"""Build docs/PROJECT_GUIDE.html, one self-contained file.

Inputs: the four markdown sources and the hand-written parts in docs/guide_src/.
The sources are embedded word for word (a small markdown converter, no libraries).
AWS identifiers are replaced by placeholders. The script fails if any section of a
source is not used, so nothing is silently left out.

Usage: python docs/build_guide.py
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SRC = HERE / "guide_src"
sys.path.insert(0, str(HERE))
import guide_figs as figs  # noqa: E402

SOURCES = {
    "IMPL": ("IMPLEMENTATION_CONTEXT_DOC.md", ROOT / "IMPLEMENTATION_CONTEXT_DOC.md"),
    "LOG": ("EXPERIMENT_ANALYSIS.md", ROOT / "EXPERIMENT_ANALYSIS.md"),
    "GUIDE": ("ANALYST_GUIDE.md", ROOT / "ANALYST_GUIDE.md"),
    "AWS": ("aws/README.md", ROOT / "aws/README.md"),
}
TABS = [
    ("start", "Start here"), ("system", "The system"), ("faults", "Faults and tasks"),
    ("recovery", "Recovery methods"), ("found", "What we did and found"),
    ("run", "Run it"), ("next", "Next steps and decisions"), ("glossary", "Glossary and source map"),
]
REDACTIONS = [
    (r"i-0200db8f0268c7340", "<OLD_INSTANCE_ID>"), (r"i-03014c108a7b7b4d1", "<NEW_INSTANCE_ID>"),
    (r"i-[0-9a-f]{17}", "<INSTANCE_ID>"), (r"sg-[0-9a-f]{17}", "<SECURITY_GROUP_ID>"),
    (r"subnet-[0-9a-f]{17}", "<SUBNET_ID>"), (r"vpc-[0-9a-f]{17}", "<VPC_ID>"),
    (r"ami-[0-9a-f]{17}", "<AMI_ID>"), (r"mccr-key", "<KEY_PAIR_NAME>"),
    (r"us-west-2", "<REGION>"), (r"us-east-1", "<BLOCKED_REGION>"),
]


def redact(text: str) -> str:
    for pattern, replacement in REDACTIONS:
        text = re.sub(pattern, replacement, text)
    return text


# ---------------------------------------------------------------- markdown

def inline(s: str) -> str:
    s = html.escape(s, quote=False)
    codes: list[str] = []

    def keep(m):
        codes.append(m.group(1))
        return f"\x00{len(codes) - 1}\x00"

    s = re.sub(r"`([^`]+)`", keep, s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)
    return re.sub(r"\x00(\d+)\x00", lambda m: f"<code>{codes[int(m.group(1))]}</code>", s)


_LIST = re.compile(r"^(\s*)([-*]|\d+\.)\s+(.*)$")


def md_to_html(text: str, shift: int = 1) -> str:
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    para: list[str] = []

    def flush():
        if para:
            out.append("<p>" + "<br>".join(inline(p) for p in para) + "</p>")
            para.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("```"):
            flush()
            i += 1
            code = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1
            out.append("<pre><code>" + html.escape("\n".join(code), quote=False) + "</code></pre>")
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            flush()
            level = min(6, len(m.group(1)) + shift)
            out.append(f"<h{level}>{inline(m.group(2))}</h{level}>")
            i += 1
            continue
        if stripped == "---":
            flush()
            out.append("<hr>")
            i += 1
            continue
        if stripped.startswith("|"):
            flush()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            head, body = rows[0], [r for r in rows[2:]] if len(rows) > 1 else []
            t = "<div class='tw'><table class='md'><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head)
            t += "</tr></thead><tbody>"
            for r in body:
                t += "<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>"
            out.append(t + "</tbody></table></div>")
            continue
        lm = _LIST.match(line)
        if lm:
            flush()
            indent, ordered = len(lm.group(1)), lm.group(2)[0].isdigit()
            items = []
            while i < len(lines):
                lm = _LIST.match(lines[i])
                if not lm or len(lm.group(1)) != indent:
                    # a blank line followed by another item at this indent continues the list
                    j = i
                    while j < len(lines) and not lines[j].strip():
                        j += 1
                    nxt = _LIST.match(lines[j]) if j < len(lines) else None
                    if j > i and nxt and len(nxt.group(1)) == indent:
                        i = j
                        continue
                    break
                body = [lm.group(3)]
                i += 1
                while i < len(lines):
                    nl = lines[i]
                    if not nl.strip():
                        j = i
                        while j < len(lines) and not lines[j].strip():
                            j += 1
                        if j < len(lines) and len(lines[j]) - len(lines[j].lstrip()) > indent:
                            body.append("")
                            i += 1
                            continue
                        break
                    if len(nl) - len(nl.lstrip()) > indent:
                        body.append(nl)
                        i += 1
                        continue
                    break
                first, rest = body[0], body[1:]
                pad = min((len(r) - len(r.lstrip()) for r in rest if r.strip()), default=0)
                rest = [r[pad:] for r in rest]
                inner = inline(first)
                if any(r.strip() for r in rest):
                    inner += md_to_html("\n".join(rest), shift=shift)
                items.append(f"<li>{inner}</li>")
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(items) + f"</{tag}>")
            continue
        if not stripped:
            flush()
            i += 1
            continue
        para.append(line)
        i += 1
    flush()
    return "\n".join(out)


def split_sections(md: str):
    """Split at '## ' headings, ignoring lines inside code fences."""
    intro: list[str] = []
    secs: dict[str, list[str]] = {}
    titles: dict[str, str] = {}
    cur, fence = intro, False
    for line in md.split("\n"):
        if line.strip().startswith("```"):
            fence = not fence
        if not fence and line.startswith("## "):
            title = line[3:].strip()
            m = re.match(r"(\d+)\.", title) or re.match(r"(E\d+):", title)
            key = m.group(1) if m else title
            secs[key], titles[key] = [line], title
            cur = secs[key]
            continue
        cur.append(line)
    return "\n".join(intro), {k: "\n".join(v) for k, v in secs.items()}, titles


class Sources:
    def __init__(self):
        self.parts, self.used = {}, {}
        for tag, (name, path) in SOURCES.items():
            intro, secs, titles = split_sections(redact(path.read_text(encoding="utf-8")))
            intro = re.sub(r"(?m)^# .*\n", "", intro, count=1)
            self.parts[tag] = (intro, secs, titles)
            self.used[tag] = set()

    def section(self, tag: str, key: str) -> str:
        intro, secs, _ = self.parts[tag]
        name = SOURCES[tag][0]
        self.used[tag].add(key)
        if key == "intro":
            return f'<div class="src" data-src="{name}">{md_to_html(intro)}</div>'
        label = f"{name} §{key}" if key.isdigit() else f"{name}"
        return f'<div class="src" data-src="{label}">{md_to_html(secs[key])}</div>'

    def everything(self, tag: str) -> str:
        _, secs, _ = self.parts[tag]
        return self.section(tag, "intro") + "".join(self.section(tag, k) for k in secs)

    def missing(self):
        gaps = []
        for tag, (intro, secs, _) in self.parts.items():
            for key in ["intro", *secs]:
                if key not in self.used[tag]:
                    gaps.append(f"{SOURCES[tag][0]}: {key}")
        return gaps


def log_timeline(src: Sources) -> str:
    summaries = json.loads((SRC / "log_summaries.json").read_text(encoding="utf-8"))
    _, secs, titles = src.parts["LOG"]
    items = []
    for key, body in secs.items():
        if not re.fullmatch(r"E\d+", key):
            continue
        src.used["LOG"].add(key)
        src.where.setdefault(("LOG", key), set()).add("What we did and found")
        m = re.search(r"(?m)^- Type: (.+)$", body)
        etype = (m.group(1) if m else "").lower()
        kind = next((k for k in ("correction", "experiment", "change", "decision", "analysis") if k in etype), "analysis")
        title = titles[key].split(":", 1)[1].strip()
        body_html = md_to_html("\n".join(body.split("\n")[1:]), shift=2)
        items.append(
            f'<li class="tl t-{kind}" id="log-{key}"><details><summary>'
            f'<span class="eid">{key}</span><span class="badge b-{kind}">{html.escape(m.group(1) if m else "")}</span>'
            f'<span class="etitle">{html.escape(title)}</span>'
            f'<span class="esum">{html.escape(summaries[key])}</span></summary>'
            f'<div class="src" data-src="EXPERIMENT_ANALYSIS.md {key}">{body_html}</div></details></li>'
        )
    missing = [k for k in secs if re.fullmatch(r"E\d+", k) and k not in summaries]
    if missing:
        raise SystemExit(f"log_summaries.json lacks: {missing}")
    return '<ol class="timeline">' + "".join(items) + "</ol>"


def source_map(src: Sources) -> str:
    rows = []
    for tag, (name, _) in SOURCES.items():
        _, secs, titles = src.parts[tag]
        for key in secs:
            where = ", ".join(sorted(src.where.get((tag, key), []))) or "n/a"
            rows.append(f"<tr><td><code>{html.escape(name)}</code></td><td>{html.escape(titles[key])}</td><td>{where}</td></tr>")
    return ("<div class='tw'><table class='md'><thead><tr><th>Source file</th><th>Section</th><th>Appears in tab</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table></div>")


def build() -> int:
    src = Sources()
    src.where = {}
    tok = re.compile(r"\{\{(\w+):([^}]+)\}\}")
    panels = []
    for n, (slug, title) in enumerate(TABS, start=1):
        text = (SRC / f"tab{n}.html").read_text(encoding="utf-8")

        def repl(m, tab=title):
            kind, arg = m.group(1), m.group(2)
            if kind == "FIG":
                return figs.FIGS[arg]()
            if kind == "LOG" and arg == "TIMELINE":
                return log_timeline(src)
            if kind == "MAP":
                return "@@SOURCE_MAP@@"
            if arg == "ALL":
                for k in ["intro", *src.parts[kind][1]]:
                    src.where.setdefault((kind, k), set()).add(tab)
                return src.everything(kind)
            src.where.setdefault((kind, arg), set()).add(tab)
            return src.section(kind, arg)

        body = tok.sub(repl, text)
        panels.append(
            f'<section id="tab-{slug}" class="panel" role="tabpanel" aria-labelledby="btn-{slug}" hidden>{body}</section>')
    page = "".join(panels)
    page = page.replace("@@SOURCE_MAP@@", source_map(src))
    nav ="".join(
        f'<button role="tab" id="btn-{s}" aria-controls="tab-{s}" aria-selected="false" data-tab="{s}">'
        f'<span class="num">{i}</span>{t}</button>' for i, (s, t) in enumerate(TABS, start=1))
    shell = (SRC / "shell.html").read_text(encoding="utf-8")
    result = (shell.replace("@@CSS@@", (SRC / "style.css").read_text(encoding="utf-8"))
              .replace("@@JS@@", (SRC / "app.js").read_text(encoding="utf-8"))
              .replace("@@NAV@@", nav).replace("@@PANELS@@", page))
    out = HERE / "PROJECT_GUIDE.html"
    out.write_text(result, encoding="utf-8")
    gaps = src.missing()
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")
    if gaps:
        print("NOT COVERED:", *gaps, sep="\n  ")
        return 1
    print("coverage: every section of the four sources is used")
    return 0


if __name__ == "__main__":
    sys.exit(build())
