import argparse
import re
import sys
import time

import serial

from matplotlib import pyplot as plt

import numpy as np

from scipy import signal as sig

SAMPLES_PER_LINE = 8
FIELDS_PER_LINE = SAMPLES_PER_LINE + 2
HEADER_GIVEUP_SECONDS = 10.0


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("port",  nargs="?", default='COM4')
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


def focusSamples(time_ms, samples0, samples1):
    sample_period = (time_ms[1] - time_ms[0]) * 1e-3
    diff = samples1 - samples0
    plt.figure()
    plt.plot(time_ms, samples0 - np.mean(samples0), alpha=0.5)
    plt.plot(time_ms, samples1 - np.mean(samples1), alpha=0.5)
    plt.plot(time_ms, diff - np.mean(diff), 'k', alpha=0.8)
    plt.suptitle('Focus Time Domain')

    freqs = np.fft.rfftfreq(len(samples0), sample_period)
    fft0 = np.fft.rfft(samples0)
    fft1 = np.fft.rfft(samples1)
    fftdiff = np.fft.rfft(diff)

    plt.figure()
    plt.plot(freqs[1:], 10*np.log10(np.abs(fft0[1:])), alpha=0.5, label='0')
    plt.plot(freqs[1:], 10*np.log10(np.abs(fft1[1:])), alpha=0.5, label='1')
    plt.plot(freqs[1:], 10*np.log10(np.abs(fftdiff[1:])), 'k', alpha=0.8, label='D')
    plt.ylabel('Magnitude (dB)')
    plt.xlabel('Frequency (Hz)')
    plt.legend()
    plt.suptitle('Focus FFT')


def main():
    args = parse_args()

    print(f'Reading from {args.port}')

    with serial.Serial(args.port, args.baudrate, timeout=args.timeout) as ser:
        print("Waiting for header...")
        ticks = 0
        stm32_timer_frequency = np.nan
        while ticks == 0:
            ticks, stm32_timer_frequency = read_header(ser)
        print(f"Header found: {ticks} ticks at {stm32_timer_frequency} Hz")
        sample_period = ticks / stm32_timer_frequency
        sample_rate = 1/sample_period
        print(f'Sample frequency: {sample_rate:0.0f} Hz')

        print("Reading samples...")
        samples = read_samples(ser)
        print(f"Read {len(samples)} samples")
        if not samples:
            raise ValueError("no samples received")

    samples = np.array(samples)

    time_ms = np.linspace(0, len(samples) / sample_rate, len(samples)) * 1e3

    raw_range = np.max(np.mean(samples, axis=0)) - np.min(np.mean(samples, axis=0))
    raw_std = np.mean(np.std(samples, axis=0))

    print(f'Signal Range:     {raw_range:0.0f} counts')
    print(f'Overall std:      {raw_std:0.2f} counts')
    print(f'Range/STD:        {10*np.log10(raw_range / raw_std):0.2f} dB')

    # focusSamples(time_ms, samples[:, 0], samples[:, 1])

    # plt.show()
    # exit()

    plt.figure()
    for tr in range(8):
        plt.plot(time_ms, samples[:, tr], alpha=0.5, label='zero', color=f'C{tr}')
        # plt.plot(meas[:, tr], alpha=0.5, label='meas', color=f'C{tr}')
    plt.title('Raw Readings')
    plt.xlabel('Time (ms)')
    plt.ylabel('Magnitude')
    # ax[1].plot(diff, alpha=1)
    # ax[1].title.set_text('Differences')

    # leave room on the right for the text labels, which start at the
    # last data point and grow rightward (sharex=True applies this to both)
    plt.xlim(right=len(samples) * 1.3)

    for tr in range(8):
        plt.text(
            time_ms[-1],
            samples[-1, tr],
            f" {np.mean(samples[:, tr]):0.0f} ±{np.std(samples[:, tr]):0.1f}",
            horizontalalignment="left",
            verticalalignment="center",
        )

    plt.tight_layout()

    # plt.figure()
    # plt.hist(samples - np.mean(samples, axis=0), alpha=0.3)

    # plt.figure()
    # tr = 1
    # plt.plot(time_ms, samples[:, tr] - np.mean(samples[:, tr]), alpha=0.5, label=f'samples - {np.mean(samples[:, tr]):0.0f}')
    # plt.legend()
    # plt.title('Mean-subtracted transient values')
    # plt.xlabel('Time (ms)')
    # plt.ylabel('Magnitude Minus Mean')
    # plt.tight_layout()

    # _, ax = plt.subplots(8)
    # for tr in range(8):
    #     freqs_z, welch_z = sig.welch(samples[:, tr], 1/sample_period)
    #     ax[tr].plot(freqs_z, 10*np.log10(welch_z), alpha=0.5, label='PSD')
    #     ax[tr].set_ylabel('Magnitude (dB)')

    # ax[0].set_xlabel('Frequency (Hz)')
    # # ax[0].legend()
    # plt.suptitle('PSD')

    # _, ax = plt.subplots(8)
    # for tr in range(8):
    #     freqs = np.fft.rfftfreq(len(samples[:, tr]), sample_period)
    #     fft = np.fft.rfft(samples[:, tr])
    #     ax[tr].plot(freqs[1:], 10*np.log10(np.abs(fft[1:])), alpha=0.5, label='FFT')
    #     ax[tr].set_ylabel('Magnitude (dB)')

    # ax[0].set_xlabel('Frequency (Hz)')
    # plt.suptitle('FFT')


if __name__ == "__main__":
    main()

    plt.show()
