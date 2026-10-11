"""Diagrams for the README explaining the emitter/reflector capacitance concept.

All dimensions are in emitter widths (1 emitter = 0.635 mm).
"""
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, Polygon, Rectangle

OUT_DIR = Path(__file__).resolve().parent

EMITTER_MM = 0.635
PERIOD = 8.0  # reflector pitch
STEM_W = 4.0  # reflector stem width (the part the emitters overlap)
BAR_W = 8.0  # reflector top bar width; equal to PERIOD so adjacent Ts touch
GAP = 0.1 / EMITTER_MM  # shrink applied to drawn shapes so neighbours are distinct

# Vertical layout of a reflector (hangs down from the top of the panel)
STEM_Y = (0.0, 2.0)
BAR_Y = (2.0, 3.0)
EMITTER_Y = (0.25, 1.75)

C_CURVE = "#2a6fb5"
C_POS = "#e8731c"
C_NEG = "#3d8fd9"
C_REFLECTOR = "#d4d4d4"
C_EDGE = "#333333"


def stem_overlap(d, x0, x1, stem0):
    """Length of [x0, x1] covered by reflector stems after the reflectors move right by d."""
    d = np.asarray(d, dtype=float)
    total = np.zeros_like(d)
    for k in range(-3, 4):
        left = stem0 + d + k * PERIOD
        right = left + STEM_W
        total += np.clip(np.minimum(right, x1) - np.maximum(left, x0), 0.0, None)
    return total


def reflector_outline(stem_left):
    """T-shaped outline, shrunk by GAP so adjacent shapes read as separate."""
    h = GAP / 2
    cx = stem_left + STEM_W / 2
    sw = STEM_W / 2 - h
    bw = BAR_W / 2 - h
    y0, y1 = STEM_Y[0] + h, STEM_Y[1]
    y2 = BAR_Y[1] - h
    return [
        (cx - sw, y0), (cx + sw, y0), (cx + sw, y1), (cx + bw, y1),
        (cx + bw, y2), (cx - bw, y2), (cx - bw, y1), (cx - sw, y1),
    ]


def draw_panel(ax, label, caption, d, stem0, emitters, show_motion=False, note=None):
    """emitters: list of (left_x, colour), each one emitter wide and fixed in place.
    note: optional text in the bottom-left corner (where the motion arrow would go)."""
    for k in range(-4, 5):
        pts = reflector_outline(stem0 + d + k * PERIOD)
        ax.add_patch(Polygon(pts, closed=True, fc=C_REFLECTOR, ec=C_EDGE, lw=1.2, zorder=1))
    for x, colour in emitters:
        ax.add_patch(Rectangle((x + GAP / 2, EMITTER_Y[0]), 1 - GAP, EMITTER_Y[1] - EMITTER_Y[0],
                               fc=colour, ec="none", alpha=0.9, zorder=2))

    # Three periods centred on the emitters, drawn at half horizontal scale
    centre = (min(x for x, _ in emitters) + max(x for x, _ in emitters) + 1) / 2
    left = centre - 1.5 * PERIOD
    ax.set_xlim(left, centre + 1.5 * PERIOD)
    ax.set_ylim(-1.0, 3.3)
    ax.set_aspect(2.0)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color(C_EDGE)
    ax.set_title(label, fontsize=14, fontweight="bold", pad=4)
    ax.set_xlabel(caption, fontsize=11, labelpad=6)
    if show_motion:
        ax.add_patch(FancyArrowPatch((left + 1.0, -0.5), (left + 8.0, -0.5), arrowstyle="-|>",
                                     mutation_scale=12, lw=1.2, color=C_EDGE))
        ax.text(left + 8.6, -0.5, "Motion", va="center", ha="left", fontsize=10)
    if note:
        ax.text(left + 1.0, -0.5, note, va="center", ha="left", fontsize=10)


def style_response_axes(ax, ylim, yticks, ylabel, xlabel_y=-0.06):
    ax.set_xlim(0, PERIOD)
    ax.set_ylim(*ylim)
    ax.set_xticks(range(0, int(PERIOD) + 1))
    ax.set_yticks(yticks)
    ax.set_xlabel("Distance (in emitter widths)", fontsize=11)
    ax.set_ylabel(ylabel, fontsize=11)
    ax.spines[["top", "right"]].set_visible(False)
    if ylim[0] < 0:
        # Keep the x axis on zero; pin the axis title to the bottom of the plot
        ax.spines["bottom"].set_position(("data", 0))
        ax.xaxis.set_label_coords(0.5, xlabel_y)
        ax.set_xticks(range(1, int(PERIOD) + 1))  # "0" would collide with the y axis "0"
    ax.grid(axis="x", color="#e6e6e6", lw=0.8)


