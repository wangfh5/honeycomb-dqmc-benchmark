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
from matplotlib.ticker import NullFormatter, NullLocator, ScalarFormatter
import numpy as np

# ---------------------------------------------------------------- style ----
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 7.0,
    "axes.linewidth": 0.6,
    "axes.labelsize": 7.5,
    "xtick.labelsize": 6.5,
    "ytick.labelsize": 6.5,
    "legend.fontsize": 6.0,
    "lines.linewidth": 1.0,
    "lines.markersize": 3.2,
    "errorbar.capsize": 1.6,
    "savefig.bbox": "tight",
})

BENCHMARK_STYLE = {
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Liberation Sans", "DejaVu Sans"],
    "font.size": 9.0,
    "axes.linewidth": 0.8,
    "axes.labelsize": 9.5,
    "xtick.labelsize": 8.0,
    "ytick.labelsize": 8.0,
    "xtick.direction": "in",
    "ytick.direction": "in",
    "xtick.top": True,
    "ytick.right": True,
    "legend.fontsize": 7.5,
    "lines.linewidth": 1.15,
    "lines.markersize": 4.2,
    "errorbar.capsize": 2.0,
}

ALGO_LABEL = {"fast": "Fast", "delayg": "Delay-G", "subg": "Submatrix-G",
              "delaylr": "Delay-T", "sublr": "Submatrix-T"}
ALGO_COLOR = {"fast": "#000000", "delayg": "#E69F00", "subg": "#D62728",
              "delaylr": "#009E73", "sublr": "#0072B2"}
ALGO_MARKER = {"fast": "o", "delayg": "s", "subg": "D", "delaylr": "^", "sublr": "v"}
ALGOS = ("fast", "delayg", "subg", "delaylr", "sublr")

STAGE_ORDER = ["update", "propagation", "stabilization", "measurement", "other"]
STAGE_LABEL = {"update": "Update", "propagation": "Propagation",
               "stabilization": "Stabilization", "measurement": "Measurement",
               "other": "I/O and remainder"}
STAGE_COLOR = {"update": "#0072B2", "propagation": "#E69F00",
               "stabilization": "#009E73", "measurement": "#D62728",
               "other": "#999999"}
STAGE_TEXT_DARK = {"propagation", "other"}  # light fills take dark text

L_TICKS = [6, 12, 24, 36, 48, 60, 72]


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
    """Ratio fast/algo at fast's measured sizes, for the four delayed-update algorithms."""
    fast = measured_medians(data, "fast", field)
    curves = {}
    for algo in ("delayg", "subg", "delaylr", "sublr"):
        med = measured_medians(data, algo, field)
        common = sorted(set(fast) & set(med))
        if common:
            curves[algo] = np.array([(L, fast[L] / med[L]) for L in common]).T
    return curves


def draw_measured(ax, L, med, lo, hi, color, marker, ls, filled=True, zorder=3):
    ax.errorbar(L, med, yerr=[med - lo, hi - med], fmt=ls + marker, color=color,
                mfc=color if filled else "none", mec=color, markeredgewidth=0.8,
                elinewidth=0.6, zorder=zorder)


def draw_extrapolated(ax, last_meas, extra, color, marker, ls=":"):
    """Extrapolated points: open markers, dotted link from the last measured point."""
    L, med, lo, hi = extra
    if len(L) == 0:
        return
    if last_meas is not None:
        ax.plot([last_meas[0], L[0]], [last_meas[1], med[0]], ls=ls,
                color=color, marker=None, zorder=2)
    ax.errorbar(L, med, yerr=[med - lo, hi - med], fmt=ls + marker, color=color,
                mfc="none", mec=color, markeredgewidth=0.8, elinewidth=0.6, zorder=2)


def setup_log_ax(ax, ylabel):
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xticks(L_TICKS)
    ax.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax.minorticks_off()
    ax.set_xlim(5, 88)
    ax.set_xlabel(r"Linear system size $L$")
    ax.set_ylabel(ylabel)


def disable_minor_ticks(ax):
    for axis in (ax.xaxis, ax.yaxis):
        axis.set_minor_locator(NullLocator())
        axis.set_minor_formatter(NullFormatter())


def setup_benchmark_log_ax(ax, data, ylabel):
    ax.set_xscale("log")
    ax.set_yscale("log")
    ticks = sorted({int(L) for L in data["l_values"]})
    labels = [str(L) if index % 2 == 0 else "" for index, L in enumerate(ticks)]
    ax.set_xticks(ticks)
    ax.set_xticklabels(labels)
    disable_minor_ticks(ax)
    ax.set_xlim(min(ticks) * 0.9, max(ticks) * 1.08)
    ax.set_xlabel(r"Linear system size $L$")
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.3)
    ax.tick_params(which="both", direction="in", top=True, right=True)


