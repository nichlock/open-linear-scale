"""Feather-style pinout diagram of the sensor PCB.

Renders the board top-down (orthographic) with kicad-cli, reads pad positions
from the board file with KiCad's bundled Python, then draws colour-coded labels
with leader lines. Pad positions come from the board, so the labels follow any
layout change; the label text below is the hand-written part.

The board is drawn rotated 90 degrees clockwise so the connectors sit on the
left and the test points on the right, which keeps most leader lines straight.

Requires KiCad 9 installed at KICAD_BIN (kicad-cli and its python.exe).
"""
import json
import subprocess
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # render to file only; never open a window

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch
from PIL import Image
from scipy import ndimage

OUT_DIR = Path(__file__).resolve().parent
BOARD = OUT_DIR.parents[1] / "hardware" / "sensor-pcb" / "sensor-pcb.kicad_pcb"
KICAD_BIN = Path(r"C:\Program Files\KiCad\9.0\bin")

# Mounting holes used to calibrate render pixels to board millimetres.
CAL_REFS = ["MH1", "MH2", "MH3", "MH4"]

# Pill colours: (fill, text)
STYLE = {
    "name": ("#ffffff", "#222222"),
    "gnd": ("#222222", "#ffffff"),
    "power": ("#d62728", "#ffffff"),
    "comms": ("#1f77b4", "#ffffff"),
    "debug": ("#8e44ad", "#ffffff"),
    "other": ("#2e8b57", "#ffffff"),
    "mcu": ("#e4e4e4", "#222222"),
    "dnp": ("#e4e4e4", "#9a9a9a"),
}
OUTLINED = ("name", "dnp", "mcu")
LEGEND = [
    ("Ground", "gnd"), ("Power", "power"), ("Communication", "comms"), ("Debug / SWD", "debug"),
    ("Other", "other"), ("MCU Pin", "mcu"),
    ("Not fitted", "dnp"),
]

ROW = 2.1  # label row pitch, mm
PILL_H = 1.6  # mm
FONT_PX = 25

# All layout coordinates below are in the rotated drawing frame: millimetres
# from the board centre, x to the right and y down. The rotated board spans
# about x = -16.5..16.5 and y = -28.5..28.5.
LEFT_X, RIGHT_X = -18.5, 18.5  # label anchor columns just outside the board

