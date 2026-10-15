"""Sensor/reflector copper overlap figure.

Renders the sensor's grid side and the reflector's pad side with kicad-cli,
finds the copper in each render, and composites the two boards as they sit in
the assembly, with the sensor drawn semi-transparent so the overlapping copper
shows through.

Copper is found from a second render of each board made with a translucent
solder mask (set in a temporary copy of the board's stackup), where copper is a
single flat colour. The boards' millimetre calibration comes from the render's
visible area, which matches each board outline exactly.

Requires KiCad 9 installed at KICAD_BIN.
"""
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # render to file only; never open a window

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, Patch
from PIL import Image
from scipy import ndimage

OUT_DIR = Path(__file__).resolve().parent
HW = OUT_DIR.parents[1] / "hardware"
SENSOR = HW / "sensor-pcb" / "sensor-pcb.kicad_pcb"
REFLECTOR = HW / "reflector-pcb-sm" / "reflector-pcb-sm.kicad_pcb"
KICAD_BIN = Path(r"C:\Program Files\KiCad\9.0\bin")

# Reflector position relative to the sensor, in mm. The y offset is the designed
# alignment: it puts the top of the T crossbars on the top edge of the RX pad and
# the bottom of the T stems on the bottom edge of the emitter grid. The x offset
# is arbitrary (it is the position being measured); this one centres the
# reflector copper under the grid, plus a fraction of an emitter.
REFLECTOR_OFFSET = (75.35, 14.3)

EMITTER_PITCH = 0.635  # mm
MASK_COLOR = "#1A6B3A33"  # translucent solder mask for the copper-finding renders
RENDER = ["-w", "7200", "-h", "4500", "--zoom", "1.6"]

COL_EMITTER = (0.18, 0.44, 0.86)
COL_RX = (0.56, 0.27, 0.68)
COL_T = (0.91, 0.53, 0.16)
COL_FILLER = (0.70, 0.62, 0.52)

STACKUP = """\t\t(stackup
\t\t\t(layer "F.Mask" (type "Top Solder Mask") (color "{c}") (thickness 0.01))
\t\t\t(layer "F.Cu" (type "copper") (thickness 0.035))
\t\t\t(layer "dielectric 1" (type "core") (thickness 1.51) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
\t\t\t(layer "B.Cu" (type "copper") (thickness 0.035))
\t\t\t(layer "B.Mask" (type "Bottom Solder Mask") (color "{c}") (thickness 0.01))
\t\t\t(copper_finish "None")
\t\t\t(dielectric_constraints no)
\t\t)
"""

GEOM_SCRIPT = r"""
import pcbnew, json, sys
out = {}
for key, path in (("sensor", sys.argv[1]), ("reflector", sys.argv[2])):
    b = pcbnew.LoadBoard(path)
    bb = b.GetBoardEdgesBoundingBox()
    d = {"edge": [pcbnew.ToMM(v) for v in (bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom())], "zones": {}}
    for z in b.Zones():
        if z.IsOnLayer(b.GetLayerID("B.Cu")):
            zb = z.GetBoundingBox()
            box = [pcbnew.ToMM(v) for v in (zb.GetLeft(), zb.GetTop(), zb.GetRight(), zb.GetBottom())]
            old = d["zones"].get(z.GetNetname())
            d["zones"][z.GetNetname()] = box if old is None else [min(old[0], box[0]), min(old[1], box[1]), max(old[2], box[2]), max(old[3], box[3])]
    out[key] = d
json.dump(out, open(sys.argv[3], "w"))
"""


def translucent_copy(board, tmp):
    """Copy a board with its solder mask made translucent, so copper renders as a flat colour."""
    dst = tmp / board.name
    shutil.copy(board.with_suffix(".kicad_pro"), dst.with_suffix(".kicad_pro"))
    t = board.read_text(encoding="utf-8")
    if "(stackup" in t:
        for m in ("F.Mask", "B.Mask"):
            t = re.sub(r'(\(layer "%s"\s*\n\s*\(type "[^"]+"\))' % re.escape(m), r'\1\n\t\t\t\t(color "%s")' % MASK_COLOR,
                       t, count=1)
    else:
        t = t.replace("\t(setup\n", "\t(setup\n" + STACKUP.format(c=MASK_COLOR), 1)
    dst.write_text(t, encoding="utf-8")
    return dst


