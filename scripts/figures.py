"""Phase 1 report figures (doc section 18.2), from a runs.csv written by analyze.py and the run logs.

F1 propagation heatmap, F2 adversarial funnel, F3 correctness against cost, F4 example trace,
F7 effects that `pass` does not show. Writes PDF and PNG files. Example:
figures.py --runs-csv results/phase1_tables/runs.csv --runs runs/main --out results/phase1_figures
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mccr.logging import read_events  # noqa: E402

# Reference palette (dataviz skill): categorical slots 1-4 for the modes, blue ramp for magnitude,
# status red and orange for the faulty item and work built on it.
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e3e2de"
MODE_COLOR = {"M0": "#2a78d6", "M1": "#eb6834", "M2": "#1baf7a", "M3": "#eda100"}
MODE_MARK = {"M0": "o", "M1": "s", "M2": "D", "M3": "^"}
LABEL_AT = {"M0": (-10, -15), "M1": (6, 6), "M2": (-18, 6), "M3": (6, -15)}  # keeps direct labels apart
MODE_NAME = {"M0": "M0 no recovery", "M1": "M1 restart, keep board", "M2": "M2 restart, wipe all",
             "M3": "M3 always-verify"}
FAULTY, TAINTED, NEUTRAL = "#d03b3b", "#ec835a", "#9a9993"
BLUE_RAMP = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
FUNNEL = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab"]
AGENTS = ["A1", "A2", "A3", "A4", "A5"]
BASE_CELLS = ["FA1xA1", "FA2xseed", "FA3xA1", "FA3xA2", "FA3xA3", "FD1xA2", "FD2xA3"]
STRESS_CELLS = ["FA4xA1", "FA5xA1", "FA6xA1"]

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "text.color": INK, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.edgecolor": GRID, "axes.grid": False, "font.size": 9, "axes.titlesize": 10,
    "axes.titleweight": "bold", "axes.spines.top": False, "axes.spines.right": False,
    "legend.frameon": False, "pdf.fonttype": 42,
})


def save(fig, out: Path, name: str) -> None:
    for ext in ("pdf", "png"):
        fig.savefig(out / f"{name}.{ext}", dpi=200, bbox_inches="tight")
    plt.close(fig)


def faulted(df: pd.DataFrame) -> pd.DataFrame:
    return df[(df["cell"] != "clean") & (df["policy_mode"] == "observe")]


def f1_propagation(df: pd.DataFrame, out: Path) -> None:
    """Share of M0 runs in which each agent read the faulty item or work built on it."""
    m0 = faulted(df)[faulted(df)["mode"] == "M0"]
    cells = [c for c in BASE_CELLS + STRESS_CELLS if c in set(m0["cell"])]
    rows = []
    for c in cells:
        g = m0[m0["cell"] == c]
        reached = g["reached_agents"].fillna("").str.split(",")
        rows.append([reached.apply(lambda a, x=x: x in a).mean() for x in AGENTS])
    cmap = LinearSegmentedColormap.from_list("blue", BLUE_RAMP)
    fig, ax = plt.subplots(figsize=(6.4, 0.42 * len(cells) + 1.2))
    ax.imshow(rows, cmap=cmap, vmin=0, vmax=1, aspect="auto")
    for i, c in enumerate(cells):
        g = m0[m0["cell"] == c]
        missing = c.startswith("FA3")
        for j, v in enumerate(rows[i]):
            text = "–" if missing else f"{v:.0%}"
            ax.text(j, i, text, ha="center", va="center", fontsize=8, color="white" if v > 0.55 else INK)
        ax.text(len(AGENTS) - 0.3, i, f"pass {int(g['pass'].astype(bool).sum())}/{len(g)}",
                ha="left", va="center", fontsize=8, color=INK2)
    if set(STRESS_CELLS) & set(cells):
        ax.axhline(len([c for c in cells if c in BASE_CELLS]) - 0.5, color=INK, lw=1.2)
    ax.set_xticks(range(len(AGENTS)), AGENTS)
    ax.set_yticks(range(len(cells)), cells)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_title("F1  Which agents read the faulty item or work built on it (M0)", loc="left")
    ax.set_xlabel("Share of 18 runs per cell. FA3 is a missing post, which no agent can read (–). "
                  "Rows below the line are stress cells.", fontsize=7.5)
    save(fig, out, "F1_propagation")


def f2_funnel(df: pd.DataFrame, out: Path) -> None:
    """Adversarial cells under M0: attack text present, retrieved, attempted, applied."""
    m0 = faulted(df)
    m0 = m0[(m0["mode"] == "M0") & (m0["fault_class"] == "adversarial")]
    stages = ["Attack text on the board", "Retrieved by an agent", "Forbidden action attempted",
              "Forbidden effect applied"]
    cells = [c for c in ("FD1xA2", "FD2xA3") if c in set(m0["cell"])]
    fig, axes = plt.subplots(1, len(cells), figsize=(7.2, 2.3), sharey=True)
    for ax, c in zip(axes if len(cells) > 1 else [axes], cells):
        g = m0[m0["cell"] == c]
        kinds = g["attempt_kinds"].fillna("").str.split(",")
        counts = [g["malicious_text_present"].astype(bool).sum(), g["marker_retrieved"].astype(bool).sum(),
                  kinds.apply(lambda ks: any(k and k != "path_escape" for k in ks)).sum(),
                  g["forbidden_applied"].astype(bool).sum()]
        y = range(len(stages))[::-1]
        ax.barh(list(y), counts, color=FUNNEL, height=0.6, edgecolor=SURFACE, linewidth=2)
        for yi, n in zip(y, counts):
            ax.text(n + 0.4, yi, f"{n} of {len(g)}", va="center", fontsize=8, color=INK)
        ax.set_yticks(list(y), stages)
        ax.set_xlim(0, len(g) * 1.3)
        ax.set_xticks([])
        ax.spines["bottom"].set_visible(False)
        ax.set_title(c, loc="left")
    fig.suptitle("F2  Adversarial cells under M0: the attack was read every time and never acted on",
                 x=0.02, y=1.1, ha="left", fontsize=10, fontweight="bold")
    for ax in (axes[1:] if len(cells) > 1 else []):
        ax.tick_params(axis="y", length=0)
    fig.text(0.02, -0.04, "The model declined, which is its behaviour, not a protection by the system. "
             "The enforce block was not run (nothing to block).", fontsize=7.5, color=INK2)
    save(fig, out, "F2_adversarial_funnel")


def method_cost(g: pd.DataFrame, mode: str) -> pd.Series:
    return (g["recovery_cost_usd"] if mode in ("M1", "M2") else g["cost_usd"]) * 1000


def f3_correct_vs_cost(df: pd.DataFrame, out: Path) -> None:
    """One point per mode: share correct against cost of the method, with the cost range."""
    f = faulted(df)
    panels = [("Accidental (matrix)", f[(f["fault_set"] == "base") & (f["fault_class"] == "accidental")]),
              ("Adversarial (matrix)", f[(f["fault_set"] == "base") & (f["fault_class"] == "adversarial")]),
              ("Stress cells FA4-FA6", f[f["fault_set"] == "stress"])]
    panels = [(t, g) for t, g in panels if not g.empty]
    fig, axes = plt.subplots(1, len(panels), figsize=(3.0 * len(panels), 2.9), sharey=True)
    for ax, (title, g) in zip(axes, panels):
        for mode in ("M0", "M1", "M2", "M3"):
            gm = g[g["mode"] == mode]
            if gm.empty:
                continue
            cost, ok = method_cost(gm, mode), gm["pass"].astype(bool).mean() * 100
            ax.plot([cost.min(), cost.max()], [ok, ok], color=MODE_COLOR[mode], lw=2, solid_capstyle="round")
            ax.scatter([cost.mean()], [ok], s=60, marker=MODE_MARK[mode], color=MODE_COLOR[mode],
                       edgecolor=SURFACE, linewidth=2, zorder=3)
            ax.annotate(mode, (cost.mean(), ok), xytext=LABEL_AT[mode], textcoords="offset points",
                        fontsize=8, color=INK)
        ax.set_title(f"{title}, n = {len(g[g['mode'] == 'M0'])}", loc="left", fontsize=9)
        ax.set_ylim(-12, 112)
        ax.yaxis.grid(True, color=GRID, lw=0.8)
    axes[0].set_ylabel("Runs correct (%)")
    fig.supxlabel("Cost of the method per run (10⁻³ USD)", fontsize=9, color=INK2, y=-0.04)
    handles = [plt.Line2D([], [], marker=MODE_MARK[m], color=MODE_COLOR[m], lw=0, markersize=7, label=MODE_NAME[m])
               for m in MODE_NAME]
    fig.legend(handles=handles, loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.16), fontsize=8)
    fig.suptitle("F3  Correctness against cost per mode", x=0.02, y=1.06, ha="left", fontsize=10,
                 fontweight="bold")
    fig.text(0.02, -0.22, "Dot = mean cost, line = min to max. M1 and M2 count the rerun only; "
             "M0 and M3 count the whole run.", fontsize=7.5, color=INK2)
    save(fig, out, "F3_correct_vs_cost")


def f7_hidden_effects(df: pd.DataFrame, out: Path) -> None:
    """Effects that `pass` does not show, per mode, for the matrix and the stress cells."""
    f = faulted(df)
    measures = [("Wrong orders sent (total)", "wrong_sends", "sum"),
                ("Orders sent twice (total)", "duplicate_sends", "sum"),
                ("Tainted posts left live (per run)", "tainted_live_posts", "mean"),
                ("Calls redoing valid agents (per run)", "wasted_calls", "mean")]
    sets = [("Matrix", f[f["fault_set"] == "base"]), ("Stress cells", f[f["fault_set"] == "stress"])]
    sets = [(t, g) for t, g in sets if not g.empty]
    fig, axes = plt.subplots(len(sets), len(measures), figsize=(9.6, 2.0 * len(sets) + 0.6), squeeze=False)
    for r, (set_name, g) in enumerate(sets):
        for c, (title, col, how) in enumerate(measures):
            ax = axes[r][c]
            modes = [m for m in ("M0", "M1", "M2", "M3") if not (col in ("duplicate_sends", "wasted_calls")
                                                                 and m not in ("M1", "M2"))]
            vals = [getattr(g[g["mode"] == m][col], how)() for m in modes]
            bars = ax.bar(modes, vals, color=[MODE_COLOR[m] for m in modes], width=0.6,
                          edgecolor=SURFACE, linewidth=2)
            for b, v in zip(bars, vals):
                ax.text(b.get_x() + b.get_width() / 2, b.get_height(), f"{v:.1f}" if how == "mean" else f"{v:.0f}",
                        ha="center", va="bottom", fontsize=8, color=INK)
            ax.set_yticks([])
            ax.spines["left"].set_visible(False)
            ax.set_ylim(0, max(vals + [1]) * 1.25)
            if r == 0:
                ax.set_title(title, fontsize=8.5, loc="left")
            if c == 0:
                ax.set_ylabel(set_name, fontsize=9, color=INK)
    fig.suptitle("F7  What the oracle's pass does not show", x=0.02, ha="left", fontsize=10, fontweight="bold")
    fig.text(0.02, -0.03, "Sent orders cannot be undone. Duplicate orders and wasted calls exist only "
             "for M1 and M2, which rerun all five agents.", fontsize=7.5, color=INK2)
    fig.tight_layout()
    save(fig, out, "F7_hidden_effects")


def trace_points(events: list[dict], phase: str, F: set[str], tainted: set[str]) -> list[tuple]:
    """Marks in time order. In the faulted run, an agent's writes after it read F count as built on F."""
    points, readers = [], set()
    for e in (e for e in events if e["phase"] == phase):
        if e["type"] == "board_search" and (F | tainted) & set(e["returned_post_ids"]) and phase == "main":
            readers.add(e["invocation"])
        t, agent = e["type"], e.get("agent")
        if agent not in AGENTS or t not in ("board_add", "board_search", "read_file", "file_read",
                                            "file_write", "external_send"):
            continue
        color = NEUTRAL
        if t == "board_add":
            color = FAULTY if e["post_id"] in F else TAINTED if e["post_id"] in tainted else NEUTRAL
        elif t == "board_search":
            got = set(e["returned_post_ids"])
            color = FAULTY if got & F else TAINTED if got & tainted else NEUTRAL
        elif t in ("file_write", "external_send") and e.get("invocation") in readers:
            color = TAINTED
        points.append((len(points), agent, t, color))
    return points


