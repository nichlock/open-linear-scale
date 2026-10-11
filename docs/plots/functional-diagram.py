"""Functional block diagram for the README: every electrical and algorithm step of
one measurement, split into the 16 kHz per-transition chain and the 1 kHz
per-sequence processing. Uses standard DSP block-diagram symbols."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # render to file only; never open a window

import matplotlib.pyplot as plt
import schemdraw
import schemdraw.dsp as dsp
import schemdraw.elements as elm
from matplotlib.patches import FancyBboxPatch, Rectangle

OUT_DIR = Path(__file__).resolve().parent

C_ELEC = "#fde7d6"  # electrical / MCU hardware (runs without the CPU)
C_SOFT = "#e3eefa"  # software
C_FRAME = "#888888"
C_NOTE = "#555555"

Y1, Y2 = 0.0, -6.5  # centre lines of the two rows
ARROW = 1.9  # arrow length between blocks on the first row


def main():
    fig, ax = plt.subplots(figsize=(16, 7))
    d = schemdraw.Drawing(canvas=ax, show=False)
    d.config(fontsize=11)
    add = d.add  # elements are placed immediately, so their anchors are usable

    def block(e):
        # Face right explicitly; schemdraw otherwise inherits the last wire's direction
        return add(e.right())

    def wire(a, b, arrow=False):
        return add((dsp.Arrow if arrow else dsp.Line)().at(a).to(b))

    def label(xy, text, loc="top", ofst=0.1, **kw):
        return add(elm.Label().at(xy).label(text, loc=loc, ofst=ofst, **kw))

    # ---- 16 kHz: once per transition ----------------------------------------
    timer = block(dsp.Box(w=2.0, h=1.3, fill=C_ELEC).at((0, Y1)).anchor("W").label("Timer\n+ DMA"))
    # Square-wave source: a circle with an upright square-wave glyph (the circuit
    # SourceSquare symbol turns its glyph sideways on a horizontal wire)
    emit = block(dsp.Circle(fill=C_ELEC).at((timer.E[0] + ARROW, Y1)).anchor("W")
                 .label("Emitters ×8", loc="bottom", ofst=0.3))
    cx, cy = emit.center
    add(elm.Wire("-").at((cx - 0.28, cy - 0.15)).to((cx - 0.1, cy - 0.15)))
    for a, b in (((cx - 0.1, cy - 0.15), (cx - 0.1, cy + 0.15)),
                 ((cx - 0.1, cy + 0.15), (cx + 0.1, cy + 0.15)),
                 ((cx + 0.1, cy + 0.15), (cx + 0.1, cy - 0.15)),
                 ((cx + 0.1, cy - 0.15), (cx + 0.28, cy - 0.15))):
        wire(a, b)
    wire(timer.E, emit.W, arrow=True)
    cap = add(elm.Capacitor().at((emit.E[0] + 0.5, Y1)).right(1.6).label("Reflector", loc="top"))
    wire(emit.E, cap.start)
    amp = block(dsp.Amp(fill=C_ELEC).at((cap.end[0] + ARROW, Y1)).anchor("input")
              .label("Charge\nintegrator", loc="bottom", ofst=0.3))
    wire(cap.end, amp.input, arrow=True)
    lpf = block(dsp.Filter(response="lp", fill=C_ELEC).at((amp.out[0] + ARROW, Y1)).anchor("W")
              .label("Sallen-Key", loc="bottom", ofst=0.3))
    wire(amp.out, lpf.W, arrow=True)
    adc = block(dsp.Adc(fill=C_ELEC).at((lpf.E[0] + ARROW, Y1)).anchor("input").label("ADC"))
    wire(lpf.E, adc.input, arrow=True)
    ovs = block(dsp.Box(w=1.6, h=1.3, fill=C_ELEC).at((adc.out[0] + ARROW, Y1)).anchor("W")
              .label("Σ / N").label("Oversample", loc="bottom", ofst=0.3))
    wire(adc.out, ovs.W, arrow=True)

    # Back round to the start of the second row
    x_in = -1.0
    y_mid = (Y1 + Y2) / 2 + 0.3
    p1, p2 = (ovs.E[0] + 0.8, Y1), (ovs.E[0] + 0.8, y_mid)
    p3, p4 = (x_in, y_mid), (x_in, Y2)
    for a, b in ((ovs.E, p1), (p1, p2), (p2, p3), (p3, p4)):
        wire(a, b)

    # ---- 1 kHz: once per sequence -------------------------------------------
    # Differences of consecutive oversamples, each cancelled against its inverted
    # twin 8 states later
    combine = block(dsp.Box(w=3.4, h=1.8, fill=C_SOFT).at((x_in + 0.9, Y2)).anchor("W")
                    .label("Combine\nsymmetric\nmeasurements"))
    wire(p4, combine.W, arrow=True)
    split = block(dsp.Box(w=1.5, h=2.6, fill=C_SOFT).at((combine.E[0] + 2.2, Y2)).anchor("W")
                .label("Split\nlanes"))
    wire(combine.E, split.W, arrow=True)
    label(((combine.E[0] + split.W[0]) / 2, Y2), "Transients", fontsize=9.5)

    # Two lanes of four transients; lane A carries the 0.5 emitter offset
    lane_y = {"A": Y2 + 0.75, "B": Y2 - 0.75}
    x_zc = split.E[0] + 1.8
    zc_e, off, off_top = None, None, None
    for lane, y in lane_y.items():
        zc = block(dsp.Box(w=2.0, h=1.2, fill=C_SOFT).at((x_zc, y)).anchor("W").label("Zero\ncrossing"))
        wire((split.E[0], y), zc.W, arrow=True)
        label((split.E[0] + 0.15, y), lane, loc="top", ofst=0.05, fontsize=10)
        zc_e = zc.E
        if lane == "A":
            off = block(dsp.Sum(fill=C_SOFT).at((zc.E[0] + 0.9, y)).anchor("W"))
            wire(zc.E, off.W, arrow=True)
            off_top = (off.N[0], off.N[1] + 0.6)
            wire(off_top, off.N, arrow=True)
    x_join = off.E[0] + 0.5
    avg = block(dsp.Box(w=2.0, h=2.6, fill=C_SOFT).at((x_join + 0.8, Y2)).anchor("W").label("Average"))
    wire(off.E, (x_join, lane_y["A"]))
    wire((x_join, lane_y["A"]), (avg.W[0], lane_y["A"]), arrow=True)
    wire((zc_e[0], lane_y["B"]), (avg.W[0], lane_y["B"]), arrow=True)
    unwrap = block(dsp.Box(w=1.8, h=1.3, fill=C_SOFT).at((avg.E[0] + 1.0, Y2)).anchor("W")
                 .label("Unwrap"))
    wire(avg.E, unwrap.W, arrow=True)
    out = wire(unwrap.E, (unwrap.E[0] + 1.6, Y2), arrow=True)
    label(((unwrap.E[0] + out.end[0]) / 2, Y2), "Position", fontsize=10)

    d.draw(show=False)

    ax.text((p2[0] + p3[0]) / 2, y_mid + 0.15, "16 oversamples / sequence", ha="center",
            va="bottom", fontsize=11)

    # Centred directly over the offset input
    ax.text(off_top[0], off_top[1] + 0.1, "−0.5", ha="center", va="bottom", fontsize=11)

    # Rate-domain frames
    x0, x1 = x_in - 0.8, max(p1[0], out.end[0]) + 0.5
    frames = [(Y1 - 2.2, Y1 + 1.9, "16 kHz: once per transition"),
              (Y2 - 2.0, Y2 + 2.6, "1 kHz: once per sequence")]
    for lo, hi, title in frames:
        ax.add_patch(FancyBboxPatch((x0, lo), x1 - x0, hi - lo,
                                    boxstyle="round,pad=0,rounding_size=0.3",
                                    fc="none", ec=C_FRAME, lw=1.2, ls="--", zorder=0))
        ax.text(x1 - 0.3, hi - 0.25, title, ha="right", va="top", fontsize=11,
                fontweight="bold", color=C_NOTE)

    # Key, above both rows
    ky, kx = Y1 + 2.7, x0
    for fill, text in ((C_ELEC, "Electrical / MCU hardware"), (C_SOFT, "Software")):
        ax.add_patch(Rectangle((kx, ky - 0.3), 0.8, 0.6, fc=fill, ec="black", lw=1.0))
        ax.text(kx + 1.0, ky, text, ha="left", va="center", fontsize=10.5)
        kx += 1.0 + 0.2 * len(text) + 1.0

    ax.set_xlim(x0 - 0.2, x1 + 0.2)
    ax.set_ylim(Y2 - 2.3, ky + 0.6)
    ax.set_aspect("equal")
    ax.axis("off")
    for ext in ("png", "svg"):
        fig.savefig(OUT_DIR / f"functional-diagram.{ext}", dpi=150, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
