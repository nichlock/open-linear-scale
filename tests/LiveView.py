import argparse
import queue
import struct
import sys
import threading
import time
from collections import deque
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import serial
from matplotlib.lines import Line2D

sys.path.insert(0, str(Path(__file__).parent / "src"))
from AccuracyAnalysis import estimatePosition, NUM_EMITTERS, PERIOD_SIZE_MM

HISTORY_SECONDS = 10.0
MAX_CONSECUTIVE_BAD_ROWS = 50
REDRAW_INTERVAL_SECONDS = 0.05

DEBUG_LOG_INPUT = True
DEBUG_LOG_FILENAME = "liveview_debug.log"
SAMPLE_PERIOD_SECONDS = 0.001


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("port", nargs="?", default="COM4")
    parser.add_argument("--baudrate", type=int, default=460800)
    parser.add_argument("--timeout", type=float, default=2.0)
    return parser.parse_args()


def parse_known_mode(raw,  mode):
    if mode == "raw":
        fields = raw.split(",")
        if len(fields) != 8:
            return float("nan"), [float("nan")] * 4, [float("nan")] * 4, False
        try:
            values = [int(field) for field in fields]
        except ValueError:
            return float("nan"), [float("nan")] * 4, [float("nan")] * 4, False
        # if any(abs(value) > 1000 for value in values):
        #     return float("nan"), [float("nan")] * 4, [float("nan")] * 4, False
        position = estimatePosition(np.array([values]))[0]
        lane0 = [values[0], values[1], values[2], values[3]]
        lane1 = [values[4], values[5], values[6], values[7]]
        return position * (PERIOD_SIZE_MM / NUM_EMITTERS), lane0, lane1, True

    if mode == "indexed":
        # rd,reading[0..7],checksum where checksum == sum(reading[0..7])
        fields = raw.split(",")
        if len(fields) != 10:
            return float("nan"), [float("nan")] * 4, [float("nan")] * 4, False
        try:
            values = [int(field) for field in fields]
        except ValueError:
            return float("nan"), [float("nan")] * 4, [float("nan")] * 4, False
        readings = values[1:9]
        checksum = values[9]
        if checksum != sum(readings):
            return float("nan"), [float("nan")] * 4, [float("nan")] * 4, False
        position = estimatePosition(np.array([readings]))[0]
        lane0 = [readings[0], readings[1], readings[2], readings[3]]
        lane1 = [readings[4], readings[5], readings[6], readings[7]]
        return position * (PERIOD_SIZE_MM / NUM_EMITTERS), lane0, lane1, True

    # Firmware sends the IEEE-754 bit pattern of a 32-bit float as 8 hex digits
    if len(raw) != 8:
        return float("nan"), None, None, False
    try:
        position = struct.unpack(">f", bytes.fromhex(raw))[0]
    except ValueError:
        return float("nan"), None, None, False
    return position, None, None, True


def detect_mode(raw):
    for candidate in ("raw", "indexed", "hex"):
        position, lane0, lane1, ok = parse_known_mode(raw, candidate)
        if ok:
            return candidate, position, lane0, lane1
    return None


def reader_loop(ser, start_time, out_queue, debug_log):
    consecutive_bad_rows = 0
    sample_index = 0

    def read_line():
        raw = ser.readline().decode("ascii", errors="replace").strip()
        if raw and debug_log is not None:
            debug_log.write(f"{time.monotonic() - start_time:.6f} {raw}\n")
            debug_log.flush()
        return raw

    mode = None
    while mode is None:
        raw = read_line()
        if not raw:
            continue
        detected = detect_mode(raw)
        if detected is None:
            consecutive_bad_rows += 1
            if consecutive_bad_rows >= MAX_CONSECUTIVE_BAD_ROWS:
                out_queue.put(RuntimeError(f"{MAX_CONSECUTIVE_BAD_ROWS} consecutive malformed rows received"))
                return
            continue
        mode, position, lane0, lane1 = detected
        print(f"Detected {mode} mode")
        consecutive_bad_rows = 0
        out_queue.put((sample_index * SAMPLE_PERIOD_SECONDS, position, lane0, lane1))
        sample_index += 1

    while True:
        raw = read_line()
        if not raw:
            continue
        position, lane0, lane1, ok = parse_known_mode(raw, mode)
        if ok:
            consecutive_bad_rows = 0
        else:
            consecutive_bad_rows += 1
            if consecutive_bad_rows >= MAX_CONSECUTIVE_BAD_ROWS:
                out_queue.put(RuntimeError(f"{MAX_CONSECUTIVE_BAD_ROWS} consecutive malformed rows received"))
                return
        out_queue.put((sample_index * SAMPLE_PERIOD_SECONDS, position, lane0, lane1))
        sample_index += 1