def concept_figure(filename, response, points, captions, label_offsets, stem0, emitters,
                   ylim, yticks):
    """points: {label: d}; label_offsets: {label: (dx, dy)} in points, chosen to sit
    inside the axes and clear of the curve."""
    fig = plt.figure(figsize=(10, 5.9))
    gs = fig.add_gridspec(2, 4, height_ratios=[2.6, 1], hspace=0.3, wspace=0.08,
                          left=0.08, right=0.98, top=0.97, bottom=0.06)

    ax = fig.add_subplot(gs[0, :])
    d = np.linspace(0, PERIOD, 801)
    ax.plot(d, response(d), color=C_CURVE, lw=2.5)
    for label, x in points.items():
        y = float(response(x))
        ax.plot(x, y, "o", color=C_CURVE, ms=7, zorder=3, clip_on=False)
        ox, oy = label_offsets[label]
        ax.annotate(label, (x, y), xytext=(ox, oy), textcoords="offset points",
                    fontsize=13, fontweight="bold",
                    ha="left" if ox > 0 else "right" if ox < 0 else "center",
                    va="bottom" if oy > 0 else "top")
    style_response_axes(ax, ylim, yticks, "Coupling")

    for i, (label, x) in enumerate(points.items()):
        draw_panel(fig.add_subplot(gs[1, i]), label, captions[label], x, stem0, emitters,
                   show_motion=(i == 0))

    fig.savefig(OUT_DIR / filename, dpi=150)
    plt.close(fig)


def single_emitter_cap():
    # Emitter fixed at x = [0, 1]. At d = 0 the stem's right edge sits 2 emitters
    # left of it, so overlap starts at d = 2, is full from 3 to 6, and ends at 7.
    stem0 = -STEM_W - 2.0
    concept_figure(
        "readme-single-emitter-cap.png",
        response=lambda d: stem_overlap(d, 0.0, 1.0, stem0),
        points={"A": 0.0, "B": 2.0, "C": 3.0, "D": 6.0},
        captions={"A": "No Overlap", "B": "Overlap Starts", "C": "Full Overlap",
                  "D": "Overlap Ending"},
        label_offsets={"A": (8, 8), "B": (-8, 8), "C": (8, -8), "D": (-8, -8)},
        stem0=stem0,
        emitters=[(0.0, C_POS)],
        ylim=(-0.05, 1.15),
        yticks=[0, 1],
    )


# Positive emitters at x = [0, 4), negative at [4, 8). At d = 0 a stem sits
# exactly over the negative emitters; at d = 4 one sits over the positives.
DIFF_STEM0 = 4.0


def differential_response(d):
    return (stem_overlap(d, 0.0, 4.0, DIFF_STEM0)
            - stem_overlap(d, 4.0, 8.0, DIFF_STEM0))


def differential_emitter_cap():
    n = int(STEM_W)
    concept_figure(
        "readme-differential-emitter-cap.png",
        response=differential_response,
        points={"A": 0.0, "B": 2.0, "C": 4.0, "D": 6.0},
        captions={"A": "Full Negative Overlap", "B": "Equal Overlap",
                  "C": "Full Positive Overlap", "D": "Equal Overlap"},
        label_offsets={"A": (8, -8), "B": (-8, 8), "C": (0, -12), "D": (8, 8)},
        stem0=DIFF_STEM0,
        emitters=[(float(i), C_POS) for i in range(n)]
                 + [(float(i), C_NEG) for i in range(n, 2 * n)],
        ylim=(-5.0, 5.0),
        yticks=range(-4, 5),
    )


