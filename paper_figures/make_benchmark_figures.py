#!/usr/bin/env python3
"""Render publication-style static figures from the production-regime DQMC benchmark report.

Reads the normalized DATA JSON of the interactive report and produces:
  1. FigS-production-benchmark.pdf      -- stacked mirrored version (manuscript column):
        (a) update time per sweep vs L for all five implementations;
        (b) total sweep time per sweep vs L for all five implementations, on the
            identical y range so that the update dominance is directly visible;
        each panel carries two insets (speedup over Fast; Submatrix-T over the other
        delayed-family updates); a shared legend sits above (a); OMP thread partitions
        are annotated only in the mid-gap strip between (a) and (b).
  2. FigR-production-benchmark-wide.pdf -- reply composite: stacked production
        benchmark (a,b) beside speedup and stage-share panels (c,d).
  3. FigR-delayT-comparison.pdf         -- direct comparison figure (response letter):
        (a) update and total-sweep times of the delay-T and submatrix-T updates vs L;
        (b) direct time ratio, delay-T over submatrix-T, at both accounting levels.

Points with kind != "measured" (extrapolated/estimated) are drawn with open markers and a
dotted extension from the last measured point, and are reported in the log.

Usage:
  make_benchmark_figures.py <report-data.json> <out-stacked.pdf> <out-composite.pdf> <out-delayt.pdf>
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.lines import Line2D
from matplotlib.colors import to_rgb
from matplotlib.patches import Rectangle
import matplotlib.patheffects as patheffects
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter, NullLocator, ScalarFormatter
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
WIDE_STYLE_SCALE = 0.9
# Inset 1: speedup over Fast (upper-left). Inset 2: Submatrix-T over delayed family (lower-right).
# Inset 1: x between the prior 0.08 and 0.12 placements.
# Inset 2: flatter, raised, so $L$ / tick labels stay inside the host axes.
INSET_BOUNDS = (0.10, 0.49, 0.36, 0.40)
INSET_BACKDROP_PAD = (0.13, 0.10, 0.01, 0.01)
INSET2_BOUNDS = (0.60, 0.10, 0.36, 0.28)
INSET2_BACKDROP_PAD = (0.055, 0.045, 0.005, 0.005)
INSET1_MARKER_SCALE = 0.82
INSET2_MARKER_SCALE = 0.62
INSET_TICK_LENGTH = 2.2
INSET_TICK_WIDTH = 0.55
INSET1_TITLE = "Speedup over Fast update"
INSET2_TITLE = "Speedup of Submatrix-T"
INSET2_FONT_SCALE = 0.92
X_LIM = (5, 80)
# Stacked layout: mid-gap OMP strip + legend above (a).
# Mid-gap is fully filled by the OMP strip (no white gutter). Strip height is
# ~30% thinner than the previous filled band (old gap*0.72).
STACKED_HSPACE = 0.11
STACKED_TOP = 0.84
STACKED_BOTTOM = 0.10
STACKED_LEFT = 0.18
STACKED_RIGHT = 0.98
OMP_STRIP_FRAC = 1.0
# Pull the strip slightly off the facing spines so they stay fully visible.
OMP_STRIP_INSET = 0.0018  # figure-fraction per side (~half a spine width)
OMP_FONT_SIZE = 7.0
OMP_TAG_FONT_SIZE = 7.0
OMP_TAG_TEXT = "Number of OpenMP threads"
OMP_TAG_COLOR = "0.20"
# Ink colors for thread numerals, keyed to the four OMP bands.
OMP_THREAD_INK = {1: "#3D6FA0", 4: "#A67A2E", 16: "#3D7A4A", 32: "#6A4E8A"}
REPLY_FIGSIZE = (6.9, 5.8 * STYLE_SCALE)
PANEL_LABEL_FONT = FontProperties(family="Arial", style="normal", weight="normal")

plt.rcParams.update({
    "font.size": FONT_SIZE,
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

BENCHMARK_L_TICKS = [6, 12, 24, 48, 72]
INSET_L_TICKS = [6, 12, 24, 48, 72]


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


def draw_measured(ax, L, med, lo, hi, color, marker, ls, filled=True, zorder=3,
                  visual_scale=1.0):
    ax.errorbar(L, med, yerr=[med - lo, hi - med], fmt=ls + marker, color=color,
                mfc=color if filled else "none", mec=color,
                markeredgewidth=STYLE_SCALE * visual_scale,
                ms=MARKER_SIZE * visual_scale, lw=LINE_WIDTH * visual_scale,
                elinewidth=STYLE_SCALE * visual_scale,
                capsize=2.5 * STYLE_SCALE * visual_scale,
                zorder=zorder)


def draw_extrapolated(ax, last_meas, extra, color, marker, ls=":", visual_scale=1.0):
    """Extrapolated points: open markers, dotted link from the last measured point."""
    L, med, lo, hi = extra
    if len(L) == 0:
        return
    if last_meas is not None:
        ax.plot([last_meas[0], L[0]], [last_meas[1], med[0]], ls=ls,
                color=color, marker=None, lw=LINE_WIDTH * visual_scale, zorder=2)
    ax.errorbar(L, med, yerr=[med - lo, hi - med], fmt=ls + marker, color=color,
                mfc="none", mec=color, markeredgewidth=STYLE_SCALE * visual_scale,
                ms=MARKER_SIZE * visual_scale, lw=LINE_WIDTH * visual_scale,
                elinewidth=STYLE_SCALE * visual_scale,
                capsize=2.5 * STYLE_SCALE * visual_scale,
                zorder=2)


def plain_log_tick(value, _position):
    if value <= 0:
        return ""
    exponent = int(round(np.log10(value)))
    if not np.isclose(value, 10.0 ** exponent):
        return ""
    return rf"$10^{{{exponent}}}$"


def style_axes(ax):
    ax.grid(True, color="#b0b0b0", linewidth=0.8, alpha=0.3)
    ax.tick_params(which="both", direction="in", top=True, right=True)


def label_panels(panels, visual_scale=1.0, x=0, y=1.02, ha="left", va="bottom"):
    font = PANEL_LABEL_FONT.copy()
    font.set_size(FONT_SIZE * visual_scale)
    for ax, tag in panels:
        ax.text(x, y, tag, transform=ax.transAxes, ha=ha, va=va,
                clip_on=False, fontproperties=font)


def label_panels_over_ylabel(fig, panels, visual_scale=1.0):
    """Place (a)/(b) on the y-label column; top of the tag on the axes top spine."""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    font = PANEL_LABEL_FONT.copy()
    font.set_size(FONT_SIZE * visual_scale)
    for ax, tag in panels:
        bb = ax.yaxis.get_label().get_window_extent(renderer=renderer)
        x_mid = 0.5 * (bb.x0 + bb.x1)
        x_frac = ax.transAxes.inverted().transform((x_mid, 0.0))[0]
        # Top of the letter aligns with the top spine (moves the tag down vs center).
        ax.text(x_frac, 1.0, tag, transform=ax.transAxes, ha="center",
                va="top", clip_on=False, fontproperties=font)


def label_every_decade(ax):
    ax.yaxis.set_major_locator(LogLocator(base=10, subs=(1.0,), numticks=20))
    ax.yaxis.set_major_formatter(FuncFormatter(plain_log_tick))
    ax.yaxis.set_minor_locator(LogLocator(base=10, subs=np.arange(2, 10) * 0.1,
                                          numticks=100))
    ax.yaxis.set_minor_formatter(NullFormatter())


def setup_log_ax(ax, ylabel):
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xticks([6, 12, 24, 36, 48, 60, 72])
    ax.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax.xaxis.set_minor_locator(NullLocator())
    ax.xaxis.set_minor_formatter(NullFormatter())
    label_every_decade(ax)
    ax.set_xlim(5, 88)
    ax.set_xlabel(r"Linear system size $L$")
    ax.set_ylabel(ylabel)
    style_axes(ax)


def setup_benchmark_log_ax(ax, ylabel, xlabel=r"$L$"):
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xticks(BENCHMARK_L_TICKS)
    ax.get_xaxis().set_major_formatter(ScalarFormatter())
    ax.xaxis.set_minor_formatter(NullFormatter())
    label_every_decade(ax)
    ax.set_xlim(5, 80)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    style_axes(ax)


# ------------------------------------------- mirrored absolute-time panel ----
def tint_pastel(hex_color, mix=0.45, toward=(1.0, 1.0, 1.0)):
    """Blend a report pastel toward `toward` (default: white)."""
    r, g, b = to_rgb(hex_color)
    tr, tg, tb = toward
    return (r * (1 - mix) + tr * mix, g * (1 - mix) + tg * mix, b * (1 - mix) + tb * mix)

def deepen_pastel(hex_color, mix=0.18, toward=(0.35, 0.40, 0.48)):
    """Slightly deepen a pastel for the mid-gap strip."""
    return tint_pastel(hex_color, mix=mix, toward=toward)


def add_inset(fig, ax, bounds, pad=None):
    """Axes-fraction inset whose *interior* is opaque white.

    No exterior white backdrop: tick/axis labels sit transparently on the host
    axes (and any OMP fills beneath). Only the inset rectangle itself is opaque.
    `pad` is accepted for call-site compatibility and ignored.
    """
    bx, by, bw, bh = bounds
    host = ax.get_position()
    axins = fig.add_axes([
        host.x0 + bx * host.width,
        host.y0 + by * host.height,
        bw * host.width,
        bh * host.height,
    ])
    axins.set_zorder(5)
    axins.patch.set_facecolor("white")
    axins.patch.set_alpha(1.0)
    # Keep a crisp black frame so the opaque island reads on pastel fills.
    for spine in axins.spines.values():
        spine.set_zorder(6)
    return axins


def finish_inset_axes(axins, ylim, yticks, font, xscale="linear", yscale="linear",
                    labelpad=1, tickpad=1):
    """Style an inset; no y-label — title is placed above the box separately.

    Inset 1 is log-log (speedup spans ~1–600; L also log). Inset 2 is lin-lin
    (ratios ~1–3.5).
    """
    axins.set_xscale(xscale)
    axins.set_yscale(yscale)
    axins.set_xlim(*X_LIM)
    axins.set_xticks(INSET_L_TICKS)
    axins.get_xaxis().set_major_formatter(ScalarFormatter())
    axins.xaxis.set_minor_formatter(NullFormatter())
    if xscale == "linear":
        axins.xaxis.set_minor_locator(NullLocator())
    axins.set_ylim(*ylim)
    axins.set_yticks(yticks)
    if yscale == "linear":
        axins.yaxis.set_major_formatter(ScalarFormatter())
        axins.yaxis.set_minor_locator(NullLocator())
    axins.set_xlabel(r"$L$", fontsize=font, labelpad=labelpad)
    axins.set_ylabel("")
    style_axes(axins)
    # Only the tick *marks* are shortened/thinned; label font sizes stay full.
    axins.tick_params(which="both", labelsize=font,
                      pad=tickpad, length=INSET_TICK_LENGTH, width=INSET_TICK_WIDTH,
                      direction="in")


def place_inset_title(fig, axins, title, font):
    """Title centered just above the inset box (frees the left y-label gutter)."""
    pos = axins.get_position()
    fig.text(pos.x0 + 0.5 * pos.width, pos.y1 + 0.0045, title,
             transform=fig.transFigure, ha="center", va="bottom",
             fontsize=font * 0.92, color="0.18", clip_on=False, zorder=6)


def draw_inset_vs_fast(fig, ax, data, field, visual_scale=1.0):
    """Upper-left inset: speedup of each delayed-family update over Fast."""
    axins = add_inset(fig, ax, INSET_BOUNDS, INSET_BACKDROP_PAD)
    for algo, (measured, estimated) in speedup_over_fast(data, field).items():
        if measured.shape[1]:
            axins.plot(measured[0], measured[1], "-" + ALGO_MARKER[algo],
                       color=ALGO_COLOR[algo], lw=INSET_LINE_WIDTH * visual_scale,
                       ms=INSET_MARKER_SIZE * visual_scale * INSET1_MARKER_SCALE)
        if estimated.shape[1]:
            if measured.shape[1]:
                axins.plot([measured[0, -1], estimated[0, 0]],
                           [measured[1, -1], estimated[1, 0]], ":",
                           color=ALGO_COLOR[algo],
                           lw=INSET_LINE_WIDTH * visual_scale)
            axins.plot(estimated[0], estimated[1], ":" + ALGO_MARKER[algo],
                       color=ALGO_COLOR[algo], mfc="none", mec=ALGO_COLOR[algo],
                       mew=STYLE_SCALE * visual_scale,
                       lw=INSET_LINE_WIDTH * visual_scale,
                       ms=INSET_MARKER_SIZE * visual_scale * INSET1_MARKER_SCALE)
    font = INSET_FONT_SIZE * visual_scale
    finish_inset_axes(axins, (0.8, 600), [1, 10, 100], font,
                      xscale="log", yscale="log")
    place_inset_title(fig, axins, INSET1_TITLE, font)


def speedup_sublr_over_delayed(data, field):
    """Submatrix-T speedup over Delay-G / Submatrix-G / Delay-T at shared measured L."""
    sub = measured_medians(data, "sublr", field)
    curves = {}
    for algo in ("delayg", "subg", "delaylr"):
        med = measured_medians(data, algo, field)
        common = sorted(set(sub) & set(med))
        curves[algo] = np.array([(L, med[L] / sub[L]) for L in common]).T
    return curves


def inset2_ylim_ticks(data, field):
    """Tight per-panel y-range for the Submatrix-T inset (update vs sweep differ)."""
    vals = []
    for curve in speedup_sublr_over_delayed(data, field).values():
        if curve.size:
            vals.extend(curve[1].tolist())
    lo, hi = min(vals), max(vals)
    pad = max(0.12, 0.08 * (hi - lo))
    y0, y1 = lo - 0.5 * pad, hi + pad
    # Round to a clean upper edge so the top series is not flush with the frame.
    import math
    y1 = math.ceil(y1 * 10) / 10
    y0 = max(0.75, math.floor(y0 * 10) / 10)
    # Major ticks every 0.5 within the window.
    t0 = math.ceil(y0 * 2) / 2
    t1 = math.floor(y1 * 2) / 2
    ticks = [t0 + 0.5 * i for i in range(int(round((t1 - t0) / 0.5)) + 1)]
    if not ticks:
        ticks = [1.0, 2.0, 3.0]
    return (y0, y1), ticks


def draw_inset_vs_delayed(fig, ax, data, field, visual_scale=1.0):
    """Lower-right inset: Submatrix-T speedup over the other delayed-family updates."""
    axins = add_inset(fig, ax, INSET2_BOUNDS, INSET2_BACKDROP_PAD)
    axins.axhline(1.0, color="0.65", lw=0.5, zorder=1)
    for algo, curve in speedup_sublr_over_delayed(data, field).items():
        if curve.size == 0:
            continue
        axins.plot(curve[0], curve[1], "-" + ALGO_MARKER[algo],
                   color=ALGO_COLOR[algo],
                   lw=INSET_LINE_WIDTH * visual_scale * 0.9,
                   ms=INSET_MARKER_SIZE * visual_scale * INSET2_MARKER_SCALE)
    font = INSET_FONT_SIZE * visual_scale * INSET2_FONT_SCALE * 0.92
    ylim, yticks = inset2_ylim_ticks(data, field)
    finish_inset_axes(axins, ylim, yticks, font,
                      xscale="linear", yscale="linear",
                      labelpad=0.2, tickpad=0.6)
    place_inset_title(fig, axins, INSET2_TITLE, font)


def panel_band_facecolor(band):
    """Panel fill: mild deepen; amber/green/violet only lightly nudged toward inks."""
    thr = int(band["threads"])
    ink = OMP_THREAD_INK.get(thr, "#555555")
    mix = 0.04 if thr == 1 else 0.12
    return tint_pastel(band["color"], mix=mix, toward=to_rgb(ink))


def draw_panel_omp_fills(ax, bands):
    """Full-height pastel OMP bands in the panel data area (below the grid)."""
    x0, x1 = X_LIM
    for i, band in enumerate(bands):
        left = max(band["left"], x0)
        right = min(band["right"] if i < len(bands) - 1 else x1, x1)
        ax.axvspan(left, right, facecolor=panel_band_facecolor(band),
                   edgecolor="none", alpha=0.58, zorder=0)
    ax.set_axisbelow(True)
    for line in ax.get_xgridlines() + ax.get_ygridlines():
        line.set_zorder(1)


def panel_abs_times(fig, ax, data, field, ylabel, ylim, visual_scale=1.0,
                    xlabel=r"$L$", omp_bands=None):
    """Absolute times of all five implementations + dual speedup insets.

    Optional full-height OMP fills live in the data area; inset interiors stay
    opaque white while their tick/axis labels remain undimmed by any backdrop.
    """
    for algo in ALGOS:
        meas, extra = series(data, algo, field)
        last = None
        if len(meas[0]):
            draw_measured(ax, *meas, ALGO_COLOR[algo], ALGO_MARKER[algo], "-",
                          visual_scale=visual_scale)
            last = meas[:, -1]
        draw_extrapolated(ax, last, extra, ALGO_COLOR[algo], ALGO_MARKER[algo],
                          visual_scale=visual_scale)
    setup_benchmark_log_ax(ax, ylabel, xlabel)
    ax.set_ylim(ylim)
    if omp_bands is not None:
        draw_panel_omp_fills(ax, omp_bands)
    draw_inset_vs_fast(fig, ax, data, field, visual_scale=visual_scale)
    draw_inset_vs_delayed(fig, ax, data, field, visual_scale=visual_scale)


def algo_legend_handles(visual_scale=1.0):
    """Two-row legend: Fast + extrapolated Fast; then the four delayed updates."""
    vs = visual_scale
    fast = Line2D([], [], color=ALGO_COLOR["fast"], marker=ALGO_MARKER["fast"],
                  mfc=ALGO_COLOR["fast"], ls="-", lw=LINE_WIDTH * vs,
                  ms=MARKER_SIZE * vs, label="Fast")
    # Matches draw_extrapolated: open marker + dotted connector (caption: extrapolated estimates).
    fast_extra = Line2D([], [], color=ALGO_COLOR["fast"], marker=ALGO_MARKER["fast"],
                        mfc="none", mec=ALGO_COLOR["fast"],
                        mew=STYLE_SCALE * vs, ls=":", lw=LINE_WIDTH * vs,
                        ms=MARKER_SIZE * vs, label="Fast (extrapolated from two-week run)")
    delayed = [
        Line2D([], [], color=ALGO_COLOR[a], marker=ALGO_MARKER[a],
               mfc=ALGO_COLOR[a], ls="-", lw=LINE_WIDTH * vs,
               ms=MARKER_SIZE * vs, label=ALGO_LABEL[a])
        for a in ("delayg", "subg", "delaylr", "sublr")
    ]
    return [fast, fast_extra], delayed


def place_benchmark_legend(fig, visual_scale, anchor_x, row1_y, row2_y):
    """Place the two-row algorithm legend at the given figure anchors.

    fig.legend() replaces any previous figure legend, so the first row is
    re-added with add_artist after the second row is created.
    """
    row1, row2 = algo_legend_handles(visual_scale)
    common = dict(
        fontsize=LEGEND_SIZE * visual_scale * 0.92,
        frameon=False, handlelength=1.5, handletextpad=0.35,
        columnspacing=0.85, borderaxespad=0.0,
    )
    leg1 = fig.legend(handles=row1, loc="lower center", ncol=2,
                      bbox_to_anchor=(anchor_x, row1_y), **common)
    leg2 = fig.legend(handles=row2, loc="lower center", ncol=4,
                      bbox_to_anchor=(anchor_x, row2_y), **common)
    fig.add_artist(leg1)


def omp_thread_numeral(fig, x_center, y_mid, threads):
    """Band-matched thread numeral with a light outline (no text box).

    Ink follows the band hue so the digit feels embedded in the strip; a thin
    light stroke separates it from tick labels without looking like a badge.
    """
    ink = OMP_THREAD_INK.get(int(threads), "#444444")
    fig.text(
        x_center, y_mid, str(threads), ha="center", va="center",
        fontsize=OMP_FONT_SIZE, color=ink, zorder=5, fontweight="bold",
        path_effects=[
            patheffects.withStroke(linewidth=2.2, foreground="white", alpha=0.92),
        ],
    )


def draw_omp_strip(fig, ax, bands, y0, y1, tag=True):
    """Pastel OMP partition strip in figure coordinates between y0 and y1.

    When tag=True, the threads=1 band carries "Number of OpenMP threads" on the
    left; each thread count sits in a colored chip matched to its band.
    """
    inv = fig.transFigure.inverted()
    pos = ax.get_position()
    strip_h = y1 - y0
    y_mid = 0.5 * (y0 + y1)
    x0_lim, x1_lim = X_LIM
    fx_left = pos.x0
    fx_right = pos.x1
    for i, band in enumerate(bands):
        left = max(band["left"], x0_lim)
        right = min(band["right"] if i < len(bands) - 1 else x1_lim, x1_lim)
        fx0 = inv.transform(ax.transData.transform((left, 1.0)))[0]
        fx1 = inv.transform(ax.transData.transform((right, 1.0)))[0]
        fx0 = max(fx0, fx_left)
        fx1 = min(fx1, fx_right)
        if fx1 <= fx0:
            continue
        fig.add_artist(Rectangle(
            (fx0, y0), fx1 - fx0, strip_h,
            transform=fig.transFigure, facecolor=band["color"],
            edgecolor="none", linewidth=0.0, clip_on=False, zorder=3,
        ))
        if i > 0:
            fig.add_artist(Rectangle(
                (fx0 - 0.0008, y0), 0.0016, strip_h,
                transform=fig.transFigure, facecolor="white",
                edgecolor="none", clip_on=False, zorder=3.5,
            ))

        threads = int(band["threads"])
        if tag and threads == 1:
            pad = 0.006 * (fx_right - fx_left)
            fig.text(
                fx0 + pad, y_mid, OMP_TAG_TEXT,
                ha="left", va="center", fontsize=OMP_TAG_FONT_SIZE,
                color=OMP_TAG_COLOR, zorder=4, clip_on=False,
                fontweight="bold",
                path_effects=[
                    patheffects.withStroke(linewidth=2.2, foreground="white",
                                           alpha=0.92),
                ],
            )
            # Park the "1" chip near the right edge of the blue band.
            omp_thread_numeral(fig, fx0 + 0.88 * (fx1 - fx0), y_mid, threads)
        else:
            cx = np.sqrt(left * right)
            fcx = inv.transform(ax.transData.transform((cx, 1.0)))[0]
            fcx = min(max(fcx, fx0), fx1)
            omp_thread_numeral(fig, fcx, y_mid, threads)


def draw_midgap_omp(fig, ax_top, ax_bot, bands):
    """OMP strip filling the stacked-panel mid-gap, inset slightly from both spines."""
    fig.canvas.draw()
    pos_t, pos_b = ax_top.get_position(), ax_bot.get_position()
    gap_h = pos_t.y0 - pos_b.y1
    inset = min(OMP_STRIP_INSET, 0.25 * gap_h)
    strip_y0 = pos_b.y1 + inset
    strip_y1 = pos_t.y0 - inset
    draw_omp_strip(fig, ax_top, bands, strip_y0, strip_y1, tag=True)


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
    visual_scale = 1.0 if orientation == "stacked" else WIDE_STYLE_SCALE
    bands = data["omp_bands"]
    if orientation == "stacked":
        context = {}
        figsize = (COLUMN_WIDTH, 12.81 * STYLE_SCALE)
    else:
        context = {"font.size": FONT_SIZE * visual_scale}
        figsize = (6.9, 6.4 * STYLE_SCALE)
    with plt.rc_context(context):
        if orientation == "stacked":
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=figsize, sharex=True)
            fig.subplots_adjust(hspace=STACKED_HSPACE, top=STACKED_TOP,
                                bottom=STACKED_BOTTOM, left=STACKED_LEFT,
                                right=STACKED_RIGHT)
            panel_abs_times(fig, ax1, data, "update_seconds",
                            "Update time per sweep (s)", ylim,
                            visual_scale=visual_scale, xlabel="",
                            omp_bands=bands)
            panel_abs_times(fig, ax2, data, "sweep_seconds",
                            "Total sweep time (s)", ylim,
                            visual_scale=visual_scale, xlabel=r"$L$",
                            omp_bands=bands)
            ax1.tick_params(axis="x", which="both", labelbottom=False)
            ax1.tick_params(axis="x", which="major", bottom=True, top=True)
            ax2.tick_params(axis="x", which="major", bottom=True, top=True)
            draw_midgap_omp(fig, ax1, ax2, bands)
            label_panels_over_ylabel(fig, ((ax1, "(a)"), (ax2, "(b)")), visual_scale)
            # Two-row legend above (a): center on the full figure (incl. y-label
            # column), not just the axes rectangle — otherwise it reads right-heavy.
            place_benchmark_legend(fig, visual_scale, 0.50,
                                   row1_y=STACKED_TOP + 0.036,
                                   row2_y=STACKED_TOP + 0.012)
            fig.savefig(out_path, bbox_inches="tight", pad_inches=0.08)
        else:
            # Wide layout: OMP strip above each panel; shared legend below both
            # panels (the stacked figure keeps the legend above (a)).
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=figsize)
            fig.subplots_adjust(left=0.09, right=0.98, bottom=0.26, top=0.82,
                                wspace=0.30)
            panel_abs_times(fig, ax1, data, "update_seconds",
                            "Update time per sweep (s)", ylim,
                            visual_scale=visual_scale, xlabel=r"$L$",
                            omp_bands=bands)
            panel_abs_times(fig, ax2, data, "sweep_seconds",
                            "Total sweep time (s)", ylim,
                            visual_scale=visual_scale, xlabel=r"$L$",
                            omp_bands=bands)
            fig.canvas.draw()
            strip_h = 0.030
            for i, ax in enumerate((ax1, ax2)):
                pos = ax.get_position()
                strip_y0 = pos.y1 + 0.010
                strip_y1 = strip_y0 + strip_h
                draw_omp_strip(fig, ax, bands, strip_y0, strip_y1, tag=(i == 0))
            label_panels_over_ylabel(fig, ((ax1, "(a)"), (ax2, "(b)")), visual_scale)
            # Two-row legend below both panels (same content as the stacked figure).
            place_benchmark_legend(fig, visual_scale, 0.535,
                                   row1_y=0.065, row2_y=0.015)
            fig.savefig(out_path, bbox_inches="tight", pad_inches=0.08)
        plt.close(fig)
    print("wrote", out_path)


# ------------------------------------------------- stage shares (on an ax) ----
def draw_stage_shares(ax, data, sizes=(18, 24, 48, 60),
                      legend_anchor=(-0.02, 1.16), legend_fontsize=None,
                      with_legend=True, text_scale=1.0, bar_height=0.62):
    rows = []  # top to bottom
    for L in reversed(sizes):
        for algo in ("sublr", "fast"):
            p = next(p for p in data["points"]
                     if p["algorithm"] == algo and p["L"] == L)
            share = [100.0 * p["stages"][s] / p["stage_total_seconds"] for s in STAGE_ORDER]
            rows.append((L, algo, share))

    # Pair gap after each (fast, submatrix-T) duo; keep bars taller than the ink.
    pair_gap = 0.55
    row_pitch = max(1.05, bar_height + 0.28)
    ypos = []
    y = 0.0
    for i, (L, algo, _) in enumerate(rows):
        ypos.append(y)
        y += row_pitch + (pair_gap if i % 2 == 1 else 0.0)
    ypos = np.array(ypos)[::-1]
    for y, (L, algo, share) in zip(ypos, rows):
        left = 0.0
        for si, s in enumerate(STAGE_ORDER):
            ax.barh(y, share[si], bar_height, left=left, color=STAGE_COLOR[s],
                    edgecolor="white", linewidth=0.4 * STYLE_SCALE, zorder=3)
            if share[si] >= 6:
                tcolor = "0.15" if s in STAGE_TEXT_DARK else "white"
                label = "≥99" if share[si] >= 99.5 else f"{share[si]:.0f}"
                ax.text(left + share[si] / 2, y, label,
                        ha="center", va="center",
                        fontsize=13 * STYLE_SCALE * text_scale,
                        color=tcolor, zorder=4)
            left += share[si]
        ax.text(2.0, y, "fast" if algo == "fast" else "submatrix-T",
                ha="left", va="center",
                fontsize=13 * STYLE_SCALE * text_scale,
                color="white", zorder=5)

    # One L label per (submatrix-T, fast) pair, centered between the two bars.
    pair_ticks, pair_labels = [], []
    for i in range(0, len(rows), 2):
        pair_ticks.append(0.5 * (ypos[i] + ypos[i + 1]))
        pair_labels.append(rf"$L$={rows[i][0]}")
    ax.set_yticks(pair_ticks)
    ax.set_yticklabels(pair_labels, fontsize=14 * STYLE_SCALE * text_scale)
    ax.set_xlim(0, 100)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xlabel("Share of total sweep time (%)",
                  fontsize=FONT_SIZE * text_scale)
    ax.tick_params(axis="x", labelsize=14 * STYLE_SCALE * text_scale)
    ax.set_axisbelow(True)
    style_axes(ax)
    handles = [plt.Rectangle((0, 0), 1, 1, fc=STAGE_COLOR[s], ec="white",
                             lw=0.4 * STYLE_SCALE,
                             label=STAGE_LABEL[s]) for s in STAGE_ORDER]
    if with_legend:
        fs = LEGEND_SIZE if legend_fontsize is None else legend_fontsize
        ax.legend(handles=handles, loc="lower left", bbox_to_anchor=legend_anchor,
                  ncol=3, columnspacing=0.8, handletextpad=0.35,
                  borderaxespad=0.0, fontsize=fs)
    return handles


# ---------------------------- reply composite (production + stages) ----
def fig_reply_composite(data, out_path):
    """Double-column reply figure: stacked production benchmark | speedup+stages.

    Sized from the manuscript stacked figure: left column ~= COLUMN_WIDTH wide
    and the same stacked height; fonts stay at full STYLE_SCALE (no downscale).
    Panel (c) is raised to the left-column legend height so the stage legend
    above (d) has a clear gap from the bars.
    """
    bands = data["omp_bands"]
    ylim = shared_ylim(data)
    vs = 1.0
    fig_w = 2.12 * COLUMN_WIDTH
    fig_h = 12.81 * STYLE_SCALE
    fig = plt.figure(figsize=(fig_w, fig_h))
    outer = fig.add_gridspec(
        1, 2, width_ratios=[1.08, 1.0], wspace=0.20,
        left=0.08, right=0.99, top=0.90, bottom=0.08,
    )
    left = outer[0].subgridspec(2, 1, hspace=STACKED_HSPACE)
    right = outer[1].subgridspec(2, 1, hspace=0.35, height_ratios=[1.0, 1.12])
    ax_a = fig.add_subplot(left[0])
    ax_b = fig.add_subplot(left[1], sharex=ax_a)
    ax_c = fig.add_subplot(right[0])
    ax_d = fig.add_subplot(right[1])

    with plt.rc_context({"font.size": FONT_SIZE * vs}):
        # ---- left: production absolute times (same chrome as FigS) ----
        panel_abs_times(fig, ax_a, data, "update_seconds",
                        "Update time per sweep (s)", ylim,
                        visual_scale=vs, xlabel="", omp_bands=bands)
        panel_abs_times(fig, ax_b, data, "sweep_seconds",
                        "Total sweep time (s)", ylim,
                        visual_scale=vs, xlabel=r"$L$", omp_bands=bands)
        ax_a.tick_params(axis="x", which="both", labelbottom=False)
        ax_a.tick_params(axis="x", which="major", bottom=True, top=True)
        ax_b.tick_params(axis="x", which="major", bottom=True, top=True)
        draw_midgap_omp(fig, ax_a, ax_b, bands)
        label_panels_over_ylabel(fig, ((ax_a, "(a)"), (ax_b, "(b)")), vs)
        fig.canvas.draw()
        pos_a = ax_a.get_position()
        pos_b = ax_b.get_position()
        cx = 0.5 * (pos_a.x0 + pos_a.x1)
        row1_y = min(0.965, pos_a.y1 + 0.034)
        row2_y = min(0.935, pos_a.y1 + 0.012)
        place_benchmark_legend(fig, vs, cx, row1_y=row1_y, row2_y=row2_y)

        # Shrink (c) so (d) and the legend gap get more room; (c) x-label must
        # stay clear of the stage legend above (d).
        pos_c0 = ax_c.get_position()
        right_x, right_w = pos_c0.x0, pos_c0.width
        bot_d = pos_b.y0
        top_c = min(0.985, row1_y + 0.035)
        total = top_c - bot_d
        gap = 0.155  # (c) xlabel above, two legend rows just above (d)
        # Give (d) the larger share; (c) is intentionally shorter.
        h_d = 0.55 * (total - gap)
        h_c = total - gap - h_d
        y_d0 = bot_d
        y_d1 = y_d0 + h_d
        y_c0 = y_d1 + gap
        ax_c.set_position([right_x, y_c0, right_w, h_c])
        ax_d.set_position([right_x, y_d0, right_w, h_d])

        # ---- right (c): speedup, legend inside axes ----
        # Measured + estimated fast (L=66,72) over measured submatrix-T.
        def _split_kind(algo, field):
            meas, est = {}, {}
            for point in data["points"]:
                if point["algorithm"] != algo or point[field] is None:
                    continue
                target = meas if point.get("kind", "measured") == "measured" else est
                target[point["L"]] = point[field]
            return meas, est

        fast_s_m, fast_s_e = _split_kind("fast", "sweep_seconds")
        fast_u_m, fast_u_e = _split_kind("fast", "update_seconds")
        sub_s = measured_medians(data, "sublr", "sweep_seconds")
        sub_u = measured_medians(data, "sublr", "update_seconds")
        common_m = sorted(set(fast_s_m) & set(sub_s) & set(fast_u_m) & set(sub_u))
        common_e = sorted(set(fast_s_e) & set(sub_s) & set(fast_u_e) & set(sub_u))
        L_m = np.array(common_m, dtype=float)
        r_sweep_m = np.array([fast_s_m[l] / sub_s[l] for l in common_m])
        r_update_m = np.array([fast_u_m[l] / sub_u[l] for l in common_m])
        # Measured: both solid+filled, distinguished by color/marker.
        # Extrapolated (L=66,72): dotted + open only — dashed is reserved no more.
        col_s, mk_s = ALGO_COLOR["sublr"], ALGO_MARKER["sublr"]       # blue ^
        col_u, mk_u = ALGO_COLOR["delayg"], ALGO_MARKER["delayg"]     # orange D
        ax_c.plot(L_m, r_sweep_m, "-" + mk_s, color=col_s,
                  ms=MARKER_SIZE * vs, lw=LINE_WIDTH * vs, zorder=3)
        ax_c.plot(L_m, r_update_m, "-" + mk_u, color=col_u,
                  ms=MARKER_SIZE * vs, lw=LINE_WIDTH * vs, zorder=3)
        if common_e:
            L_e = np.array(common_e, dtype=float)
            r_sweep_e = np.array([fast_s_e[l] / sub_s[l] for l in common_e])
            r_update_e = np.array([fast_u_e[l] / sub_u[l] for l in common_e])
            ax_c.plot([L_m[-1], L_e[0]], [r_sweep_m[-1], r_sweep_e[0]], ":",
                      color=col_s, lw=LINE_WIDTH * vs, zorder=2)
            ax_c.plot([L_m[-1], L_e[0]], [r_update_m[-1], r_update_e[0]], ":",
                      color=col_u, lw=LINE_WIDTH * vs, zorder=2)
            ax_c.plot(L_e, r_sweep_e, ":" + mk_s, color=col_s,
                      mfc="none", mec=col_s, mew=STYLE_SCALE * vs,
                      ms=MARKER_SIZE * vs, lw=LINE_WIDTH * vs, zorder=3)
            ax_c.plot(L_e, r_update_e, ":" + mk_u, color=col_u,
                      mfc="none", mec=col_u, mew=STYLE_SCALE * vs,
                      ms=MARKER_SIZE * vs, lw=LINE_WIDTH * vs, zorder=3)
            L_end, r_s_end, r_u_end = int(L_e[-1]), r_sweep_e[-1], r_update_e[-1]
        else:
            L_end, r_s_end, r_u_end = int(L_m[-1]), r_sweep_m[-1], r_update_m[-1]
        setup_log_ax(ax_c, "Speedup over fast update")
        ax_c.set_xlim(5, 115)
        ax_c.set_xticks([6, 12, 24, 48, 72])
        ax_c.set_yticks([1, 3, 10, 30, 100, 300])
        ax_c.get_yaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
        ax_c.set_ylim(1, 500)
        ax_c.tick_params(labelsize=FONT_SIZE * vs)
        ax_c.xaxis.label.set_size(FONT_SIZE * vs)
        ax_c.yaxis.label.set_size(FONT_SIZE * vs)
        handles = [
            Line2D([], [], color=col_s, marker=mk_s, mfc=col_s, ls="-",
                   lw=LINE_WIDTH * vs, ms=MARKER_SIZE * vs,
                   label=rf"Total sweep ({r_s_end:.1f}× at $L$={L_end})"),
            Line2D([], [], color=col_u, marker=mk_u, mfc=col_u, ls="-",
                   lw=LINE_WIDTH * vs, ms=MARKER_SIZE * vs,
                   label=rf"Update ({r_u_end:.0f}× at $L$={L_end})"),
        ]
        ax_c.legend(handles=handles, loc="upper left",
                    fontsize=LEGEND_SIZE * vs,
                    handletextpad=0.35, borderaxespad=0.35, labelspacing=0.25,
                    frameon=True, fancybox=False, edgecolor="0.75",
                    framealpha=0.92)
        print(f"composite endpoint speedups at L={L_end}: "
              f"update {r_u_end:.2f}x, sweep {r_s_end:.2f}x")
        label_panels_over_ylabel(fig, ((ax_c, "(c)"),), vs)

        # ---- right (d): stage shares; legend sits in the gap above (d) ----
        stage_handles = draw_stage_shares(
            ax_d, data, sizes=(18, 24, 48, 60),
            with_legend=False, text_scale=1.25, bar_height=1.08,
        )
        ax_d.xaxis.label.set_size(FONT_SIZE * vs)
        fig.canvas.draw()
        pos_c = ax_c.get_position()
        pos_d = ax_d.get_position()
        row1 = stage_handles[:3]
        row2 = stage_handles[3:]
        common = dict(
            bbox_transform=fig.transFigure, frameon=False,
            columnspacing=0.7, handletextpad=0.3, borderaxespad=0.0,
            fontsize=LEGEND_SIZE * vs * 0.95,
        )
        # Keep legend tight above (d); leave the upper gap clear for (c) xlabel.
        gap_lo, gap_hi = pos_d.y1, pos_c.y0
        y_leg_top = gap_lo + 0.42 * (gap_hi - gap_lo)
        y_leg_row2 = gap_lo + 0.22 * (gap_hi - gap_lo)
        leg1 = ax_d.legend(handles=row1, loc="upper left", ncol=3,
                           bbox_to_anchor=(pos_d.x0, y_leg_top), **common)
        ax_d.add_artist(leg1)
        ax_d.legend(handles=row2, loc="upper left", ncol=2,
                    bbox_to_anchor=(pos_d.x0, y_leg_row2), **common)
        font = PANEL_LABEL_FONT.copy()
        font.set_size(FONT_SIZE * vs)
        bb = ax_d.yaxis.get_label().get_window_extent(renderer=fig.canvas.get_renderer())
        x_mid = 0.5 * (bb.x0 + bb.x1)
        x_frac = ax_d.transAxes.inverted().transform((x_mid, 0.0))[0]
        _, y_axes = ax_d.transAxes.inverted().transform(
            fig.transFigure.transform((0.0, y_leg_top)))
        ax_d.text(x_frac, y_axes, "(d)", transform=ax_d.transAxes,
                  ha="center", va="top", clip_on=False, fontproperties=font)

    fig.savefig(out_path, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    print("wrote", out_path)


# --------------------------------------------- delay-T comparison (U12) ----
def fig_delayt_comparison(data, out_path):
    """Submatrix-T vs Delay-T in the production regime: absolute times and direct ratio."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=REPLY_FIGSIZE,
                                   gridspec_kw={"width_ratios": [1.2, 1]})
    fig.subplots_adjust(left=0.09, right=0.98, bottom=0.20, top=0.78, wspace=0.32)

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
    ax1.legend(handles=handles, loc="upper left", fontsize=LEGEND_SIZE,
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
    ax2.set_xticks([6, 12, 24, 36, 48, 72])
    ax2.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax2.xaxis.set_minor_locator(NullLocator())
    ax2.xaxis.set_minor_formatter(NullFormatter())
    ax2.set_xlim(5, 88)
    ax2.set_xlabel(r"Linear system size $L$")
    ax2.set_ylabel(r"Time ratio, delay-T / submatrix-T")
    ax2.set_ylim(0.8, 1.8)
    ax2.set_yticks([0.8, 1.0, 1.2, 1.4, 1.6])
    style_axes(ax2)
    ax2.legend(loc="lower right", bbox_to_anchor=(1.0, 1.02), handletextpad=0.4,
               borderaxespad=0.2, labelspacing=0.3, fontsize=LEGEND_SIZE)

    label_panels(((ax1, "(a)"), (ax2, "(b)")))
    fig.savefig(out_path, bbox_inches=fig.bbox_inches)
    plt.close(fig)
    print("wrote", out_path)


# -------------------------------------------------------------- drivers ----
def main():
    data_path, out_stacked, out_composite, out_delayt = sys.argv[1:5]
    data = load_data(data_path)
    print("report generated_at:", data["generated_at"])
    kinds = {(p["algorithm"], p["L"], p.get("kind", "measured"))
             for p in data["points"] if p.get("kind", "measured") != "measured"}
    if kinds:
        print("NOTE: non-measured points present:", sorted(kinds))
    else:
        print("all benchmark points are measured")
    fig_benchmark_mirrored(data, out_stacked, "stacked")
    # Reply letter composite: production stacked | speedup+stages.
    fig_reply_composite(data, out_composite)
    fig_delayt_comparison(data, out_delayt)


if __name__ == "__main__":
    main()