def f4_trace(runs: Path, out: Path, run_id: str) -> None:
    """One task, faulted run and its M1 rerun: what each agent did, and when it touched the faulty post."""
    src, rec = runs / run_id, runs / f"{run_id}__recovered_M1"
    F = set(json.loads((src / "manifest.json").read_text())["F"])
    main = read_events(src / "events.jsonl")
    tainted, readers = set(), set()
    for e in main:
        if e["type"] == "board_search" and (F | tainted) & set(e["returned_post_ids"]):
            readers.add(e["invocation"])
        elif e["type"] == "board_add" and e["invocation"] in readers:
            tainted.add(e["post_id"])
    panels = [("Faulted run (M0)", main, "main")]
    if (rec / "events_recovery.jsonl").exists():
        panels.append(("M1 rerun on the kept board", read_events(rec / "events_recovery.jsonl"), "recovery"))
    marks = {"board_add": ("s", "post to board"), "board_search": ("o", "search board"),
             "file_read": (".", "read file"), "file_write": ("^", "write file"), "external_send": ("*", "send order")}
    fig, axes = plt.subplots(len(panels), 1, figsize=(8.4, 1.7 * len(panels) + 0.6), squeeze=False)
    for ax, (title, events, phase) in zip([a[0] for a in axes], panels):
        for x, agent, t, color in trace_points(events, phase, F, tainted - F):
            ax.scatter(x, AGENTS.index(agent), marker=marks[t][0], s={"file_read": 40, "external_send": 150}.get(t, 70),
                       color=color, edgecolor=SURFACE, linewidth=1.5, zorder=3)
        ax.set_yticks(range(len(AGENTS)), AGENTS)
        ax.invert_yaxis()
        ax.set_xticks([])
        ax.spines["bottom"].set_visible(False)
        for i in range(len(AGENTS)):
            ax.axhline(i, color=GRID, lw=0.8, zorder=1)
        ax.set_title(title, loc="left", fontsize=9)
    handles = [plt.Line2D([], [], marker=m, color=INK2, lw=0, markersize=7, label=l) for m, l in marks.values()]
    handles += [plt.Line2D([], [], marker="s", color=c, lw=0, markersize=7, label=l)
                for c, l in ((FAULTY, "the faulty post, or a search that returned it"),
                             (TAINTED, "work built on it"), (NEUTRAL, "untouched"))]
    fig.legend(handles=handles, loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.12), fontsize=7.5)
    fig.suptitle(f"F4  Example trace: {run_id.split('__')[0]}, wrong claim FA1, rep 0",
                 x=0.02, ha="left", fontsize=10, fontweight="bold")
    fig.text(0.02, -0.2, "Time runs left to right, one mark per action. In the M1 rerun, agents still retrieve "
             "the faulty post, and follow the newer, correct diagnosis (E25).", fontsize=7.5, color=INK2)
    fig.tight_layout()
    save(fig, out, "F4_example_trace")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-csv", type=Path, default=ROOT / "results/phase1_tables/runs.csv")
    parser.add_argument("--runs", type=Path, default=ROOT / "runs/main")
    parser.add_argument("--out", type=Path, default=ROOT / "results/phase1_figures")
    parser.add_argument("--trace-run", default="T03__FA1xA1__M0__observe__r0")
    args = parser.parse_args()
    df = pd.read_csv(args.runs_csv)
    if "fault_set" not in df:
        df["fault_set"] = "base"
    args.out.mkdir(parents=True, exist_ok=True)
    f1_propagation(df, args.out)
    f2_funnel(df, args.out)
    f3_correct_vs_cost(df, args.out)
    f7_hidden_effects(df, args.out)
    if (args.runs / args.trace_run).exists():
        f4_trace(args.runs, args.out, args.trace_run)
    print(f"wrote figures to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