def position_ambiguity(measured=2.1):
    """A single measured pulse size matches two positions within one period."""
    fig, ax = plt.subplots(figsize=(10, 3.9))
    fig.subplots_adjust(left=0.08, right=0.98, top=0.95, bottom=0.12)

    d = np.linspace(0, PERIOD, 801)
    ax.plot(d, differential_response(d), color=C_CURVE, lw=2.5)

    # Triangle wave: rises 2 per emitter from -4 at d = 0 to +4 at d = 4, then falls
    rising = (measured + 4.0) / 2.0
    falling = PERIOD - rising
    ax.axhline(measured, color=C_POS, lw=1.5, ls="--", zorder=2)
    for x in (rising, falling):
        ax.plot([x, x], [0, measured], color=C_POS, lw=1.2, ls=":", zorder=2)
        ax.plot(x, measured, "o", color=C_POS, ms=8, zorder=4)
    ax.annotate(f"Measured {measured:.1f}V", (0.15, measured), xytext=(0, 6),
                textcoords="offset points", fontsize=12, fontweight="bold",
                color=C_POS, ha="left", va="bottom")

    style_response_axes(ax, (-5.0, 5.0), range(-4, 5), "Transient Voltage", xlabel_y=-0.08)
    fig.savefig(OUT_DIR / "readme-position-ambiguity.png", dpi=150)
    plt.close(fig)