def fast_cost_note(L, seconds):
    days = seconds / 86400.0
    if days >= 2:
        return rf"fast, $L={L}$:" + "\n" + rf"$\approx\!{days:.1f}$ days"
    hours = seconds / 3600.0
    return rf"fast, $L={L}$:" + "\n" + rf"$\approx\!{hours:.0f}$ h"


# ------------------------------------------- mirrored absolute-time panel ----
def panel_abs_times(fig, ax, data, field, ylabel, ylim, days_note=False):
    """Absolute times of all five implementations + inset speedup over fast."""
    is_update = field == "update_seconds"
    measured_style = "--" if is_update else "-"
    measured_filled = not is_update
    for algo in ALGOS:
        meas, extra = series(data, algo, field)
        last = None
        if len(meas[0]):
            draw_measured(ax, *meas, ALGO_COLOR[algo], ALGO_MARKER[algo], measured_style,
                          filled=measured_filled)
            last = meas[:, -1]
        draw_extrapolated(ax, last, extra, ALGO_COLOR[algo], ALGO_MARKER[algo])
    setup_benchmark_log_ax(ax, data, ylabel)
    ax.set_ylim(ylim)

    # inset: speedup of each delayed-update implementation over the fast update
    bounds = ax.get_position()
    axins = fig.add_axes([
        bounds.x0 + 0.10 * bounds.width,
        bounds.y0 + 0.56 * bounds.height,
        0.38 * bounds.width,
        0.34 * bounds.height,
    ])
    axins.set_zorder(5)
    axins.patch.set_facecolor("white")
    for algo, curve in speedup_over_fast(data, field).items():
        axins.plot(curve[0], curve[1], "-" + ALGO_MARKER[algo],
                   color=ALGO_COLOR[algo], ms=3.0, lw=0.9)
    axins.set_yscale("log")
    axins.set_ylim(0.8, 400)
    axins.set_yticks([1, 10, 100])
    axins.yaxis.set_major_formatter(ScalarFormatter())
    axins.set_xlim(5, 70)
    axins.set_xticks([12, 36, 60])
    disable_minor_ticks(axins)
    axins.tick_params(which="both", direction="in", top=True, right=True,
                      labelsize=6.2, length=2.0)
    axins.set_xlabel(r"$L$", fontsize=6.5, labelpad=0.8)
    axins.grid(True, alpha=0.3)
    for side in ("top", "right", "bottom", "left"):
        axins.spines[side].set_linewidth(0.65)

    handles = [Line2D([], [], color=ALGO_COLOR[a], marker=ALGO_MARKER[a],
                      mfc=ALGO_COLOR[a] if measured_filled else "none", ls=measured_style,
                      label=ALGO_LABEL[a]) for a in ALGOS]
    ax.legend(handles=handles, loc="lower right", frameon=False,
              handletextpad=0.4, borderaxespad=0.2, labelspacing=0.25)

    if days_note:
        meas, _ = series(data, "fast", "sweep_seconds")
        L, med = meas[0], meas[1]
        i = int(np.argmax(L))
        ax.annotate(fast_cost_note(int(L[i]), med[i]),
                    xy=(L[i] * 0.95, med[i] * 1.2), xytext=(26, 1.6e6),
                    fontsize=6.0, va="center", ha="left",
                    arrowprops=dict(arrowstyle="-", lw=0.5, color="0.35",
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
    with plt.rc_context(BENCHMARK_STYLE):
        ylim = shared_ylim(data)
        if orientation == "stacked":
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(3.4, 5.3))
            fig.subplots_adjust(hspace=0.42)
        else:
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(6.9, 2.9))
            fig.subplots_adjust(wspace=0.30)
        panel_abs_times(fig, ax1, data, "update_seconds", "Update time per sweep (s)", ylim)
        panel_abs_times(fig, ax2, data, "sweep_seconds", "Total sweep time (s)", ylim,
                        days_note=True)
        for ax, tag in ((ax1, "(a)"), (ax2, "(b)")):
            ax.set_title(tag, loc="left", fontsize=10, fontweight="bold", pad=3)
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
                    edgecolor="white", linewidth=0.4, zorder=3)
            if share[si] >= 6:
                tcolor = "0.15" if s in STAGE_TEXT_DARK else "white"
                label = r"$\geq\!99$" if share[si] >= 99.5 else f"{share[si]:.0f}"
                ax.text(left + share[si] / 2, y, label,
                        ha="center", va="center", fontsize=5.8, color=tcolor, zorder=4)
            left += share[si]
        ax.text(2.0, y, "fast" if algo == "fast" else "submatrix-T",
                ha="left", va="center", fontsize=5.6, color="white", zorder=5)

    ax.set_yticks(ypos)
    ax.set_yticklabels([rf"$L={L}$" if a == "fast" else "" for (L, a, _) in rows],
                       fontsize=6.0)
    ax.set_xlim(0, 100)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xlabel("Share of total sweep time (%)")
    ax.tick_params(axis="y", length=0)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    handles = [plt.Rectangle((0, 0), 1, 1, fc=STAGE_COLOR[s], ec="white", lw=0.4,
                             label=STAGE_LABEL[s]) for s in STAGE_ORDER]
    ax.legend(handles=handles, loc="lower left", bbox_to_anchor=(-0.02, 1.16),
              frameon=False, ncol=3, columnspacing=0.8, handletextpad=0.35,
              borderaxespad=0.0, fontsize=5.9)


