import argparse
import subprocess
import sys
import time
from pathlib import Path

import serial

READER_SCRIPT = Path(__file__).parent / "BurstReader.py"

ABS_Z_MIN = 145
ABS_Z_MAX = 160

SENSOR_PORT = "COM4"
PRINTER_PORT = "COM6"
PRINTER_BAUD = 115200

Z_FEEDRATE = 300  # mm/min
SETTLE_SECONDS = 0.3
HOMING_TIMEOUT_S = 60.0
MOVE_TIMEOUT_S = 60.0


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sensor-port", default=SENSOR_PORT)
    parser.add_argument("--printer-port", default=PRINTER_PORT)
    parser.add_argument("--printer-baud", type=int, default=PRINTER_BAUD)
    return parser.parse_args()


def prompt_test_parameters():
    output_dir = Path(input("Output directory: ").strip())
    output_dir.mkdir(parents=True, exist_ok=True)
    start = float(input(f"Start position (mm, {ABS_Z_MIN}-{ABS_Z_MAX}): ").strip())
    end = float(input(f"End position (mm, {ABS_Z_MIN}-{ABS_Z_MAX}): ").strip())
    default_step = "0.01" if end >= start else "-0.01"
    stepsize = float(input(f"Step size (mm, signed) [{default_step}]: ").strip() or default_step)
    cycles = int(input("Number of cycles: ").strip())
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
    if cycles < 1:
        raise ValueError(f"cycles {cycles} must be at least 1")

    return output_dir, start, end, stepsize, cycles, rehome.lower() == 'y'


def generate_cycle_positions(start, end, stepsize):
    # stepsize carries the direction of travel, so (end - start) / stepsize is
    # always positive whether the sweep runs up or down the axis.
    steps = round((end - start) / stepsize)
    forward = [start + i * stepsize for i in range(steps)]
    forward.append(end)
    forward = [round(position, 6) for position in forward]
    back = list(reversed(forward[:-1]))
    return forward + back


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


def capture(sensor_port, output_dir, sample_index, position):
    output_file = output_dir / f"{sample_index:05d}_{position:.4f}.json"
    # The first capture after a move often still catches the tail end of the
    # motion due to sample/output delay, so take it twice and let the second
    # capture overwrite the first before keeping the result.
    for _ in range(2):
        result = subprocess.run([sys.executable, str(READER_SCRIPT), sensor_port, str(output_file)])
        if result.returncode != 0:
            raise RuntimeError(
                f"sensor capture failed at position {position:.4f} (exit code {result.returncode})")


def main():
    print("WARNING: This script will not set the device into burst mode, if a UART timeout happens change the mode manually.")
    args = parse_args()
    output_dir, start, end, stepsize, cycles, rehome = prompt_test_parameters()

    positions = generate_cycle_positions(start, end, stepsize)
    total_samples = len(positions) * cycles
    print(f"Start={start} End={end} Step={stepsize} Cycles={cycles}")
    print(f"{len(positions)} samples per cycle, {total_samples} samples total "
          f"(at least ~{total_samples * 2:.0f}s / {total_samples * 2 / 60:.1f}min)")

    input("This will home the printer and move its axes. Make sure the sensor "
          "cannot be bumped. Press Enter to continue...")

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

        sample_index = 0
        for cycle in range(1, cycles + 1):
            for position in positions:
                move_z(ser, position)
                last_position = position
                capture(args.sensor_port, output_dir, sample_index, position)
                sample_index += 1
                print(f"cycle {cycle}/{cycles} sample {sample_index}/{total_samples} "
                      f"z={position:.4f}")
    finally:
        ser.close()
        if last_position is not None:
            print(f"Printer left at Z={last_position:.4f}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)
