#!/usr/bin/env python3
"""Render publication-style static figures from the production-regime DQMC benchmark report.

Reads the normalized DATA JSON of the interactive report and produces:
  1. FigS-production-benchmark.pdf      -- stacked mirrored version (manuscript column):
        (a) update time per sweep vs L for all five implementations;
        (b) total sweep time per sweep vs L for all five implementations, on the
            identical y range so that the update dominance is directly visible;
        insets give each delayed-update implementation's speedup over the fast update.
  2. FigR-production-benchmark-wide.pdf -- side-by-side mirrored version (response letter).
  3. FigR-speedup-stage-shares.pdf      -- argument figure (response letter):
        (a) speedup of the submatrix-T update over the fast update vs L, at the
            update-time and the total-sweep-time accounting levels;
        (b) stage-time shares of one production sweep for the fast update and the
            submatrix-T update at representative sizes.
  4. FigR-delayT-comparison.pdf         -- direct comparison figure (response letter):
        (a) update and total-sweep times of the delay-T and submatrix-T updates vs L;
        (b) direct time ratio, delay-T over submatrix-T, at both accounting levels.

Points with kind != "measured" (extrapolated/estimated) are drawn with open markers and a
dotted extension from the last measured point, and are reported in the log.

Usage:
  make_benchmark_figures.py <report-data.json> <out-stacked.pdf> <out-wide.pdf> <out-sharp.pdf> <out-delayt.pdf>
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter, NullFormatter, NullLocator, ScalarFormatter
import numpy as np

# ---------------------------------------------------------------- style ----
plt.rcParams.update({
    "font.size": 19,
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial"],
    "xtick.direction": "in",
    "ytick.direction": "in",
    "xtick.top": True,
    "ytick.right": True,
    "savefig.bbox": "tight",
    "mathtext.fontset": "custom",
    "mathtext.rm": "Arial",
    "mathtext.it": "DejaVu Sans:italic",
    "mathtext.bf": "Arial",
})

REFERENCE_WIDTH = 7.0
COLUMN_WIDTH = 3.4
STYLE_SCALE = COLUMN_WIDTH / REFERENCE_WIDTH
FONT_SIZE = 19 * STYLE_SCALE
LINE_WIDTH = 1.0 * STYLE_SCALE
MARKER_SIZE = 8.0 * STYLE_SCALE
INSET_LINE_WIDTH = 0.8 * STYLE_SCALE
INSET_MARKER_SIZE = 6.0 * STYLE_SCALE
LEGEND_SIZE = 18 * STYLE_SCALE
INSET_FONT_SIZE = 16 * STYLE_SCALE

plt.rcParams.update({
    "font.size": FONT_SIZE,
    "axes.linewidth": 0.8 * STYLE_SCALE,
    "grid.linewidth": 0.8 * STYLE_SCALE,
    "xtick.major.width": 0.8 * STYLE_SCALE,
    "xtick.minor.width": 0.6 * STYLE_SCALE,
    "ytick.major.width": 0.8 * STYLE_SCALE,
    "ytick.minor.width": 0.6 * STYLE_SCALE,
})

ALGO_LABEL = {"fast": "Fast", "delayg": "Delay-G", "subg": "Submatrix-G",
              "delaylr": "Delay-T", "sublr": "Submatrix-T"}
ALGO_COLOR = {"fast": "black", "delayg": "orange", "subg": "red",
              "delaylr": "green", "sublr": "blue"}
ALGO_MARKER = {"fast": "s", "delayg": "D", "subg": "o", "delaylr": "v", "sublr": "^"}
ALGOS = ("fast", "delayg", "subg", "delaylr", "sublr")

STAGE_ORDER = ["update", "propagation", "stabilization", "measurement", "other"]
STAGE_LABEL = {"update": "Update", "propagation": "Propagation",
               "stabilization": "Stabilization", "measurement": "Measurement",
               "other": "I/O and remainder"}
STAGE_COLOR = {"update": "#0072B2", "propagation": "#E69F00",
               "stabilization": "#009E73", "measurement": "#D62728",
               "other": "#999999"}
STAGE_TEXT_DARK = {"propagation", "other"}  # light fills take dark text

L_TICKS = list(range(6, 73, 6))


def load_data(data_path):
    return json.loads(Path(data_path).read_text())


def series(data, algo, field):
    """Median/min/max of `field` vs L, split into measured and extrapolated points."""
    meas, extra = [], []
    for p in data["points"]:
        if p["algorithm"] != algo or p[field] is None:
            continue
        row = (p["L"], p[field], p[field + "_min"], p[field + "_max"])
        (meas if p.get("kind", "measured") == "measured" else extra).append(row)
    meas.sort()
    extra.sort()
    return np.array(meas).T if meas else (np.array([]),) * 4, \
           np.array(extra).T if extra else (np.array([]),) * 4


def measured_medians(data, algo, field):
    return {p["L"]: p[field] for p in data["points"]
            if p["algorithm"] == algo and p[field] is not None
            and p.get("kind", "measured") == "measured"}


def speedup_over_fast(data, field):
    """Ratios fast/algo, split into measured and estimated fast-update points."""
    fast_measured, fast_estimated = {}, {}
    for point in data["points"]:
        if point["algorithm"] != "fast" or point[field] is None:
            continue
        target = fast_measured if point.get("kind", "measured") == "measured" else fast_estimated
        target[point["L"]] = point[field]
    curves = {}
    for algo in ("delayg", "subg", "delaylr", "sublr"):
        med = measured_medians(data, algo, field)
        measured_L = sorted(set(fast_measured) & set(med))
        estimated_L = sorted(set(fast_estimated) & set(med))
        measured = np.array([(L, fast_measured[L] / med[L]) for L in measured_L]).T
        estimated = np.array([(L, fast_estimated[L] / med[L]) for L in estimated_L]).T
        curves[algo] = (
            measured if measured_L else np.empty((2, 0)),
            estimated if estimated_L else np.empty((2, 0)),
        )
    return curves


def draw_measured(ax, L, med, lo, hi, color, marker, ls, filled=True, zorder=3):
    ax.errorbar(L, med, yerr=[med - lo, hi - med], fmt=ls + marker, color=color,
                mfc=color if filled else "none", mec=color, markeredgewidth=STYLE_SCALE,
                ms=MARKER_SIZE, lw=LINE_WIDTH, elinewidth=STYLE_SCALE,
                capsize=2.5 * STYLE_SCALE,
                zorder=zorder)


def draw_extrapolated(ax, last_meas, extra, color, marker, ls=":"):
    """Extrapolated points: open markers, dotted link from the last measured point."""
    L, med, lo, hi = extra
    if len(L) == 0:
        return
    if last_meas is not None:
        ax.plot([last_meas[0], L[0]], [last_meas[1], med[0]], ls=ls,
                color=color, marker=None, lw=LINE_WIDTH, zorder=2)
    ax.errorbar(L, med, yerr=[med - lo, hi - med], fmt=ls + marker, color=color,
                mfc="none", mec=color, markeredgewidth=STYLE_SCALE, ms=MARKER_SIZE,
                lw=LINE_WIDTH, elinewidth=STYLE_SCALE, capsize=2.5 * STYLE_SCALE,
                zorder=2)


def plain_log_tick(value, _position):
    if value <= 0:
        return ""
    exponent = int(round(np.log10(value)))
    if not np.isclose(value, 10.0 ** exponent):
        return ""
    return rf"$10^{{{exponent}}}$"


def style_axes(ax):
    ax.grid(True, alpha=0.3)
    ax.tick_params(which="both", direction="in", top=True, right=True)


def setup_log_ax(ax, ylabel):
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xticks([6, 12, 24, 36, 48, 60, 72])
    ax.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax.xaxis.set_minor_locator(NullLocator())
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.yaxis.set_major_formatter(FuncFormatter(plain_log_tick))
    ax.set_xlim(5, 88)
    ax.set_xlabel(r"Linear system size $L$")
    ax.set_ylabel(ylabel)
    style_axes(ax)


def setup_benchmark_log_ax(ax, ylabel):
    ax.set_xscale("linear")
    ax.set_yscale("log")
    ax.set_xticks(L_TICKS)
    ax.set_xticklabels([str(L) for L in L_TICKS])
    ax.xaxis.set_minor_locator(NullLocator())
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.yaxis.set_major_formatter(FuncFormatter(plain_log_tick))
    ax.set_xlim(4, 74)
    ax.set_xlabel(r"Linear system size $L$")
    ax.set_ylabel(ylabel)
    style_axes(ax)


def fast_cost_note(L, seconds):
    days = seconds / 86400.0
    if days >= 2:
        return rf"fast, $L$={L}:" + "\n" + f"≈{days:.1f} days"
    hours = seconds / 3600.0
    return rf"fast, $L$={L}:" + "\n" + f"≈{hours:.0f} h"


# ------------------------------------------- mirrored absolute-time panel ----
def panel_abs_times(fig, ax, data, field, ylabel, ylim, days_note=False):
    """Absolute times of all five implementations + inset speedup over fast."""
    for algo in ALGOS:
        meas, extra = series(data, algo, field)
        last = None
        if len(meas[0]):
            draw_measured(ax, *meas, ALGO_COLOR[algo], ALGO_MARKER[algo], "-")
            last = meas[:, -1]
        draw_extrapolated(ax, last, extra, ALGO_COLOR[algo], ALGO_MARKER[algo])
    setup_benchmark_log_ax(ax, ylabel)
    ax.set_ylim(ylim)

    # inset: speedup of each delayed-update implementation over the fast update
    bounds = ax.get_position()
    axins = fig.add_axes([
        bounds.x0 + 0.11 * bounds.width,
        bounds.y0 + 0.545 * bounds.height,
        0.387 * bounds.width,
        0.39 * bounds.height,
    ])
    axins.set_zorder(5)
    axins.patch.set_facecolor("white")
    for algo, (measured, estimated) in speedup_over_fast(data, field).items():
        if measured.shape[1]:
            axins.plot(measured[0], measured[1], "-" + ALGO_MARKER[algo],
                       color=ALGO_COLOR[algo], lw=INSET_LINE_WIDTH,
                       ms=INSET_MARKER_SIZE)
        if estimated.shape[1]:
            if measured.shape[1]:
                axins.plot([measured[0, -1], estimated[0, 0]],
                           [measured[1, -1], estimated[1, 0]], ":",
                           color=ALGO_COLOR[algo], lw=INSET_LINE_WIDTH)
            axins.plot(estimated[0], estimated[1], ":" + ALGO_MARKER[algo],
                       color=ALGO_COLOR[algo], mfc="none", mec=ALGO_COLOR[algo],
                       mew=STYLE_SCALE, lw=INSET_LINE_WIDTH, ms=INSET_MARKER_SIZE)
    axins.set_yscale("log")
    axins.set_ylim(0.8, 600)
    axins.set_yticks([1, 10, 100])
    axins.yaxis.set_major_formatter(ScalarFormatter())
    axins.set_xlim(4, 74)
    axins.set_xticks(L_TICKS[::2])
    axins.set_xlabel(r"$L$", fontsize=INSET_FONT_SIZE)
    axins.set_ylabel("Speedup", fontsize=INSET_FONT_SIZE)
    axins.grid(True, alpha=0.3)
    axins.tick_params(which="both", direction="in", top=True, right=True,
                      labelsize=INSET_FONT_SIZE)

    handles = [Line2D([], [], color=ALGO_COLOR[a], marker=ALGO_MARKER[a],
                      mfc=ALGO_COLOR[a], ls="-", lw=LINE_WIDTH,
                      ms=MARKER_SIZE, label=ALGO_LABEL[a]) for a in ALGOS]
    ax.legend(handles=handles, fontsize=LEGEND_SIZE, loc="lower right")

    if days_note:
        meas, _ = series(data, "fast", "sweep_seconds")
        L, med = meas[0], meas[1]
        i = int(np.argmax(L))
        ax.annotate(fast_cost_note(int(L[i]), med[i]),
                    xy=(L[i] * 0.95, med[i] * 1.2), xytext=(43, 2.0e6),
                    fontsize=15 * STYLE_SCALE, va="center", ha="left",
                    arrowprops=dict(arrowstyle="-", lw=0.8 * STYLE_SCALE, color="0.35",
                                    connectionstyle="arc3,rad=-0.1"), color="0.2")


def shared_ylim(data):
    """One y range covering both accounting levels, for the mirrored panels."""
    lo, hi = np.inf, 0.0
    for algo in ALGOS:
        for field in ("update_seconds", "sweep_seconds"):
            meas, extra = series(data, algo, field)
            for arr in (meas, extra):
                if len(arr[0]):
                    lo = min(lo, arr[1].min())
                    hi = max(hi, arr[1].max())
    return lo * 0.45, hi * 12.0


def fig_benchmark_mirrored(data, out_path, orientation):
    ylim = shared_ylim(data)
    if orientation == "stacked":
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(COLUMN_WIDTH, 12 * STYLE_SCALE))
        fig.subplots_adjust(hspace=0.42)
    else:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(6.9, 6 * STYLE_SCALE))
        fig.subplots_adjust(wspace=0.30)
    panel_abs_times(fig, ax1, data, "update_seconds", "Update time per sweep (s)", ylim)
    panel_abs_times(fig, ax2, data, "sweep_seconds", "Total sweep time (s)", ylim,
                    days_note=True)
    for ax, tag in ((ax1, "(a)"), (ax2, "(b)")):
        ax.set_title(tag, loc="left", fontsize=FONT_SIZE, fontweight="normal", pad=3)
    fig.savefig(out_path)
    plt.close(fig)
    print("wrote", out_path)


# ------------------------------------------------- stage shares (on an ax) ----
def draw_stage_shares(ax, data, sizes=(24, 36, 54, 60)):
    rows = []  # top to bottom
    for L in reversed(sizes):
        for algo in ("sublr", "fast"):
            p = next(p for p in data["points"]
                     if p["algorithm"] == algo and p["L"] == L)
            share = [100.0 * p["stages"][s] / p["stage_total_seconds"] for s in STAGE_ORDER]
            rows.append((L, algo, share))

    ypos = []
    y = 0.0
    for i, (L, algo, _) in enumerate(rows):
        ypos.append(y)
        y += 1.0 + (0.45 if i % 2 == 1 else 0.0)
    ypos = np.array(ypos)[::-1]
    for y, (L, algo, share) in zip(ypos, rows):
        left = 0.0
        for si, s in enumerate(STAGE_ORDER):
            ax.barh(y, share[si], 0.62, left=left, color=STAGE_COLOR[s],
                    edgecolor="white", linewidth=0.4 * STYLE_SCALE, zorder=3)
            if share[si] >= 6:
                tcolor = "0.15" if s in STAGE_TEXT_DARK else "white"
                label = "≥99" if share[si] >= 99.5 else f"{share[si]:.0f}"
                ax.text(left + share[si] / 2, y, label,
                        ha="center", va="center", fontsize=13 * STYLE_SCALE,
                        color=tcolor, zorder=4)
            left += share[si]
        ax.text(2.0, y, "fast" if algo == "fast" else "submatrix-T",
                ha="left", va="center", fontsize=13 * STYLE_SCALE,
                color="white", zorder=5)

    ax.set_yticks(ypos)
    ax.set_yticklabels([rf"$L$={L}" if a == "fast" else "" for (L, a, _) in rows],
                       fontsize=14 * STYLE_SCALE)
    ax.set_xlim(0, 100)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xlabel("Share of total sweep time (%)")
    ax.tick_params(axis="y", length=0)
    ax.set_axisbelow(True)
    style_axes(ax)
    handles = [plt.Rectangle((0, 0), 1, 1, fc=STAGE_COLOR[s], ec="white",
                             lw=0.4 * STYLE_SCALE,
                             label=STAGE_LABEL[s]) for s in STAGE_ORDER]
    ax.legend(handles=handles, loc="lower left", bbox_to_anchor=(-0.02, 1.16),
              ncol=3, columnspacing=0.8, handletextpad=0.35,
              borderaxespad=0.0, fontsize=13 * STYLE_SCALE)


# ------------------------------------------------- argument figure (sharp) ----
def fig_sharp(data, out_path):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(6.9, 5.8 * STYLE_SCALE),
                                   gridspec_kw={"width_ratios": [1, 1.15]})
    fig.subplots_adjust(wspace=0.30)

    # (a) speedup of submatrix-T over fast at both accounting levels
    fast_s = measured_medians(data, "fast", "sweep_seconds")
    fast_u = measured_medians(data, "fast", "update_seconds")
    sub_s = measured_medians(data, "sublr", "sweep_seconds")
    sub_u = measured_medians(data, "sublr", "update_seconds")
    common = sorted(set(fast_s) & set(sub_s) & set(fast_u) & set(sub_u))
    L = np.array(common, dtype=float)
    r_sweep = np.array([fast_s[l] / sub_s[l] for l in common])
    r_update = np.array([fast_u[l] / sub_u[l] for l in common])
    marker = ALGO_MARKER["sublr"]
    ax1.plot(L, r_sweep, "-" + marker, color=ALGO_COLOR["sublr"],
             ms=MARKER_SIZE, lw=LINE_WIDTH, zorder=3)
    ax1.plot(L, r_update, "--" + marker, color=ALGO_COLOR["sublr"], mfc="none",
             mec=ALGO_COLOR["sublr"], mew=STYLE_SCALE, ms=MARKER_SIZE,
             lw=LINE_WIDTH, zorder=3)
    setup_log_ax(ax1, "Speedup over fast update")
    ax1.set_xlim(5, 115)
    ax1.set_xticks([6, 12, 24, 48, 96])
    ax1.set_yticks([1, 3, 10, 30, 100, 300])
    ax1.get_yaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax1.set_ylim(1, 400)
    handles = [
        Line2D([], [], color=ALGO_COLOR["sublr"], marker=marker, ls="-",
               lw=LINE_WIDTH, ms=MARKER_SIZE,
               label=rf"Total sweep time ({r_sweep[-1]:.1f}× at $L$={int(L[-1])})"),
        Line2D([], [], color=ALGO_COLOR["sublr"], marker=marker, mfc="none", ls="--",
               lw=LINE_WIDTH, ms=MARKER_SIZE,
               label=rf"Update time ({r_update[-1]:.0f}× at $L$={int(L[-1])})"),
    ]
    ax1.legend(handles=handles, loc="upper left", fontsize=14 * STYLE_SCALE,
               handletextpad=0.4, borderaxespad=0.2, labelspacing=0.3)
    print(f"endpoint speedups at L={int(L[-1])}: update {r_update[-1]:.2f}x, "
          f"sweep {r_sweep[-1]:.2f}x")

    # (b) stage-time shares
    draw_stage_shares(ax2, data)

    for ax, tag in ((ax1, "(a)"), (ax2, "(b)")):
        ax.set_title(tag, loc="left", fontsize=FONT_SIZE, fontweight="normal", pad=3)
    fig.savefig(out_path)
    plt.close(fig)
    print("wrote", out_path)


# --------------------------------------------- delay-T comparison (U12) ----
def fig_delayt_comparison(data, out_path):
    """Submatrix-T vs Delay-T in the production regime: absolute times and direct ratio."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(6.9, 5.4 * STYLE_SCALE),
                                   gridspec_kw={"width_ratios": [1.2, 1]})
    fig.subplots_adjust(wspace=0.32)

    # (a) absolute times at both accounting levels
    for algo in ("delaylr", "sublr"):
        for field, filled, ls in (("update_seconds", False, "--"),
                                  ("sweep_seconds", True, "-")):
            meas, extra = series(data, algo, field)
            last = None
            if len(meas[0]):
                draw_measured(ax1, *meas, ALGO_COLOR[algo], ALGO_MARKER[algo], ls,
                              filled=filled)
                last = meas[:, -1]
            draw_extrapolated(ax1, last, extra, ALGO_COLOR[algo], ALGO_MARKER[algo])
    setup_log_ax(ax1, "Time per sweep (s)")
    handles = [
        Line2D([], [], color=ALGO_COLOR["delaylr"], marker=ALGO_MARKER["delaylr"],
               ms=MARKER_SIZE, lw=LINE_WIDTH, ls="-", label="Delay-T"),
        Line2D([], [], color=ALGO_COLOR["sublr"], marker=ALGO_MARKER["sublr"],
               ms=MARKER_SIZE, lw=LINE_WIDTH, ls="-", label="Submatrix-T"),
        Line2D([], [], color="0.35", marker="o", ms=MARKER_SIZE,
               lw=LINE_WIDTH, ls="-", label="Total sweep time"),
        Line2D([], [], color="0.35", marker="o", mfc="none", ms=MARKER_SIZE,
               lw=LINE_WIDTH, ls="--", label="Update time"),
    ]
    ax1.legend(handles=handles, loc="upper left", fontsize=14 * STYLE_SCALE,
               handletextpad=0.4, borderaxespad=0.2, labelspacing=0.25)

    # (b) direct ratio, delay-T over submatrix-T, at both accounting levels
    for field, filled, ls, lab in (("update_seconds", False, "--", "Update time"),
                                   ("sweep_seconds", True, "-", "Total sweep time")):
        d = measured_medians(data, "delaylr", field)
        s = measured_medians(data, "sublr", field)
        common = sorted(set(d) & set(s))
        r = np.array([(L, d[L] / s[L]) for L in common]).T
        ax2.plot(r[0], r[1], ls + "o", color="0.15",
                 mfc="0.15" if filled else "none", mec="0.15", mew=STYLE_SCALE,
                 ms=MARKER_SIZE, lw=LINE_WIDTH, zorder=3,
                 label=rf"{lab} ({r[1][-1]:.2f}× at $L$={int(r[0][-1])})")
    ax2.axhline(1.0, color="0.5", lw=0.7 * STYLE_SCALE, zorder=1)
    ax2.annotate("equal time", xy=(36, 1.0), xytext=(36, 0.965),
                 fontsize=14 * STYLE_SCALE,
                 color="0.4", va="top", ha="center")
    ax2.set_xscale("log")
    ax2.set_xticks([6, 12, 24, 36, 48, 60, 72])
    ax2.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax2.xaxis.set_minor_locator(NullLocator())
    ax2.xaxis.set_minor_formatter(NullFormatter())
    ax2.set_xlim(5, 88)
    ax2.set_xlabel(r"Linear system size $L$")
    ax2.set_ylabel(r"Time ratio, delay-T / submatrix-T")
    ax2.set_ylim(0.8, 1.8)
    ax2.set_yticks([0.8, 1.0, 1.2, 1.4, 1.6])
    style_axes(ax2)
    ax2.legend(loc="upper left", handletextpad=0.4,
               borderaxespad=0.2, labelspacing=0.3, fontsize=14 * STYLE_SCALE)

    for ax, tag in ((ax1, "(a)"), (ax2, "(b)")):
        ax.set_title(tag, loc="left", fontsize=FONT_SIZE, fontweight="normal", pad=3)
    fig.savefig(out_path)
    plt.close(fig)
    print("wrote", out_path)


# -------------------------------------------------------------- drivers ----
def main():
    data_path, out_stacked, out_wide, out_sharp, out_delayt = sys.argv[1:6]
    data = load_data(data_path)
    print("report generated_at:", data["generated_at"])
    kinds = {(p["algorithm"], p["L"], p.get("kind", "measured"))
             for p in data["points"] if p.get("kind", "measured") != "measured"}
    if kinds:
        print("NOTE: non-measured points present:", sorted(kinds))
    else:
        print("all benchmark points are measured")
    fig_benchmark_mirrored(data, out_stacked, "stacked")
    fig_benchmark_mirrored(data, out_wide, "wide")
    fig_sharp(data, out_sharp)
    fig_delayt_comparison(data, out_delayt)


if __name__ == "__main__":
    main()