class CursorTool:
    """Click two points in an axes to show a delta readout (x1, x2, dx, 1/dx, y1, y2)."""

    def __init__(self, ax):
        self.ax = ax
        self.points = []
        # Added via add_artist (not ax.plot/add_line) so these never feed
        # relim()/autoscale_view() - otherwise a cursor placed on data that
        # later scrolls out of the time window would pin the y autoscale.
        self.vlines = [Line2D([], [], color="0.5", linestyle="--", linewidth=1) for _ in range(2)]
        self.markers = [Line2D([], [], marker="o", linestyle="none", color="red", markersize=5) for _ in range(2)]
        for artist in (*self.vlines, *self.markers):
            ax.add_artist(artist)
        self.text = ax.text(
            0.02,
            0.98,
            "",
            transform=ax.transAxes,
            va="top",
            ha="left",
            fontsize=9,
            family="monospace",
            visible=False,
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.8, edgecolor="0.5"),
        )

    def on_click(self, event):
        toolbar = getattr(event.canvas, "toolbar", None)
        if toolbar is not None and toolbar.mode:
            return
        if event.inaxes is not self.ax or event.xdata is None or event.ydata is None:
            return
        if len(self.points) >= 2:
            self.points = []
        self.points.append((event.xdata, event.ydata))
        self.refresh()

    def refresh(self):
        ylim = self.ax.get_ylim()
        for i in range(2):
            if i < len(self.points):
                x, y = self.points[i]
                self.vlines[i].set_data([x, x], ylim)
                self.markers[i].set_data([x], [y])
            else:
                self.vlines[i].set_data([], [])
                self.markers[i].set_data([], [])

        if len(self.points) == 2:
            (x1, y1), (x2, y2) = self.points
            diff = x1 - x2
            freq = (1.0 / diff) if diff != 0 else float("nan")
            ratio = (y1 / y2) if y2 != 0 else float("nan")
            self.text.set_text(
                f"x1       = {x1:.4f} s\n"
                f"x2       = {x2:.4f} s\n"
                f"x1-x2    = {diff * 1000:.3f} ms\n"
                f"1/(x1-x2)= {freq:.3f} Hz\n"
                f"y1       = {y1:.4g}\n"
                f"y2       = {y2:.4g}\n"
                f"y1/y2    = {ratio:.4g}"
            )
            self.text.set_visible(True)
        else:
            self.text.set_visible(False)


def main():
    args = parse_args()

    times = deque()
    positions = deque()
    transient_times = deque()
    transients_lane0 = deque()
    transients_lane1 = deque()
    out_queue = queue.Queue()

    plt.ion()
    fig, ax = plt.subplots()
    line, = ax.plot([], [])
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Position (mm)")

    transient_fig, transient_axes = plt.subplots(2, sharex=True)
    lane_lines = [
        [ax.plot([], [], label=f"transient {i}")[0] for i in range(4)]
        for ax in transient_axes
    ]
    for lane, lane_ax in enumerate(transient_axes):
        lane_ax.set_title(f"Lane {lane}")
        lane_ax.set_ylabel("Transient value")
    transient_axes[-1].set_xlabel("Time (s)")

    position_cursor = CursorTool(ax)
    transient_cursors = [CursorTool(lane_ax) for lane_ax in transient_axes]

    stop_event = threading.Event()

    def on_key_press(event):
        stop_event.set()

    fig.canvas.mpl_connect("key_press_event", on_key_press)
    transient_fig.canvas.mpl_connect("key_press_event", on_key_press)
    fig.canvas.mpl_connect("button_press_event", position_cursor.on_click)
    for transient_cursor in transient_cursors:
        transient_fig.canvas.mpl_connect("button_press_event", transient_cursor.on_click)

    debug_log = open(DEBUG_LOG_FILENAME, "w") if DEBUG_LOG_INPUT else None

    with serial.Serial(args.port, args.baudrate, timeout=args.timeout) as ser:
        start_time = time.monotonic()
        thread = threading.Thread(target=reader_loop, args=(ser, start_time, out_queue, debug_log), daemon=True)
        thread.start()

        now = 0.0
        print("Press any key in a plot window to stop capturing.")
        try:
            while not stop_event.is_set():
                while True:
                    try:
                        item = out_queue.get_nowait()
                    except queue.Empty:
                        break
                    if isinstance(item, Exception):
                        raise item
                    now, position, lane0, lane1 = item
                    times.append(now)
                    positions.append(position)
                    if lane0 is not None:
                        transient_times.append(now)
                        transients_lane0.append(lane0)
                        transients_lane1.append(lane1)

                if times:
                    now = times[-1]
                    while now - times[0] > HISTORY_SECONDS:
                        times.popleft()
                        positions.popleft()

                    line.set_data(times, positions)
                    ax.set_xlim(max(0, now - HISTORY_SECONDS), max(now, HISTORY_SECONDS))
                    ax.relim()
                    ax.autoscale_view(scalex=False, scaley=True)

                while transient_times and transient_times[0] < now - HISTORY_SECONDS:
                    transient_times.popleft()
                    transients_lane0.popleft()
                    transients_lane1.popleft()

                if transient_times:
                    for lane_transients, lines in zip(
                        (transients_lane0, transients_lane1), lane_lines
                    ):
                        lane_array = np.array(lane_transients)
                        for i, transient_line in enumerate(lines):
                            transient_line.set_data(transient_times, lane_array[:, i])
                    for lane_ax in transient_axes:
                        lane_ax.set_xlim(max(0, now - HISTORY_SECONDS), max(now, HISTORY_SECONDS))
                        lane_ax.relim()
                        lane_ax.autoscale_view(scalex=False, scaley=True)

                position_cursor.refresh()
                for transient_cursor in transient_cursors:
                    transient_cursor.refresh()

                for f in (fig, transient_fig):
                    f.canvas.draw_idle()
                    f.canvas.flush_events()
                time.sleep(REDRAW_INTERVAL_SECONDS)
        except RuntimeError as error:
            print(f"error: {error}", file=sys.stderr)
            sys.exit(1)
        except KeyboardInterrupt:
            pass

    print("Capture stopped, close the plot windows to exit.")
    plt.ioff()
    plt.show()


if __name__ == "__main__":
    main()