# Each label: footprint ref, pad number (None for the footprint centre),
# side ("L"/"R": pills grow left/right from the anchor; "T"/"B": pills sit
# above/below the leader, first pill centred on it), leader waypoints, the
# anchor, and the pills as (text, style). In waypoints and anchors, None means
# "keep the previous coordinate", so (RIGHT_X, None) is a straight horizontal
# leader from the pad.
LABELS = [
    # Right: analog test points and the gain trimmer
    ("TP14", "1", "R", [], (RIGHT_X, None), [("GND", "name"), ("GND", "gnd")]),
    ("TP6", "1", "R", [], (RIGHT_X, None), [("IntOut", "name"), ("Integrator out", "other"), ("PB0", "mcu")]),
    ("C15", None, "R", [], (RIGHT_X, None), [("C15", "name"), ("Gain trimmer", "other")]),
    ("TP11", "1", "R", [], (RIGHT_X, None), [("Rx", "name"), ("RX antenna", "other"), ("PA7", "mcu")]),
    ("TP7", "1", "R", [], (RIGHT_X, None), [("DAC", "name"), ("Bias (VREF)", "other"), ("PA4", "mcu")]),
    ("TP8", "1", "R", [], (RIGHT_X, None), [("FiltOut", "name"), ("Filter out", "other"), ("PA3", "mcu")]),
    ("TP9", "1", "R", [], (RIGHT_X, None), [("VDDA", "name"), ("Analog supply", "power")]),
    ("TP13", "1", "R", [(None, 16.4)], (RIGHT_X, 16.4), [("GND", "name"), ("GND", "gnd")]),
    # Top: LEDs
    ("D2", None, "T", [], (None, -30.6), [("GPIO", "name"), ("Status LED", "other"), ("PB13", "mcu")]),
    ("D1", None, "T", [], (None, -32.7), [("3V3", "name"), ("Power LED", "other")]),
    # Bottom: buttons
    ("SW1", None, "B", [], (None, 30.6), [("RST", "name"), ("NRST", "other")]),
    ("SW2", None, "B", [], (None, 32.7), [("BT0", "name"), ("BOOT0", "other")]),
    # Left: J2 main connector
    ("J2", "1", "L", [], (LEFT_X, None), [("GND", "gnd"), ("1", "name")]),
    ("J2", "2", "L", [], (LEFT_X, None), [("VIN", "power"), ("2", "name")]),
    ("J2", "3", "L", [], (LEFT_X, None), [("PC10", "mcu"), ("UART TX", "comms"), ("3", "name")]),
    ("J2", "4", "L", [], (LEFT_X, None), [("PC11", "mcu"), ("UART RX", "comms"), ("4", "name")]),
    ("J2", "5", "L", [], (LEFT_X, None), [("PC12", "mcu"), ("Unused", "dnp"), ("5", "name")]),
    # Left: J4, not fitted
    ("J4", "1", "L", [], (LEFT_X, None), [("GND", "dnp"), ("1", "dnp")]),
    ("J4", "2", "L", [], (LEFT_X, None), [("VIN", "dnp"), ("2", "dnp")]),
    ("J4", "3", "L", [], (LEFT_X, None), [("I2C SDA", "dnp"), ("3", "dnp")]),
    ("J4", "4", "L", [], (LEFT_X, None), [("I2C SCL", "dnp"), ("4", "dnp")]),
]

# J1 (Tag-Connect SWD) gets one leader to a bracketed pin table.
J1_TABLE_CENTRE_Y = -15.0
J1_ROWS = [
    ("1", [("3V3", "power")]),
    ("2", [("SWDIO", "debug"), ("PA13", "mcu")]),
    ("3", [("NRST", "other")]),
    ("4", [("SWCLK", "debug"), ("PA14", "mcu")]),
    ("5", [("GND", "gnd")]),
    ("6", [("SWO", "debug"), ("PB3", "mcu")]),
]

GROUP_TITLES = [  # (text, x, y, horizontal alignment)
    ("J1  ·  SWD (Tag-Connect TC2030)", LEFT_X, -21.9, "right"),
    ("J2  ·  JST PH 5-pin", LEFT_X, -6.6, "right"),
    ("J4  ·  JST PH 4-pin (I²C, not fitted)", LEFT_X, 9.0, "right"),
]

CANVAS = (-42.0, 42.0, -38.0, 40.0)  # x0, x1, y0, y1 in the rotated frame

DUMP_SCRIPT = r"""
import pcbnew, json, sys
b = pcbnew.LoadBoard(sys.argv[1])
bb = b.GetBoardEdgesBoundingBox()
out = {"edge": [pcbnew.ToMM(v) for v in (bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom())], "fps": {}}
for fp in b.GetFootprints():
    p = fp.GetPosition()
    out["fps"][fp.GetReference()] = {
        "x": pcbnew.ToMM(p.x), "y": pcbnew.ToMM(p.y),
        "pads": {pad.GetNumber(): [pcbnew.ToMM(pad.GetPosition().x), pcbnew.ToMM(pad.GetPosition().y)]
                 for pad in fp.Pads() if pad.GetNumber()},
    }
json.dump(out, open(sys.argv[2], "w"))
"""


def board_data(tmp):
    script = tmp / "dump.py"
    script.write_text(DUMP_SCRIPT)
    subprocess.run([str(KICAD_BIN / "python.exe"), str(script), str(BOARD), str(tmp / "board.json")], check=True)
    return json.loads((tmp / "board.json").read_text())


