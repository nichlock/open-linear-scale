"""Timing diagram for the README: one full sample sequence (all 16 emitter states),
showing the emitter bus, the charge integrator output and the ADC conversions."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # render to file only; never open a window

import matplotlib.pyplot as plt
import numpy as np
from scipy import signal

OUT_DIR = Path(__file__).resolve().parent

# Copied from the firmware (sensor-math.hpp)
EMITTER_STATES = [
    0x0F, 0xE1, 0x1E, 0xC3, 0x3C, 0x87, 0x78, 0x0F,
    0xF0, 0x1E, 0xE1, 0x3C, 0xC3, 0x78, 0x87, 0xF0,
]
N_EMITTERS = 8
N_STATES = len(EMITTER_STATES)

# Reflector stem (4 emitters wide, 8 pitch) position over the emitters, in emitter
# widths. Any non-integer value gives a representative mix of step sizes.
REFLECTOR_POS = 1.3
STEM_W, PERIOD = 4.0, 8.0

CONVERSIONS_PER_STATE = 4  # just enough stems to show several per transition
ADC_WINDOW = (0.55, 0.9)  # where in each state the oversample burst sits

# Row layout (y ranges)
BUS_Y = (3.0, 3.45)
INT_Y = (1.3, 2.6)
ADC_Y = (0.2, 0.55)

C_WAVE = "#2a6fb5"
C_EDGE = "#333333"
C_GRID = "#d9d9d9"
C_NOTE = "#555555"


def emitter_weights():
    """Fraction of each emitter covered by a reflector stem."""
    w = np.zeros(N_EMITTERS)
    for k in range(-2, 3):
        left = REFLECTOR_POS + k * PERIOD
        for e in range(N_EMITTERS):
            w[e] += max(0.0, min(left + STEM_W, e + 1) - max(left, e))
    return w


def intout_wave(samples_per_state=400):
    """Integrator output over one sequence: an inverted step per transition sized by
    the coupled emitters, a fast settle and a slow droop from the bleed resistor."""
    w = emitter_weights()
    coupled = np.array([sum(w[e] for e in range(N_EMITTERS) if s >> e & 1)
                        for s in EMITTER_STATES])
    target = -np.repeat(np.tile(coupled, 3), samples_per_state)  # 3 periods to settle
    droop = np.exp(-1 / (6.0 * samples_per_state))
    stepped = signal.lfilter([1.0, -1.0], [1.0, -droop], target)
    settle = np.exp(-1 / (0.03 * samples_per_state))
    smooth = signal.lfilter([1 - settle], [1.0, -settle], stepped)
    v = smooth[-N_STATES * samples_per_state:]
    t = np.arange(len(v)) / samples_per_state
    return t, v


def bus_row(ax):
    lo, hi = BUS_Y
    mid, c = (lo + hi) / 2, 0.1
    for i, state in enumerate(EMITTER_STATES):
        x0, x1 = i, i + 1
        ax.fill([x0, x0 + c, x1 - c, x1, x1 - c, x0 + c],
                [mid, hi, hi, mid, lo, lo], fc="white", ec=C_EDGE, lw=1.4)
        ax.text(i + 0.5, mid, f"0x{state:02X}", ha="center", va="center", fontsize=9,
                family="monospace")


def intout_row(ax):
    t, v = intout_wave()
    lo, hi = INT_Y
    v = (v - v.min()) / (v.max() - v.min())
    ax.plot(t, lo + v * (hi - lo), color=C_WAVE, lw=1.8)


def adc_row(ax):
    lo, hi = ADC_Y
    for i in range(N_STATES):
        for x in np.linspace(i + ADC_WINDOW[0], i + ADC_WINDOW[1], CONVERSIONS_PER_STATE):
            ax.plot([x, x], [lo, hi], color=C_EDGE, lw=1.2)
            ax.plot(x, hi, "o", color=C_EDGE, ms=3.5)

    # Call out one conversion and one oversample burst
    x_conv = 0 + ADC_WINDOW[0]
    ax.annotate("conversion", (x_conv, hi + 0.06), xytext=(x_conv - 0.25, hi + 0.42),
                ha="center", va="bottom", fontsize=9, color=C_NOTE,
                arrowprops=dict(arrowstyle="-|>", color=C_NOTE, lw=1.0, mutation_scale=9))
    b0, b1 = 2 + ADC_WINDOW[0], 2 + ADC_WINDOW[1]
    yb = hi + 0.15
    ax.plot([b0, b0, b1, b1], [yb, yb + 0.1, yb + 0.1, yb], color=C_NOTE, lw=1.0)
    ax.text((b0 + b1) / 2, yb + 0.16, "oversample", ha="center", va="bottom", fontsize=9,
            color=C_NOTE)


def main():
    fig, ax = plt.subplots(figsize=(13, 4.2))

    # State boundaries
    for i in range(N_STATES + 1):
        ax.plot([i, i], [ADC_Y[0] - 0.05, BUS_Y[1] + 0.05], color=C_GRID, lw=0.8, zorder=0)
    for i in range(N_STATES):
        ax.text(i + 0.5, BUS_Y[1] + 0.15, str(i), ha="center", va="bottom", fontsize=9,
                color=C_NOTE)
    ax.text(-0.15, BUS_Y[1] + 0.15, "State", ha="right", va="bottom", fontsize=9, color=C_NOTE)

    bus_row(ax)
    intout_row(ax)
    adc_row(ax)

    for label, (lo, hi) in (("EM0…7", BUS_Y), ("IntOut", INT_Y), ("ADC", ADC_Y)):
        ax.text(-0.3, (lo + hi) / 2, label, ha="right", va="center", fontsize=12)

    # One sample sequence spans all 16 states
    yb = ADC_Y[0] - 0.3
    ax.annotate("", (0, yb), xytext=(N_STATES, yb),
                arrowprops=dict(arrowstyle="<|-|>", color=C_EDGE, lw=1.2, mutation_scale=12,
                                shrinkA=0, shrinkB=0))
    ax.text(N_STATES / 2, yb - 0.08, "Sample sequence (one period)", ha="center", va="top",
            fontsize=11)

    ax.set_xlim(-1.6, N_STATES + 0.1)
    ax.set_ylim(yb - 0.45, BUS_Y[1] + 0.45)
    ax.axis("off")
    for ext in ("png", "svg"):
        fig.savefig(OUT_DIR / f"timing-diagram.{ext}", dpi=150, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
