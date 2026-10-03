import argparse
import datetime
import json
import re
import sys
import time

import serial

SAMPLES_PER_LINE = 8
FIELDS_PER_LINE = SAMPLES_PER_LINE + 2
HEADER_GIVEUP_SECONDS = 10.0


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("port",  nargs="?", default='COM4')
    parser.add_argument("output", nargs="?", default=None)
    parser.add_argument("--baudrate", type=int, default=460800)
    parser.add_argument("--timeout", type=float, default=2.0)
    return parser.parse_args()


HEADER_LINE_RE = re.compile(r"^Sequence Rate: (\d+) ticks at (\d+) Hz$")


def parse_header_line(line):
    match = HEADER_LINE_RE.match(line.strip())
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def read_header(ser):
    last_data_time = time.monotonic()
    while True:
        raw = ser.readline()
        if raw:
            last_data_time = time.monotonic()
            line = raw.decode("ascii", errors="replace").strip()
            header = parse_header_line(line)
            if header is not None:
                return header
        elif time.monotonic() - last_data_time > HEADER_GIVEUP_SECONDS:
            raise ValueError(f"no data received within {HEADER_GIVEUP_SECONDS}s while waiting for header")


def parse_data_line(line, line_number):
    fields = line.split(",")
    if len(fields) != FIELDS_PER_LINE:
        raise ValueError(f"line {line_number}: expected {FIELDS_PER_LINE} fields, got {len(fields)}: {line!r}")
    try:
        values = [int(field) for field in fields]
    except ValueError:
        raise ValueError(f"line {line_number}: non-integer field in {line!r}")
    index = values[0]
    samples = values[1:-1]
    checksum = values[-1]
    if checksum != sum(samples):
        raise ValueError(f"line {line_number}: checksum mismatch, expected {sum(samples)} but got {checksum}")
    return index, samples


def read_samples(ser):
    records = []
    expected_index = None
    line_number = 1
    while True:
        raw = ser.readline()
        if not raw:
            break
        line_number += 1
        line = raw.decode("ascii", errors="replace").strip()
        if not line:
            continue
        if parse_header_line(line) is not None:
            print(f"line {line_number}: next header encountered, stopping capture")
            break
        if line == "end":
            break
        index, samples = parse_data_line(line, line_number)
        if expected_index is None:
            expected_index = index
        elif index != expected_index:
            raise ValueError(f"line {line_number}: expected index {expected_index}, got {index}")
        records.append(samples)
        expected_index += 1
    return records


def main():
    args = parse_args()
    output = args.output or datetime.datetime.now().strftime("impulse_data/%Y-%m-%d_%H-%M-%S.json")

    print(f'Reading from {args.port} to file {output}')

    try:
        with serial.Serial(args.port, args.baudrate, timeout=args.timeout) as ser:
            print("Waiting for header...")
            ticks, frequency_hz = read_header(ser)
            print(f"Header found: {ticks} ticks at {frequency_hz} Hz")
            print("Reading samples...")
            samples = read_samples(ser)
            print(f"Read {len(samples)} samples")
            if not samples:
                raise ValueError("no samples received")

        data = {
            "sample_period": ticks / frequency_hz / len(samples),
            "samples": samples,
        }
        with open(output, "w") as f:
            json.dump(data, f)
        print(f"Saved to {output}")
    except (ValueError, serial.SerialException) as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