SUPERSAMPLE = 3  # the basic renderer doesn't anti-alias, so render large and scale down


def render(tmp):
    png = tmp / "render.png"
    subprocess.run([str(KICAD_BIN / "kicad-cli.exe"), "pcb", "render", "--side", "top", "--quality", "basic",
                    "--background", "transparent", "-w", str(2400 * SUPERSAMPLE), "-h", str(1500 * SUPERSAMPLE),
                    "-o", str(png), str(BOARD)],
                   check=True, capture_output=True)
    big = Image.open(png).convert("RGBA")
    # Resample with premultiplied alpha so transparent black doesn't bleed into the edges.
    size = (big.width // SUPERSAMPLE, big.height // SUPERSAMPLE)
    return big.convert("RGBa").resize(size, Image.Resampling.LANCZOS).convert("RGBA")


def calibrate(img, data):
    """Fit render px = s*mm + t from the gold annular rings of the mounting holes."""
    a = np.asarray(img).astype(int)
    gold = (a[..., 0] > 180) & (a[..., 1] > 150) & (a[..., 2] < 90) & (a[..., 3] > 200)
    lab, n = ndimage.label(gold)
    sizes = ndimage.sum(gold, lab, range(1, n + 1))
    rings = [ndimage.center_of_mass(gold, lab, i + 1)[::-1] for i in np.argsort(sizes)[::-1][:4]]
    mm = [[data["fps"][r]["x"], data["fps"][r]["y"]] for r in CAL_REFS]
    # order both sets as top-left, top-right, bottom-left, bottom-right
    order = lambda pts: np.array(sorted(pts, key=lambda c: (c[1] > np.mean([p[1] for p in pts]), c[0])))
    px, mm_sorted = order(rings), order(mm)
    sx, tx = np.polyfit(mm_sorted[:, 0], px[:, 0], 1)
    sy, ty = np.polyfit(mm_sorted[:, 1], px[:, 1], 1)
    resid = np.abs(np.c_[sx * mm_sorted[:, 0] + tx - px[:, 0], sy * mm_sorted[:, 1] + ty - px[:, 1]]).max()
    assert resid < 2 and abs(sx / sy - 1) < 0.01, f"calibration failed (residual {resid:.1f} px)"
    return (sx + sy) / 2, tx, ty


def main():
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        data = board_data(tmp)
        img = render(tmp)
    s, tx, ty = calibrate(img, data)

    e = data["edge"]
    cx, cy = (e[0] + e[2]) / 2, (e[1] + e[3]) / 2
    rot = lambda x, y: (-(y - cy), x - cx)  # board mm -> rotated frame (90 degrees clockwise)

    X0, X1, Y0, Y1 = CANVAS
    W, H = (X1 - X0) * s, (Y1 - Y0) * s
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    ax.axis("off")
    fig.patch.set_facecolor("white")
    renderer = fig.canvas.get_renderer()

    P = lambda x, y: ((x - X0) * s, (y - Y0) * s)  # rotated frame mm -> canvas px

    # Place the rotated render. Its left edge is the original bottom edge, its
    # top edge the original left edge.
    x_lo, x_hi = (0 - tx) / s, (img.width - tx) / s
    y_lo, y_hi = (0 - ty) / s, (img.height - ty) / s
    left, top = rot(x_lo, y_hi)[0], rot(x_lo, y_lo)[1]
    right, bottom = rot(x_lo, y_lo)[0], rot(x_hi, y_lo)[1]
    # Composite onto white first: resampling an image with transparency gives dark fringes.
    board = Image.new("RGBA", img.size, "white")
    board.alpha_composite(img)
    ax.imshow(board.convert("RGB").rotate(-90, expand=True),
              extent=(P(left, 0)[0], P(right, 0)[0], P(0, bottom)[1], P(0, top)[1]),
              zorder=1, interpolation="lanczos")

    def pills_at(x, y, side, pills):
        """Draw a row of pills at anchor (x, y) px; returns nothing."""
        pad, gap, h = 0.45 * s, 0.25 * s, PILL_H * s
        texts = []
        for text, style in pills:
            fill, fg = STYLE[style]
            txt = ax.text(0, 0, text, fontsize=FONT_PX * 72 / 100, fontweight="bold", color=fg,
                          ha="center", va="center", family="DejaVu Sans", zorder=4)
            texts.append((txt, txt.get_window_extent(renderer).width + 2 * pad, style))
        if side == "L":
            cur = x - gap - sum(w for _, w, _ in texts) - gap * (len(texts) - 1)
        elif side == "R":
            cur = x + gap
        else:  # "T"/"B": first pill centred on the leader
            cur = x - texts[0][1] / 2
        for txt, w, style in texts:
            fill, _ = STYLE[style]
            txt.set_position((cur + w / 2, y))
            ax.add_patch(FancyBboxPatch((cur, y - h / 2), w, h, boxstyle=f"round,pad=0,rounding_size={h * 0.3}",
                                        fc=fill, ec="#555555" if style in OUTLINED else fill, lw=1.2, zorder=3))
            cur += w + gap

    def leader(points, grey=False):
        xs, ys = zip(*[P(*p) for p in points])
        c = "#b0b0b0" if grey else "#333333"
        ax.plot(xs, ys, color=c, lw=2, zorder=2, solid_capstyle="round")
        ax.plot(xs[0], ys[0], "o", ms=9, mfc="white", mec=c, mew=2, zorder=2.5)

    for ref, pad, side, route, anchor, pills in LABELS:
        fp = data["fps"][ref]
        start = rot(*(fp["pads"][pad] if pad else (fp["x"], fp["y"])))
        pts, cur = [start], start
        for wx, wy in list(route) + [anchor]:
            cur = (cur[0] if wx is None else wx, cur[1] if wy is None else wy)
            pts.append(cur)
        ax_, ay = pts[-1]
        if side in ("T", "B"):  # stop the leader at the pill edge
            pts[-1] = (ax_, ay + (PILL_H / 2 if side == "T" else -PILL_H / 2))
        leader(pts, grey=all(st == "dnp" for _, st in pills))
        pills_at(*P(ax_, ay), side, pills)

    # J1: one leader to a bracket, then a pin table
    j1 = rot(data["fps"]["J1"]["x"], data["fps"]["J1"]["y"])
    leader([j1, (LEFT_X, j1[1])])
    rows_y = [J1_TABLE_CENTRE_Y + (i - (len(J1_ROWS) - 1) / 2) * ROW for i in range(len(J1_ROWS))]
    for y, (num, pills) in zip(rows_y, J1_ROWS):
        pills_at(*P(LEFT_X, y), "L", pills + [(num, "name")])
    bx = P(LEFT_X, 0)[0]
    ax.plot([bx, bx], [P(0, rows_y[0])[1], P(0, rows_y[-1])[1]], color="#333333", lw=2, zorder=2)

    for text, x, y, ha in GROUP_TITLES:
        ax.text(*P(x - 0.25, y), text, fontsize=20 * 72 / 100, fontweight="bold", color="#444444", ha=ha,
                va="bottom", family="DejaVu Sans", zorder=4)

    ax.text(*P(X0 + 2, Y0 + 2.5), "Open Linear Scale  ·  Sensor PCB", fontsize=40 * 72 / 100,
            fontweight="bold", color="#222222", va="center", family="DejaVu Sans")
    ax.text(*P(X0 + 2, Y0 + 5.2), "Top view", fontsize=24 * 72 / 100, color="#666666", va="center",
            family="DejaVu Sans")

    for i, (text, style) in enumerate(LEGEND):  # legend, bottom right
        pills_at(*P(22.0, 21.0 + i * ROW), "R", [(text, style)])

    for ext in ("png", "svg"):
        fig.savefig(OUT_DIR / f"sensor-pinout.{ext}", dpi=100, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    main()
