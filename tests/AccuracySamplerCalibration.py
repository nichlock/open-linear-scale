import argparse
import json
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

import serial

READER_SCRIPT = Path(__file__).parent / "ImpuleReader.py"
# Printed by ImpuleReader once the header is found and sample data starts.
READER_SAMPLING_MARKER = "Reading samples..."

ABS_Z_MIN = 0
ABS_Z_MAX = 200

SENSOR_PORT = "COM4"
PRINTER_PORT = "COM6"
PRINTER_BAUD = 115200
GAUGE_PORT = "COM7"
GAUGE_BAUD = 115200

Z_FEEDRATE = 300  # mm/min
SETTLE_SECONDS = 0.3
HOMING_TIMEOUT_S = 60.0
MOVE_TIMEOUT_S = 60.0


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sensor-port", default=SENSOR_PORT)
    parser.add_argument("--printer-port", default=PRINTER_PORT)
    parser.add_argument("--printer-baud", type=int, default=PRINTER_BAUD)
    parser.add_argument("--gauge-port", default=GAUGE_PORT)
    parser.add_argument("--gauge-baud", type=int, default=GAUGE_BAUD)
    return parser.parse_args()


def prompt_test_parameters():
    output_dir = Path(input("Output directory: ").strip())
    output_dir.mkdir(parents=True, exist_ok=True)
    start = float(input(f"Start position (mm, {ABS_Z_MIN}-{ABS_Z_MAX}): ").strip())
    end = float(input(f"End position (mm, {ABS_Z_MIN}-{ABS_Z_MAX}): ").strip())
    default_step = "0.01" if end >= start else "-0.01"
    stepsize = float(input(f"Step size (mm, signed) [{default_step}]: ").strip() or default_step)
    rehome = input("Rehome? (y/n): ").strip()

    if not (ABS_Z_MIN <= start <= ABS_Z_MAX):
        raise ValueError(f"start {start} outside allowed range [{ABS_Z_MIN}, {ABS_Z_MAX}]")
    if not (ABS_Z_MIN <= end <= ABS_Z_MAX):
        raise ValueError(f"end {end} outside allowed range [{ABS_Z_MIN}, {ABS_Z_MAX}]")
    if start == end:
        raise ValueError(f"start {start} must differ from end {end}")
    if stepsize == 0 or (stepsize > 0) != (end > start):
        raise ValueError(f"stepsize {stepsize} must be nonzero and point from start {start} "
                         f"toward end {end}")

    return output_dir, start, end, stepsize, rehome.lower() == 'y'


def generate_positions(start, end, stepsize):
    # stepsize carries the direction of travel, so (end - start) / stepsize is
    # always positive whether the sweep runs up or down the axis.
    steps = round((end - start) / stepsize)
    positions = [start + i * stepsize for i in range(steps)]
    positions.append(end)
    return [round(position, 6) for position in positions]


def connect_printer(port, baud):
    ser = serial.Serial(port, baud, timeout=MOVE_TIMEOUT_S)
    time.sleep(2.0)
    ser.reset_input_buffer()
    return ser


def send_gcode(ser, line):
    ser.write((line + "\n").encode("ascii"))


