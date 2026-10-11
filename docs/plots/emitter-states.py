"""Emitter state transitions for the README.

Each row is the change from one entry of `emitter_states` (firmware) to the next,
one rectangle per emitter: orange = driven high (rising), blue = driven low
(falling), white = no change. Emitter 0 is bit 0, drawn on the left.
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # render to file only; never open a window

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

OUT_DIR = Path(__file__).resolve().parent

# Copied from the firmware
EMITTER_STATES = [
    0x0F, 0xE1, 0x1E, 0xC3, 0x3C, 0x87, 0x78, 0x0F,
    0xF0, 0x1E, 0xE1, 0x3C, 0xC3, 0x78, 0x87, 0xF0,
]
N_EMITTERS = 8

C_POS = "#e8731c"
C_NEG = "#3d8fd9"
C_NONE = "white"
C_EDGE = "black"

CELL_W, CELL_H = 0.6, 1.0  # tall, narrow emitter rectangles
PITCH_X, PITCH_Y = 0.8, 1.25
HALF_GAP = 0.6  # extra space between the two halves of the sequence


def transitions(states):
    """Per-emitter change from each state to the next (wrapping at the end): +1, -1 or 0."""
    rows = []
    for i, before in enumerate(states):
        after = states[(i + 1) % len(states)]
        rows.append([((after >> e) & 1) - ((before >> e) & 1) for e in range(N_EMITTERS)])
    return rows


# One colour per reduced pattern, kept clear of the orange/blue emitter colours
C_LINKS = ["#2e7d32", "#8e24aa", "#00838f", "#c2185b",
           "#6d4c41", "#1a237e", "#827717", "#37474f"]
N_REDUCED = N_EMITTERS // 2  # emitters 4-7 always mirror emitters 0-3

# Layout of the reduced patterns and the wiring to them (x in the same units as PITCH_X)
MULT_X = N_EMITTERS * PITCH_X + 0.05
WIRE_X0 = MULT_X + 1.3
BUS_X0, BUS_DX = WIRE_X0 + 0.5, 0.35
REDUCED_X = BUS_X0 + 8 * BUS_DX + 0.5


def draw_cells(ax, x, y, changes):
    for e, change in enumerate(changes):
        colour = C_POS if change > 0 else C_NEG if change < 0 else C_NONE
        ax.add_patch(FancyBboxPatch((x + e * PITCH_X, y), CELL_W, CELL_H,
                                    boxstyle="round,pad=0,rounding_size=0.08",
                                    fc=colour, ec=C_EDGE, lw=2.0))


def reduced_target(r, n_rows):
    """Which reduced pattern row r maps to, and the sign it carries.

    Every transition is [h, -h] for some 4-emitter pattern h, and the second half of
    the sequence is the first half inverted. So the reduced patterns are emitters 0-3
    of the first 8 transitions, split into two interleaved lanes: even rows are lane
    A, odd rows lane B. Returns (target index 0-7 ordered A0..A3, B0..B3, sign)."""
    half = n_rows // 2
    base = r % half
    lane = base % 2
    return lane * N_REDUCED + base // 2, (1 if r < half else -1)


# Offset of each reduced pattern in emitter widths, matching the firmware
# (measure-main-events.cpp mapped_readings + casm::evalPosition). Each ADC reading is
# taken before that period's emitter update, so lane A lands in firmware phase 1 as
# [-A3, A0, A1, A2] (shifted by -0.5) and lane B in phase 0 as [-B3, B0, B1, B2].
# That puts A_i at i + 0.5 and B_i at i + 1 (B3 at 4 is the inverted -B3 at 0).
LANE_OFFSET = {0: 0.5, 1: 1.0}  # lane A, lane B


def main(style, filename):
    """style: "schematic" (right-angle buses with junction dots) or "diagonal"
    (straight arrows from each row to its reduced pattern)."""
    rows = transitions(EMITTER_STATES)
    half = len(rows) // 2
    height = len(rows) * PITCH_Y + HALF_GAP

    fig, ax = plt.subplots(figsize=(8.4, height * 0.42))
    centres = []
    for r, row in enumerate(rows):
        y = height - (r + 1) * PITCH_Y - (HALF_GAP if r >= half else 0)
        centres.append(y + CELL_H / 2)
        draw_cells(ax, 0.0, y, row)
        before = EMITTER_STATES[r]
        after = EMITTER_STATES[(r + 1) % len(EMITTER_STATES)]
        ax.text(-0.3, y + CELL_H / 2, f"0x{before:02X} → 0x{after:02X}",
                ha="right", va="center", fontsize=10, family="monospace")

    for e in range(N_EMITTERS):
        ax.text(e * PITCH_X + CELL_W / 2, height + 0.15, str(e),
                ha="center", va="bottom", fontsize=10)
    ax.text((N_EMITTERS - 1) * PITCH_X / 2 + CELL_W / 2, height + 0.75, "Emitter",
            ha="center", va="bottom", fontsize=11)

    # Reduced patterns: lane A centred on the first half of the sequence, lane B on
    # the second, each one level with the middle of a pair of source rows
    targets = []
    for t in range(2 * N_REDUCED):
        lane, i = divmod(t, N_REDUCED)
        a = lane * half + 2 * i
        targets.append((centres[a] + centres[a + 1]) / 2)
    offset_x = REDUCED_X + N_REDUCED * PITCH_X + 1.6
    for t, cy in enumerate(targets):
        lane, i = divmod(t, N_REDUCED)
        draw_cells(ax, REDUCED_X, cy - CELL_H / 2, rows[2 * i + lane][:N_REDUCED])
        ax.text(REDUCED_X + N_REDUCED * PITCH_X + 0.1, cy, f"{'AB'[lane]}{i}",
                ha="left", va="center", fontsize=11, fontweight="bold", color=C_LINKS[t])
        offset = i + LANE_OFFSET[lane]
        ax.text(offset_x, cy, f"{offset:g}", ha="center", va="center", fontsize=11)
    ax.text(offset_x, height + 0.15, "(emitters)", ha="center", va="bottom", fontsize=9)
    ax.text(offset_x, height + 0.75, "Offset", ha="center", va="bottom", fontsize=11)
    for lane in range(2):
        cys = targets[lane * N_REDUCED:(lane + 1) * N_REDUCED]
        ax.text(REDUCED_X + N_REDUCED * PITCH_X / 2 - 0.1, max(cys) + CELL_H / 2 + 0.25,
                f"Lane {'AB'[lane]}", ha="center", va="bottom", fontsize=11)
    for e in range(N_REDUCED):
        ax.text(REDUCED_X + e * PITCH_X + CELL_W / 2, height + 0.15, str(e),
                ha="center", va="bottom", fontsize=10)
    ax.text(REDUCED_X + (N_REDUCED - 1) * PITCH_X / 2 + CELL_W / 2, height + 0.75,
            "Reduced", ha="center", va="bottom", fontsize=11)

    for r, cy in enumerate(centres):
        t, sign = reduced_target(r, len(rows))
        ax.text(MULT_X, cy, "×1" if sign > 0 else "×−1", ha="left", va="center",
                fontsize=11, fontweight="bold", color=C_LINKS[t])
    if style == "schematic":
        draw_schematic_links(ax, centres, targets)
    elif style == "diagonal":
        draw_diagonal_links(ax, centres, targets)
    else:
        raise ValueError(f"unknown style {style!r}")

    ax.set_xlim(-3.6, offset_x + 0.8)
    ax.set_ylim(-0.2, height + 1.3)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.savefig(OUT_DIR / filename, dpi=150, bbox_inches="tight")
    plt.close(fig)


def link_style(sign):
    return "-" if sign > 0 else (0, (3, 2))


def draw_schematic_links(ax, centres, targets):
    """Each reduced pattern has its own vertical bus; source rows join it with a dot,
    so crossings without a dot are not connections."""
    n = len(centres)
    for r, cy in enumerate(centres):
        t, sign = reduced_target(r, n)
        bus_x = BUS_X0 + t * BUS_DX
        ax.plot([WIRE_X0, bus_x], [cy, cy], color=C_LINKS[t], lw=1.6, ls=link_style(sign),
                solid_capstyle="butt")
        ax.plot(bus_x, cy, "o", color=C_LINKS[t], ms=5)
    for t, cy in enumerate(targets):
        colour = C_LINKS[t]
        bus_x = BUS_X0 + t * BUS_DX
        ys = [c for r, c in enumerate(centres) if reduced_target(r, n)[0] == t] + [cy]
        ax.plot([bus_x, bus_x], [min(ys), max(ys)], color=colour, lw=1.6)
        ax.annotate("", (REDUCED_X - 0.1, cy), xytext=(bus_x, cy),
                    arrowprops=dict(arrowstyle="-|>", color=colour, lw=1.6,
                                    shrinkA=0, shrinkB=0, mutation_scale=12))
        ax.plot(bus_x, cy, "o", color=colour, ms=5)


def draw_diagonal_links(ax, centres, targets):
    """A straight arrow from each source row to its reduced pattern."""
    for r, cy in enumerate(centres):
        t, sign = reduced_target(r, len(centres))
        ax.annotate("", (REDUCED_X - 0.1, targets[t]), xytext=(WIRE_X0, cy),
                    arrowprops=dict(arrowstyle="-|>", color=C_LINKS[t], lw=1.6,
                                    ls=link_style(sign), shrinkA=0, shrinkB=0,
                                    mutation_scale=12))


if __name__ == "__main__":
    main("schematic", "emitter-state-transitions.png")
    main("diagonal", "emitter-state-transitions-diagonal.png")