def pattern_signs(shift, hidden=()):
    """Drive sign of each of the 8 emitters with the pattern rotated right by shift.
    hidden: slots within the pattern (0 = first positive, 4 = first negative) that
    produce no transient (sign 0); they rotate along with the pattern."""
    n = int(PERIOD)
    slots = [(e - shift) % n for e in range(n)]
    return [0 if s in hidden else 1 if s < n // 2 else -1 for s in slots]


def pattern_response(d, shift, hidden=()):
    return sum(s * stem_overlap(d, e, e + 1, DIFF_STEM0)
               for e, s in enumerate(pattern_signs(shift, hidden)))


def sliding_samples(shifts=(0, 1, 2, 4), hidden=(), filename="readme-sliding-samples.png"):
    """Reflectors held at position A while the drive pattern is rotated across the
    8 emitters. A shift of 4 is the fully flipped pattern."""
    fig, axes = plt.subplots(1, len(shifts), figsize=(10, 2.0))
    fig.subplots_adjust(left=0.08, right=0.98, top=1.0, bottom=0.3, wspace=0.08)

    for i, (ax, shift) in enumerate(zip(axes, shifts)):
        sign = pattern_signs(shift, hidden)
        emitters = [(float(e), C_POS if s > 0 else C_NEG) for e, s in enumerate(sign) if s]
        coupling = float(pattern_response(0.0, shift, hidden))
        value = "0" if np.isclose(coupling, 0) else f"{coupling:+.0f}".replace("-", "−")
        draw_panel(ax, f"Sample {shift}", f"Coupling: {value}",
                   0.0, DIFF_STEM0, emitters, note="No motion" if i == 0 else None)

    # Sample-time arrow spanning the panels, outside the axes
    x0 = axes[0].get_position().x0
    x1 = axes[-1].get_position().x1
    fig.add_artist(FancyArrowPatch((x0, 0.07), (x1, 0.07), transform=fig.transFigure,
                                   arrowstyle="-|>", mutation_scale=14, lw=1.4, color=C_EDGE))
    fig.text((x0 + x1) / 2, 0.1, "Sample time", ha="center", va="bottom", fontsize=11)

    fig.savefig(OUT_DIR / filename, dpi=150)
    plt.close(fig)


C_SAMPLES = ["#2a6fb5", "#e8731c", "#2e9e5b", "#8e5bb5"]


C_GHOST = "#9a9a9a"


def draw_sample_index(ax, position, wrap=False, hidden=()):
    """Sample values against sample index, with a ghost of the waveform they lie on
    and circled zero crossings. wrap adds the virtual sample at index 4 (= -sample 0)."""
    samples = [float(pattern_response(position, k, hidden)) for k in range(len(C_SAMPLES))]
    n_idx = len(samples) + (1 if wrap else 0)

    # Rotating the pattern (hidden slots included) by k is the same as the
    # reflectors sitting k behind, so sample k reads the response at position - k
    k_fine = np.linspace(-0.5, n_idx - 0.5, 801)
    ghost = pattern_response(position - k_fine, 0, hidden)
    ax.plot(k_fine, ghost, color=C_GHOST, lw=1.8, ls="--", zorder=2)
    for i in np.nonzero(np.diff(np.sign(ghost)))[0]:
        crossing = np.interp(0, sorted(ghost[i:i + 2]), k_fine[i:i + 2][np.argsort(ghost[i:i + 2])])
        ax.plot(crossing, 0, "o", ms=22, mfc="none", mec=C_GHOST, mew=1.8, zorder=2)

    for k, (v, colour) in enumerate(zip(samples, C_SAMPLES)):
        ax.plot(k, v, "o", color=colour, ms=9, zorder=3)
    if wrap:
        v = -samples[0]
        ax.plot(len(samples), v, "o", ms=9, mfc="white", mec=C_SAMPLES[0], mew=2.2, zorder=3)
        ax.annotate("Virtual sample\n(−Sample 0)", (len(samples), v), xytext=(0, 12),
                    textcoords="offset points", ha="center", va="bottom", fontsize=10,
                    color=C_SAMPLES[0])

    ax.set_xlim(-0.5, n_idx - 0.5)
    ax.set_ylim(-5.0, 5.0)
    ax.set_xticks(range(n_idx))
    ax.set_yticks(range(-4, 5))
    ax.set_xlabel("Sample index", fontsize=11)
    ax.set_ylabel("Transient Voltage", fontsize=11)
    ax.spines[["top", "right"]].set_visible(False)
    # Ticks stay at the bottom so the points can't cover them; zero drawn as a line
    ax.axhline(0, color=C_EDGE, lw=0.8, zorder=1)
    ax.grid(axis="x", color="#e6e6e6", lw=0.8)


def wrapped_samples(position=1.1):
    """At this position all four samples share a sign, so only the virtual sample
    at index 4 produces a zero crossing."""
    fig_h, ax_h = 3.9, 3.0
    fig = plt.figure(figsize=(10, fig_h))
    ax = fig.add_axes((0.08, 0.55 / fig_h, 0.9, ax_h / fig_h))
    draw_sample_index(ax, position, wrap=True)
    fig.savefig(OUT_DIR / "readme-wrapped-samples.png", dpi=150)
    plt.close(fig)


def sampled_waveforms(position=2.6, hidden=(), filename="readme-sampled-waveforms.png"):
    """One response line per drive-pattern shift, and the four values read off
    at a single reflector position."""
    # Both plots share the same size so volts-per-inch match between them
    fig_h, ax_h = 8.2, 3.0
    fig = plt.figure(figsize=(10, fig_h))
    top = fig.add_axes((0.08, 4.65 / fig_h, 0.9, ax_h / fig_h))
    bottom = fig.add_axes((0.08, 0.55 / fig_h, 0.9, ax_h / fig_h))

    d = np.linspace(0, PERIOD, 801)
    drawn = []
    for k, colour in enumerate(C_SAMPLES):
        r = pattern_response(d, k, hidden)
        # A curve identical to an earlier one is dashed on top so both colours show
        same = any(np.allclose(r, prev) for prev in drawn)
        drawn.append(r)
        top.plot(d, r, color=colour, lw=2.5, label=f"Sample {k}",
                 ls=(0, (4, 4)) if same else "-", zorder=2.5 if same else 2)
        top.plot(position, float(pattern_response(position, k, hidden)), "o", color=colour,
                 ms=7, zorder=4)
    top.axvline(position, color=C_EDGE, lw=1.4, ls="--", zorder=3)
    top.annotate("Sample position", (position, 4.6), xytext=(6, 0), textcoords="offset points",
                 ha="left", va="center", fontsize=10)
    style_response_axes(top, (-5.0, 5.0), range(-4, 5), "Transient Voltage", xlabel_y=-0.08)
    top.legend(ncol=4, loc="lower center", bbox_to_anchor=(0.5, 1.0), frameon=False, fontsize=10)

    draw_sample_index(bottom, position, hidden=hidden)

    # Arrow carrying the sample position down into the sampled plot
    x_fig = fig.transFigure.inverted().transform(top.transData.transform((position, 0)))[0]
    y0 = top.get_position().y0 - 0.01
    y1 = bottom.get_position().y1 + 0.01
    fig.add_artist(FancyArrowPatch((x_fig, y0), (x_fig, y1), transform=fig.transFigure,
                                   arrowstyle="-|>", mutation_scale=16, lw=1.4, ls="--",
                                   color=C_EDGE))

    fig.savefig(OUT_DIR / filename, dpi=150)
    plt.close(fig)


# The first emitter of the positive group and of the negative group produce no
# transient, which flattens the peaks
HIDDEN_SLOTS = (0, 4)


if __name__ == "__main__":
    single_emitter_cap()
    differential_emitter_cap()
    position_ambiguity()
    sliding_samples()
    sampled_waveforms()
    wrapped_samples()
    sliding_samples(hidden=HIDDEN_SLOTS, filename="readme-sliding-samples-hidden.png")
    sampled_waveforms(hidden=HIDDEN_SLOTS, filename="readme-sampled-waveforms-hidden.png")