def render(board, side, out, stackup_colors=False):
    cmd = [str(KICAD_BIN / "kicad-cli.exe"), "pcb", "render", "--side", side, "--quality", "basic",
           "--background", "transparent", *RENDER, "-o", str(out), str(board)]
    if stackup_colors:
        cmd.insert(-1, "--use-board-stackup-colors")
    subprocess.run(cmd, check=True, capture_output=True)
    img = Image.open(out).convert("RGBA")
    x0, y0, x1, y1 = img.getbbox()
    assert x0 > 0 and y0 > 0 and x1 < img.width and y1 < img.height, f"{board.name} render is clipped"
    return img


class Placed:
    """A board render with its pixel <-> board-mm calibration (top-view frame)."""

    def __init__(self, img, edge):
        x0, y0, x1, y1 = img.getbbox()
        self.img, self.edge = img, edge
        self.s = (x1 - x0) / (edge[2] - edge[0])
        sy = (y1 - y0) / (edge[3] - edge[1])
        assert abs(self.s / sy - 1) < 0.01, "render scale is not square"
        self.tx, self.ty = x0 - self.s * edge[0], y0 - self.s * edge[1]

    def px(self, x, y):
        return self.s * x + self.tx, self.s * y + self.ty

    def warp(self, img, window, scale, offset=(0.0, 0.0), resample=Image.Resampling.BICUBIC):
        """Resample `img` (same frame as self.img) into a canvas covering `window` (mm) at `scale` px/mm."""
        X0, Y0, X1, Y1 = window
        size = (round((X1 - X0) * scale), round((Y1 - Y0) * scale))
        k = self.s / scale
        data = (k, 0, self.s * (X0 - offset[0]) + self.tx, 0, k, self.s * (Y0 - offset[1]) + self.ty)
        mode = "RGBa" if img.mode == "RGBA" else img.mode
        out = img.convert(mode).transform(size, Image.Transform.AFFINE, data, resample=resample)
        return out.convert("RGBA") if mode == "RGBa" else out


def copper_mask(img):
    a = np.asarray(img).astype(int)
    return (a[..., 0] > 130) & (a[..., 3] > 128)


def box_mask(placed, shape, box, pad=0.0):
    m = np.zeros(shape, bool)
    x0, y0 = placed.px(box[0] - pad, box[1] - pad)
    x1, y1 = placed.px(box[2] + pad, box[3] + pad)
    m[int(y0):int(np.ceil(y1)), int(x0):int(np.ceil(x1))] = True
    return m