def wait_for_ok(ser, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        raw = ser.readline()
        if not raw:
            continue
        line = raw.decode("ascii", errors="replace").strip()
        if not line:
            continue
        if line.lower().startswith("ok"):
            return
        print(f"printer: {line}")
    raise TimeoutError(f"no ok response within {timeout}s")


def gcode_command(ser, line, timeout=MOVE_TIMEOUT_S):
    send_gcode(ser, line)
    wait_for_ok(ser, timeout)


def home_printer(ser):
    print("Homing printer...")
    gcode_command(ser, "G28", timeout=HOMING_TIMEOUT_S)
    gcode_command(ser, "G90")
    gcode_command(ser, "G1 X0 Y0 F3000")
    gcode_command(ser, "M400", timeout=HOMING_TIMEOUT_S)


def move_z(ser, z):
    gcode_command(ser, f"G1 Z{z:.4f} F{Z_FEEDRATE}")
    gcode_command(ser, "M400")
    time.sleep(SETTLE_SECONDS)


class GaugeReader:
    '''Continuously reads the Mitutoyo SPC bridge (spc-firmware) in a background
    thread, keeping timestamped readings so a time window can be pulled out later.'''

    def __init__(self, port, baud):
        self.ser = serial.Serial(port, baud, timeout=0.5)
        self.readings = []  # (monotonic time, value in mm)
        self.faults = []  # (monotonic time, message)
        self.lock = threading.Lock()
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        while self.running:
            try:
                raw = self.ser.readline()
            except serial.SerialException as error:
                with self.lock:
                    self.faults.append((time.monotonic(), f"serial error: {error}"))
                return
            if not raw:
                continue
            now = time.monotonic()
            line = raw.decode("ascii", errors="replace").strip()
            if not line:
                continue
            with self.lock:
                try:
                    self.readings.append((now, float(line)))
                except ValueError:
                    self.faults.append((now, line))

    def window(self, start, end):
        '''Returns the readings and faults received between start and end, and
        drops everything older than end since it will never be needed again.'''
        with self.lock:
            readings = [value for t, value in self.readings if start <= t <= end]
            faults = [message for t, message in self.faults if start <= t <= end]
            self.readings = [r for r in self.readings if r[0] > end]
            self.faults = [f for f in self.faults if f[0] > end]
        return readings, faults

    def close(self):
        self.running = False
        self.thread.join()
        self.ser.close()


def run_reader(sensor_port, output_file, position):
    '''Runs the sensor-under-test reader and returns the monotonic time window
    during which it was streaming samples.'''
    process = subprocess.Popen(
        [sys.executable, "-u", str(READER_SCRIPT), sensor_port, str(output_file)],
        stdout=subprocess.PIPE, text=True)
    assert process.stdout is not None
    sampling_start = None
    for line in process.stdout:
        print(line, end="")
        if sampling_start is None and line.strip() == READER_SAMPLING_MARKER:
            sampling_start = time.monotonic()
    returncode = process.wait()
    sampling_end = time.monotonic()
    if returncode != 0:
        raise RuntimeError(
            f"sensor capture failed at position {position:.4f} (exit code {returncode})")
    if sampling_start is None:
        raise RuntimeError(f"sensor reader at position {position:.4f} never reported "
                           f"{READER_SAMPLING_MARKER!r}")
    return sampling_start, sampling_end


def capture(sensor_port, gauge, output_dir, gauge_dir, sample_index, position):
    filename = f"{sample_index:05d}_{position:.4f}.json"
    output_file = output_dir / filename
    # The first capture after a move often still catches the tail end of the
    # motion due to sample/output delay, so take it twice and let the second
    # capture overwrite the first before keeping the result.
    run_reader(sensor_port, output_file, position)
    sampling_start, sampling_end = run_reader(sensor_port, output_file, position)

    # Gauge readings taken while the kept sensor capture was streaming
    readings, faults = gauge.window(sampling_start, sampling_end)
    if not readings:
        raise RuntimeError(f"no gauge readings during capture at position {position:.4f} "
                           f"({len(faults)} faults: {faults[:3]})")
    mean = statistics.fmean(readings)
    std = statistics.stdev(readings) if len(readings) > 1 else 0.0
    data = {
        "commanded_position": position,
        "measured_position": mean,
        "measured_std": std,
        "count": len(readings),
        "duration": sampling_end - sampling_start,
        "readings": readings,
        "faults": faults,
    }
    with open(gauge_dir / filename, "w") as f:
        json.dump(data, f)
    return mean, std


def main():
    args = parse_args()
    output_dir, start, end, stepsize, rehome = prompt_test_parameters()
    # Kept beside output_dir rather than inside it, since AccuracyAnalysis
    # expects every entry in output_dir to be a sensor capture.
    gauge_dir = output_dir.parent / f"{output_dir.name}_mitutoyo"
    gauge_dir.mkdir(parents=True, exist_ok=True)

    positions = generate_positions(start, end, stepsize)
    total_samples = len(positions)
    print(f"Start={start} End={end} Step={stepsize}")
    print(f"{total_samples} samples total "
          f"(at least ~{total_samples * 2:.0f}s / {total_samples * 2 / 60:.1f}min)")

    input("This will home the printer and move its axes. Make sure the sensor "
          "cannot be bumped. Press Enter to continue...")

    gauge = GaugeReader(args.gauge_port, args.gauge_baud)
    ser = connect_printer(args.printer_port, args.printer_baud)
    last_position = None
    try:
        if rehome:
            home_printer(ser)
        input("Printer ready to move. Ensure nothing is interfering with motion.")
        move_z(ser, start)
        last_position = start

        input(f"Printer homed and positioned at the start (Z={start}). Verify "
              "alignment, then press Enter to begin sampling...")

        for sample_index, position in enumerate(positions):
            move_z(ser, position)
            last_position = position
            mean, std = capture(args.sensor_port, gauge, output_dir, gauge_dir,
                                sample_index, position)
            print(f"sample {sample_index + 1}/{total_samples} "
                  f"z={position:.4f} gauge={mean:.4f} std={std:.4f}")
    finally:
        ser.close()
        gauge.close()
        if last_position is not None:
            print(f"Printer left at Z={last_position:.4f}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)
