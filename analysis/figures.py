#!/usr/bin/env python3
"""Draw the figures of the paper.

Input:  results/paper/timeline_by_day.csv, results/paper/suite_history.csv
        (from paper_numbers.py), data/derived/coded_inputs.jsonl
Output: figures/timeline.pdf, figures/suite.pdf

The script draws with pltrs (`pip install pltrs`), the library that the
paper is about. Without pltrs, it uses matplotlib. The two libraries have
the same API.
"""
import csv
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402

try:
    import pltrs.pyplot as plt
    import pltrs.dates as mdates
    LIBRARY = "pltrs"
except ImportError:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    LIBRARY = "matplotlib"

FIGURES = os.path.join(lib.ROOT, "figures")
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e6e5e1"
AGENT = "#8a8984"       # agent work: neutral gray
OTHER = "#2a78d6"       # my other inputs
CORRECTIVE = "#eb6834"  # my corrective inputs
RELEASE = datetime.datetime(2026, 11, 20)

plt.rcParams.update({
    "font.size": 8,
    "axes.titlesize": 8,
    "axes.labelsize": 8,
    "xtick.labelsize": 7.5,
    "ytick.labelsize": 7.5,
    "legend.fontsize": 7.5,
    "axes.edgecolor": INK_2,
    "axes.labelcolor": INK,
    "text.color": INK,
    "xtick.color": INK_2,
    "ytick.color": INK_2,
    "axes.linewidth": 0.6,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": False,
    "pdf.fonttype": 42,
})


def style(ax, title):
    ax.set_title(title, loc="left", color=INK, fontweight="bold", pad=4)
    ax.yaxis.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(length=2.5, width=0.6)
    ax.margins(x=0.01)


def timeline():
    rows = list(csv.DictReader(open(os.path.join(lib.RESULTS, "paper", "timeline_by_day.csv"))))
    days = [datetime.datetime.fromisoformat(r["day"]) for r in rows]
    cost = [float(r["cost_usd"]) for r in rows]
    commits = [int(r["commits"]) for r in rows]
    corrective = [int(r["corrective"]) for r in rows]
    other = [int(r["inputs"]) - int(r["corrective"]) for r in rows]
    fig, axes = plt.subplots(3, 1, figsize=(6.5, 4.5), sharex=True)
    width = 0.72
    axes[0].bar(days, cost, width=width, color=AGENT)
    style(axes[0], "Agent work: cost of the model responses per day (USD at API prices)")
    axes[1].bar(days, commits, width=width, color=AGENT)
    style(axes[1], "Commits per day")
    axes[2].bar(days, other, width=width, color=OTHER, label="Other inputs")
    axes[2].bar(days, corrective, width=width, bottom=other, color=CORRECTIVE, label="Corrective inputs")
    style(axes[2], "My inputs per day")
    axes[2].legend(loc="upper left", frameon=False, ncol=2, borderaxespad=0.2, handlelength=1.2)
    half = datetime.timedelta(hours=12)
    for ax in axes:
        ax.axvspan(RELEASE - half, days[-1] + half, color="#f1f0ec", linewidth=0, zorder=0)
    top = axes[1].get_ylim()[1]
    axes[1].text(RELEASE + datetime.timedelta(days=1.5), top * 0.93, "release",
                 ha="center", va="top", color=INK_2, fontsize=7.5)
    axes[2].xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
    axes[2].xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    axes[2].set_xlim(days[0] - datetime.timedelta(hours=18), days[-1] + half)
    fig.tight_layout(h_pad=1.0)
    fig.savefig(os.path.join(FIGURES, "timeline.pdf"))
    plt.close(fig)


def suite():
    rows = list(csv.DictReader(open(os.path.join(lib.RESULTS, "paper", "suite_history.csv"))))
    t = [datetime.datetime.fromisoformat(r["time"].replace("Z", "+00:00")).replace(tzinfo=None) for r in rows]
    pct = [float(r["percent"]) for r in rows]
    end = datetime.datetime(2026, 11, 2, 12)
    keep = [i for i, x in enumerate(t) if x <= end]
    t, pct = [t[i] for i in keep], [pct[i] for i in keep]
    inputs = [json.loads(l) for l in open(os.path.join(lib.DERIVED, "coded_inputs.jsonl"), encoding="utf-8")]
    it = [datetime.datetime.fromisoformat(r["time"].replace("Z", "+00:00")).replace(tzinfo=None) for r in inputs]
    it = [x for x in it if t[0] - datetime.timedelta(hours=3) <= x <= end]
    fig, ax = plt.subplots(figsize=(6.5, 2.3))
    ax.step(t + [end], pct + [pct[-1]], where="post", color=AGENT, linewidth=1.6)
    ax.plot(t, pct, "o", color=AGENT, markersize=3)
    ax.plot(it, [-7] * len(it), "|", color=OTHER, markersize=7, markeredgewidth=1.4, clip_on=False)
    ax.text(datetime.datetime(2026, 10, 31, 20), -7, "my inputs (one mark each)", color=INK_2,
            fontsize=7.5, ha="center", va="center")
    style(ax, "Tests of the matplotlib suite that pass with pltrs (% of the tests that pass with matplotlib)")
    ax.set_ylim(-18, 104)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.xaxis.set_major_locator(mdates.DayLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    ax.set_xlim(t[0] - datetime.timedelta(hours=3), end)
    ax.annotate("50 of 8,830", (t[0], pct[0]), xytext=(16, 5), textcoords="offset points",
                color=INK_2, fontsize=7.5)
    full = next(i for i, p in enumerate(pct) if p == 100.0)
    ax.annotate("9,427 of 9,427", (t[full], 100), xytext=(-6, -11), textcoords="offset points",
                ha="right", color=INK_2, fontsize=7.5)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGURES, "suite.pdf"))
    plt.close(fig)


def main():
    os.makedirs(FIGURES, exist_ok=True)
    timeline()
    suite()
    print("drawn with", LIBRARY)


if __name__ == "__main__":
    main()