def main():
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        (tmp / "geom.py").write_text(GEOM_SCRIPT)
        subprocess.run([str(KICAD_BIN / "python.exe"), str(tmp / "geom.py"), str(SENSOR), str(REFLECTOR),
                        str(tmp / "geom.json")], check=True, capture_output=True)
        geom = json.loads((tmp / "geom.json").read_text())
        s_clear, r_clear = translucent_copy(SENSOR, tmp), translucent_copy(REFLECTOR, tmp)
        # The bottom view is mirrored; flip it so both boards share KiCad's top-view coordinates.
        flip = lambda im: im.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        s_img = flip(render(SENSOR, "bottom", tmp / "s.png"))
        s_cu = flip(render(s_clear, "bottom", tmp / "sc.png", True))
        r_img = render(REFLECTOR, "top", tmp / "r.png")
        r_cu = render(r_clear, "top", tmp / "rc.png", True)

    S = Placed(s_img, geom["sensor"]["edge"])
    R = Placed(r_img, geom["reflector"]["edge"])
    zones = geom["sensor"]["zones"]
    grid = [min(v[i] for k, v in zones.items() if k.startswith("/EM")) if i < 2 else
            max(v[i] for k, v in zones.items() if k.startswith("/EM")) for i in range(4)]
    rx = zones["/A_INTGR_INV"]

    # Copper masks (in each render's own pixel frame)
    scu = copper_mask(s_cu)
    m_emit = scu & box_mask(S, scu.shape, grid)
    m_rx = scu & box_mask(S, scu.shape, rx)
    rcu = copper_mask(r_cu)
    lab, n = ndimage.label(rcu)
    crossbar_row = int(R.px(0, 91.5)[1])  # T crossbars sit above this; filler bars start below it
    t_ids = set(np.unique(lab[:crossbar_row][rcu[:crossbar_row]]))
    m_t = np.isin(lab, list(t_ids)) & rcu
    m_fill = rcu & ~m_t

    to_img = lambda m: Image.fromarray((m * 255).astype(np.uint8), "L")

    def layer(placed, mask, window, scale, offset=(0.0, 0.0)):
        return np.asarray(placed.warp(to_img(mask), window, scale, offset, Image.Resampling.BILINEAR)) / 255.0

    def tint(base, mask, color, alpha):
        a = (mask * alpha)[..., None]
        return base * (1 - a) + np.array(color) * a

    def board(placed, window, scale, offset=(0.0, 0.0), opacity=1.0, base=None):
        im = np.asarray(placed.warp(placed.img, window, scale, offset)).astype(float) / 255.0
        a = im[..., 3:4] * opacity
        base = np.ones(im.shape[:2] + (3,)) if base is None else base
        return base * (1 - a) + im[..., :3] * a

    def single(placed, window, scale, masks, mirror=False):
        out = board(placed, window, scale)
        for m, col in masks:
            out = tint(out, layer(placed, m, window, scale), col, 0.85)
        return out[:, ::-1] if mirror else out

    def outline(mask_layer, width_px):
        m = mask_layer > 0.5
        return (m & ~ndimage.binary_erosion(m, iterations=width_px)).astype(float)

    def assembled(window, scale, outlined=False):
        off = REFLECTOR_OFFSET
        out = board(R, window, scale, off)
        out = out * 0.45 + 0.55  # fade the reflector body so the copper colours stand out
        out = tint(out, layer(R, m_fill, window, scale, off), COL_FILLER, 0.8)
        out = tint(out, layer(R, m_t, window, scale, off), COL_T, 0.9)
        out = board(S, window, scale, opacity=0.2, base=out)  # sensor body, see-through
        emit, rxl = layer(S, m_emit, window, scale), layer(S, m_rx, window, scale)
        if outlined:  # light fill plus a solid outline, so the reflector copper reads through
            w = max(2, round(scale / 30))
            out = tint(out, emit, COL_EMITTER, 0.25)
            out = tint(out, outline(emit, w), COL_EMITTER, 1.0)
            out = tint(out, rxl, COL_RX, 0.3)
            out = tint(out, outline(rxl, w), COL_RX, 1.0)
        else:
            out = tint(out, emit, COL_EMITTER, 0.6)
            out = tint(out, rxl, COL_RX, 0.6)
        return out

    # Emitter strips and their index (EM0..EM7), from the copper mask
    lab_e, n_e = ndimage.label(m_emit)
    strip_x = sorted((ndimage.center_of_mass(m_emit, lab_e, i + 1)[1] - S.tx) / S.s for i in range(n_e))
    strip_x = [x for x in strip_x if x > 0]
    x_first = strip_x[0]
    emitter_index = lambda x: round((x - x_first) / EMITTER_PITCH) % 8

    se, re_ = S.edge, R.edge
    pad = 1.0
    win_s = (se[0] - pad, se[1] - pad, se[2] + pad, se[3] + pad)
    win_r = (re_[0] - pad, re_[1] - pad, re_[2] + pad, re_[3] + pad)
    rx_off = (re_[0] + REFLECTOR_OFFSET[0], re_[2] + REFLECTOR_OFFSET[0])
    win_a = (min(se[0], rx_off[0]) - pad, se[1] - pad, max(se[2], rx_off[1]) + pad, se[3] + 3.4)
    period = 8 * EMITTER_PITCH
    zx = x_first - EMITTER_PITCH / 2 + 2 * period  # start the detail on a period boundary
    win_z = (zx - 0.2, rx[1] - 1.2, zx + 3 * period + 0.2, grid[3] + 1.6)

    # Every image is rendered at the same pixel width, so text reads the same size in the README.
    WIDTH_PX = 1800
    sc = lambda win: WIDTH_PX / (win[2] - win[0])
    img_s = single(S, win_s, sc(win_s), [(m_emit, COL_EMITTER), (m_rx, COL_RX)], mirror=True)
    img_r = single(R, win_r, sc(win_r), [(m_fill, COL_FILLER), (m_t, COL_T)])
    img_a = assembled(win_a, sc(win_a))
    img_z = assembled(win_z, sc(win_z), outlined=True)

    LEG = {"emit": Patch(color=COL_EMITTER, label="Emitters (sensor)"), "rx": Patch(color=COL_RX, label="RX pad (sensor)"),
           "t": Patch(color=COL_T, label="T pads (reflector)"), "fill": Patch(color=COL_FILLER, label="Filler copper (reflector)")}

    def save(name, im, win, legend, mirror=False, decorate=None):
        """Save one panel at the image's own resolution, with a legend strip underneath."""
        h_px, w_px = im.shape[:2]
        legend_px = 100
        fig = plt.figure(figsize=(w_px / 100, (h_px + legend_px) / 100), dpi=100)
        ax = fig.add_axes([0, legend_px / (h_px + legend_px), 1, h_px / (h_px + legend_px)])
        x0, y0, x1, y1 = win
        ax.imshow(np.clip(im, 0, 1), extent=(x1, x0, y1, y0) if mirror else (x0, x1, y1, y0),
                  interpolation="antialiased")
        ax.set_xlim(x1, x0) if mirror else ax.set_xlim(x0, x1)
        ax.set_ylim(y1, y0)
        ax.axis("off")
        if decorate:
            decorate(ax)
        fig.legend(handles=[LEG[k] for k in legend], loc="lower center", ncol=len(legend), fontsize=19,
                   frameon=False, bbox_to_anchor=(0.5, 0.0), handlelength=1.6, columnspacing=1.8)
        fig.savefig(OUT_DIR / f"{name}.png", dpi=100, facecolor="white")
        plt.close(fig)

    save("sensor-grid-side", img_s[:, ::-1], win_s, ["emit", "rx"], mirror=True)
    save("reflector-pad-side", img_r, win_r, ["t", "fill"])

    def deco_assembled(ax):
        e = se
        ax.plot([e[0], e[2], e[2], e[0], e[0]], [e[1], e[1], e[3], e[3], e[1]], color="#1d4d2b", lw=1.5, ls="--")
        ax.text(e[2] - 0.5, e[1] + 0.6, "sensor outline", ha="right", va="top", fontsize=17, color="#1d4d2b")
        arrow_y = se[3] + 1.4
        ax.add_patch(FancyArrowPatch((rx_off[0] + 4, arrow_y), (rx_off[1] - 4, arrow_y), arrowstyle="<|-|>",
                                     mutation_scale=26, color="#555555", lw=2.2))
        ax.text((rx_off[0] + rx_off[1]) / 2, arrow_y + 0.5, "reflector travel", ha="center", va="top",
                fontsize=18, color="#555555")

    save("assembled", img_a, win_a, ["emit", "rx", "t", "fill"], decorate=deco_assembled)

    def deco_detail(ax):
        for x in strip_x:
            if win_z[0] + 0.2 < x < win_z[2] - 0.2:
                ax.text(x, grid[3] + 0.65, str(emitter_index(x)), ha="center", va="center", fontsize=17,
                        color=COL_EMITTER, fontweight="bold")
        ax.text(win_z[0] + 0.25, grid[3] + 1.25, "Emitter index (EM0 to EM7)", ha="left", va="center", fontsize=18,
                color=COL_EMITTER)
        ax.text(win_z[0] + 0.25, rx[1] - 0.6, "RX pad", ha="left", va="center", fontsize=19, color=COL_RX,
                fontweight="bold")

    save("detail", img_z, win_z, ["emit", "rx", "t", "fill"], decorate=deco_detail)


if __name__ == "__main__":
    main()
