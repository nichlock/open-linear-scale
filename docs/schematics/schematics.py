"""Receive-chain schematic for the README, with example waveforms at each node."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # render to file only; never open a window

import matplotlib.pyplot as plt
import numpy as np
import schemdraw
import schemdraw.dsp as dsp
import schemdraw.elements as elm
from matplotlib.patches import ConnectionPatch
from matplotlib.transforms import ScaledTranslation
from scipy import signal

OUT_DIR = Path(__file__).resolve().parent

C_WAVE = "#2a6fb5"

fig = plt.figure(figsize=(11, 6.2))
ax = fig.add_axes((0.0, 0.33, 1.0, 0.67))
with schemdraw.Drawing(canvas=ax, show=False) as d:
    d.config(fontsize=11)
    elm.Ground()
    elm.SourceSquare().up().label("Emitter")
    elm.Line().right(1)
    elm.Capacitor().right().label("$C_{couple}$")
    elm.Line().right(1)
    rx = elm.Dot().label("RX", loc="bottom")
    elm.Line().right(1.5)
    oa = elm.Opamp(leads=True).anchor("in1")

    # Feedback: trimmable C_fb with a 100M bleed resistor in parallel
    fb_low = elm.Line().at(rx.center).up(1.5)
    cfb = elm.Capacitor(variable=True).right().tox(oa.out).label("$C_{fb}$ (trim)")
    elm.Line().down().toy(oa.out)
    elm.Line().at(fb_low.end).up(1.5)
    elm.Resistor().right().tox(oa.out).label("100 M$\\Omega$")
    elm.Line().down().toy(cfb.end)
    elm.Dot().at(fb_low.end)
    elm.Dot().at(cfb.end)

    # Non-inverting input to the reference
    elm.Line().at(oa.in2).left(0.75)
    elm.Dot(open=True).label("$V_{ref}$", loc="bottom")

    integ = elm.Dot().at(oa.out).label("IntOut", loc="bottom")
    elm.Line().right(2)
    dsp.Filter(response="lp").anchor("W").label("Sallen-Key LPF", loc="bottom", ofst=0.15)
    elm.Line().right(2)
    filt = elm.Dot().label("FiltOut", loc="bottom")

    d.draw(show=False)

ax.axis("off")
# Between the RX and IntOut leader lines, below the op-amp
ax.text((rx.center[0] + integ.center[0]) / 2, oa.in2[1] - 1.6,
        "Integrator gain $= -\\dfrac{C_{couple}}{C_{fb}}$",
        ha="center", va="top", fontsize=11)

# Example waveforms: several emitter periods, shown once the filter has settled
period = 1.0
fs = 400
t_all = np.arange(0, 6 * period, 1 / fs)
emitter = np.where((t_all % period) < period / 2, 1.0, -1.0)
edges = np.diff(emitter, prepend=emitter[0])

# RX: a brief spike at each edge before the integrator pulls it back to the reference
rx_wave = signal.lfilter([1.0], [1.0, -np.exp(-1 / (0.02 * fs))], edges)
# IntOut: inverted step per edge, slowly drooping through the 100M bleed resistor
droop = np.exp(-1 / (3.0 * period * fs))
int_wave = -signal.lfilter([1.0, -1.0], [1.0, -droop], emitter)
# FiltOut: second-order low-pass rounds the steps off
sos = signal.butter(2, 1.6 / period, fs=fs, output="sos")
filt_wave = signal.sosfilt(sos, int_wave)

show = t_all >= 3 * period
t = t_all[show] - t_all[show][0]


def node_plot(node, t, v, title, width=0.17):
    """Small waveform panel centred under a schematic node, with a leader line."""
    fig.canvas.draw()
    x_fig = fig.transFigure.inverted().transform(ax.transData.transform(node))[0]
    ins = fig.add_axes((x_fig - width / 2, 0.04, width, 0.22))
    ins.plot(t, v, color=C_WAVE, lw=1.5)
    ins.set_title(title, fontsize=9)
    ins.set_xticks([])
    ins.set_yticks([])
    pad = (v.max() - v.min()) * 0.15
    ins.set_ylim(v.min() - pad, v.max() + pad)
    # Leader stops short of the node label and panel title, like a dimension line.
    # Offsets are in points: the node label sits ~18 pt below the dot, the
    # title ~17 pt above the panel
    gap = 4 / 72
    start = ax.transData + ScaledTranslation(0, -(18 / 72 + gap), fig.dpi_scale_trans)
    end = ins.transAxes + ScaledTranslation(0, 17 / 72 + gap, fig.dpi_scale_trans)
    fig.add_artist(ConnectionPatch(node, (0.5, 1.0), coordsA=start, coordsB=end,
                                   ls=":", lw=0.9, color="k"))


node_plot(rx.center, t, rx_wave[show], "RX: spikes")
node_plot(integ.center, t, int_wave[show], "IntOut: steps")
node_plot(filt.center, t, filt_wave[show], "FiltOut: filtered")

fig.savefig(OUT_DIR / "rx-chain.svg", bbox_inches="tight")
fig.savefig(OUT_DIR / "rx-chain.png", bbox_inches="tight", dpi=150)
plt.close(fig)
