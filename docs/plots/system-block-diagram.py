"""Simple system block diagram for the README: the MCU drives the emitters, the
signal couples capacitively through the reflector to the sensor grid, and the
measurement comes back through the analog front end to the MCU and out over UART."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # render to file only; never open a window

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT_DIR = Path(__file__).resolve().parent

BOX_W, BOX_H = 1.6, 0.9
COL_PITCH = BOX_W + 1.4  # wide gaps leave room for the coupling symbols
ROW_Y = {"top": 1.9, "bottom": 0.0}

# name: (label, column, row)
BLOCKS = {
    "host": ("Host", 0, "bottom"),
    "mcu": ("MCU", 1, "bottom"),
    "analog": ("Analog\nsensing", 3, "bottom"),
    "emitter": ("Emitter", 1, "top"),
    "reflector": ("Reflector", 2, "top"),
    "grid": ("Sensor\ngrid", 3, "top"),
}

C_FILL = "#eef3f9"
C_EDGE = "#333333"
C_COUPLE = "#e8731c"  # capacitive (wireless) links stand out from wired ones


def box(name):
    _, col, row = BLOCKS[name]
    return col * COL_PITCH, ROW_Y[row]


def side(name, where):
    """Midpoint of a box edge: 'left', 'right', 'top' or 'bottom'."""
    x, y = box(name)
    return {"left": (x, y + BOX_H / 2), "right": (x + BOX_W, y + BOX_H / 2),
            "top": (x + BOX_W / 2, y + BOX_H), "bottom": (x + BOX_W / 2, y)}[where]


def wire(ax, start, end, label=None, label_side="top"):
    ax.add_patch(FancyArrowPatch(start, end, arrowstyle="-|>", mutation_scale=14, lw=1.6,
                                 color=C_EDGE, shrinkA=0, shrinkB=2))
    if label:
        mx, my = (start[0] + end[0]) / 2, (start[1] + end[1]) / 2
        if label_side == "top":
            ax.text(mx, my + 0.1, label, ha="center", va="bottom", fontsize=11)
        else:
            ax.text(mx + 0.1, my, label, ha="left", va="center", fontsize=11)


def coupling(ax, start, end):
    """Horizontal link drawn as a capacitor: two plates with no wire between them."""
    (x0, y), (x1, _) = start, end
    xm, gap, plate_h = (x0 + x1) / 2, 0.09, 0.5
    kw = dict(color=C_COUPLE, lw=2.0, solid_capstyle="butt")
    ax.plot([x0, xm - gap], [y, y], **kw)
    ax.plot([xm - gap] * 2, [y - plate_h / 2, y + plate_h / 2], color=C_COUPLE, lw=3.0)
    ax.plot([xm + gap] * 2, [y - plate_h / 2, y + plate_h / 2], color=C_COUPLE, lw=3.0)
    ax.add_patch(FancyArrowPatch((xm + gap, y), end, arrowstyle="-|>", mutation_scale=14,
                                 lw=2.0, color=C_COUPLE, shrinkA=0, shrinkB=2))
    ax.text(xm, y + plate_h / 2 + 0.08, "capacitive\ncoupling", ha="center", va="bottom",
            fontsize=9.5, style="italic", color=C_COUPLE, linespacing=1.0)


def main():
    width = 3 * COL_PITCH + BOX_W
    height = ROW_Y["top"] + BOX_H
    fig, ax = plt.subplots(figsize=(width * 0.8, (height + 0.6) * 0.8))

    for name, (label, _, _) in BLOCKS.items():
        x, y = box(name)
        ax.add_patch(FancyBboxPatch((x, y), BOX_W, BOX_H, boxstyle="round,pad=0,rounding_size=0.12",
                                    fc=C_FILL, ec=C_EDGE, lw=1.6, zorder=2))
        ax.text(x + BOX_W / 2, y + BOX_H / 2, label, ha="center", va="center", fontsize=12,
                linespacing=1.1, zorder=3)

    wire(ax, side("mcu", "top"), side("emitter", "bottom"), "drive", label_side="right")
    coupling(ax, side("emitter", "right"), side("reflector", "left"))
    coupling(ax, side("reflector", "right"), side("grid", "left"))
    wire(ax, side("grid", "bottom"), side("analog", "top"))
    wire(ax, side("analog", "left"), side("mcu", "right"))
    wire(ax, side("mcu", "left"), side("host", "right"), "UART")

    ax.set_xlim(-0.05, width + 0.05)
    ax.set_ylim(-0.05, height + 0.05)
    ax.set_aspect("equal")
    ax.axis("off")
    for ext in ("png", "svg"):
        fig.savefig(OUT_DIR / f"system-block-diagram.{ext}", dpi=150, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