# ------------------------------------------------- argument figure (sharp) ----
def fig_sharp(data, out_path):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(6.9, 2.8),
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
    ax1.plot(L, r_sweep, "-v", color=ALGO_COLOR["sublr"], ms=3.0, lw=0.9, zorder=3)
    ax1.plot(L, r_update, "--v", color=ALGO_COLOR["sublr"], mfc="none",
             mec=ALGO_COLOR["sublr"], mew=0.8, ms=3.0, lw=0.9, zorder=3)
    setup_log_ax(ax1, "Speedup over fast update")
    ax1.set_xlim(5, 115)
    ax1.set_xticks([6, 12, 24, 48, 96])
    ax1.set_yticks([1, 3, 10, 30, 100, 300])
    ax1.get_yaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax1.set_ylim(1, 400)
    handles = [
        Line2D([], [], color=ALGO_COLOR["sublr"], marker="v", ls="-",
               label=rf"Total sweep time (${r_sweep[-1]:.1f}\times$ at $L={int(L[-1])}$)"),
        Line2D([], [], color=ALGO_COLOR["sublr"], marker="v", mfc="none", ls="--",
               label=rf"Update time (${r_update[-1]:.0f}\times$ at $L={int(L[-1])}$)"),
    ]
    ax1.legend(handles=handles, loc="upper left", frameon=False,
               handletextpad=0.4, borderaxespad=0.2, labelspacing=0.3)
    print(f"endpoint speedups at L={int(L[-1])}: update {r_update[-1]:.2f}x, "
          f"sweep {r_sweep[-1]:.2f}x")

    # (b) stage-time shares
    draw_stage_shares(ax2, data)

    for ax, tag in ((ax1, "(a)"), (ax2, "(b)")):
        ax.set_title(tag, loc="left", fontsize=8, fontweight="bold", pad=3)
    fig.savefig(out_path)
    print("wrote", out_path)


# --------------------------------------------- delay-T comparison (U12) ----
def fig_delayt_comparison(data, out_path):
    """Submatrix-T vs Delay-T in the production regime: absolute times and direct ratio."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(6.9, 2.6),
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
        Line2D([], [], color=ALGO_COLOR["delaylr"], marker="^", ls="-", label="Delay-T"),
        Line2D([], [], color=ALGO_COLOR["sublr"], marker="v", ls="-", label="Submatrix-T"),
        Line2D([], [], color="0.35", marker="o", ls="-", label="Total sweep time"),
        Line2D([], [], color="0.35", marker="o", mfc="none", ls="--", label="Update time"),
    ]
    ax1.legend(handles=handles, loc="upper left", frameon=False,
               handletextpad=0.4, borderaxespad=0.2, labelspacing=0.25)

    # (b) direct ratio, delay-T over submatrix-T, at both accounting levels
    for field, filled, ls, lab in (("update_seconds", False, "--", "Update time"),
                                   ("sweep_seconds", True, "-", "Total sweep time")):
        d = measured_medians(data, "delaylr", field)
        s = measured_medians(data, "sublr", field)
        common = sorted(set(d) & set(s))
        r = np.array([(L, d[L] / s[L]) for L in common]).T
        ax2.plot(r[0], r[1], ls + "o", color="0.15",
                 mfc="0.15" if filled else "none", mec="0.15", mew=0.8,
                 ms=3.0, lw=0.9, zorder=3,
                 label=rf"{lab} (${r[1][-1]:.2f}\times$ at $L={int(r[0][-1])}$)")
    ax2.axhline(1.0, color="0.5", lw=0.7, zorder=1)
    ax2.annotate("equal time", xy=(36, 1.0), xytext=(36, 0.965), fontsize=5.6,
                 color="0.4", va="top", ha="center")
    ax2.set_xscale("log")
    ax2.set_xticks(L_TICKS)
    ax2.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax2.minorticks_off()
    ax2.set_xlim(5, 88)
    ax2.set_xlabel(r"Linear system size $L$")
    ax2.set_ylabel(r"Time ratio, delay-T / submatrix-T")
    ax2.set_ylim(0.8, 1.8)
    ax2.set_yticks([0.8, 1.0, 1.2, 1.4, 1.6])
    ax2.legend(loc="upper left", frameon=False, handletextpad=0.4,
               borderaxespad=0.2, labelspacing=0.3, fontsize=6.0)

    for ax, tag in ((ax1, "(a)"), (ax2, "(b)")):
        ax.set_title(tag, loc="left", fontsize=8, fontweight="bold", pad=3)
    fig.savefig(out_path)
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
