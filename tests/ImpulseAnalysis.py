import json

import numpy as np
from matplotlib import pyplot as plt

from scipy.stats import norm

from scipy import signal as sig


NUM_EMITTERS = 4

PERIOD_SIZE_MM = 12
ESTIMATES_TO_MM = PERIOD_SIZE_MM / (NUM_EMITTERS*2)


def estimatePosition(measurments):
    '''
    Input: array:
    [transient type index, actual reflector position index] == sum of that transient at that position
    '''

    measurments = measurments.T

    mapped = np.zeros((NUM_EMITTERS, 2, len(measurments[0])))
    mapped[0][1] = measurments[0]
    mapped[1][1] = measurments[2]
    mapped[2][1] = measurments[4]
    mapped[3][1] = measurments[6]

    mapped[0][0] = measurments[1]
    mapped[1][0] = measurments[3]
    mapped[2][0] = measurments[5]
    mapped[3][0] = measurments[7]

    def runEstimate(readings):
        zeros = np.zeros(2)

        for lane in [0, 1]:
            first_sign = readings[0][lane] >= 0
            transition_idx = NUM_EMITTERS

            # Look for the first zero crossing and interpolate
            for test_idx in range(NUM_EMITTERS):
                if ((readings[test_idx][lane] >= 0) != first_sign):
                    transition_idx = test_idx
                    break

            # Handle edge-cases that do not explicitly cross  within the first four
            if transition_idx == NUM_EMITTERS:
                # Handle waveforms that do not explicitly cross 0
                x1 = readings[NUM_EMITTERS - 1][lane]
                x2 = -readings[0][lane]
            else:
                x1 = readings[transition_idx - 1][lane]
                x2 = readings[transition_idx][lane]

            interp = -x1 / (x2 - x1)
            zeros[lane] = interp + transition_idx

            # Handle the lane offset
            if lane:
                zeros[lane] -= 0.5

            # Handle overflows above four
            if zeros[lane] >= 4:
                zeros[lane] -= 4

        dist = zeros[0] - zeros[1]

        if abs(dist) > 3.75:
            # One lane has overflowed but the other hasn't.
            # Averaging would choose a midpoint (ie. we'd get '2' when we're actually at 4 (=0)).
            # We'll just pick one and run with it.
            return zeros[0]

        return (zeros[0] + zeros[1]) / 2

    position_estimates = np.array([runEstimate(mapped[:, :, pos]) for pos in range(len(mapped[0][0]))])

    return position_estimates


def positions(raw_samples, positions, sample_time_period):
    noise = positions - np.mean(positions)

    plt.figure()
    plt.plot(positions)
    plt.title('Position (mm)')
    plt.figure()
    plt.plot(freq_bounds[1:], np.abs(positions_fft))
    plt.title('Noise FFT')
    plt.figure()
    plt.plot(freq_bounds[1:], np.cumsum(np.abs(positions_fft[::-1]))[::-1])
    plt.title('Noise Frequency CDF')
    plt.figure()
    plt.hist(noise)
    plt.title('Histogram of Noise')

    confidence_level = 0.95
    z = norm.ppf((1 + confidence_level) / 2)
    quantile = z * noise.std()


def rawNoiseAnalysis(raw_samples, sample_time_period, name=None):
    noise = raw_samples - np.mean(raw_samples, axis=0)

    print(f'Sample rate: {1e-3/sample_time_period:0.2f} kHz')

    ffts = np.fft.rfft(raw_samples, axis=0)
    freq_bounds = np.fft.rfftfreq(raw_samples.shape[0], sample_time_period)
    _, ax = plt.subplots(3)
    for smp in range(noise.shape[1]):
        ax[0].plot(raw_samples[:, smp], alpha=0.5)
    ax[0].set_xlabel('Sample Index')
    ax[0].set_ylabel('Magnitude (counts)')
    ax[0].title.set_text('Time Domain')

    for tr in range(8):
        ax[1].plot(freq_bounds, 10*np.log10(np.abs(ffts[:, tr])))
    ax[1].set_xlabel('Frequency (Hz)')
    ax[1].set_ylabel('Magnitude (dB)')
    ax[1].set_title('FFT')

    for tr in range(8):
        welch_freqs, welch = sig.welch(raw_samples[:, tr], 1/sample_time_period)
        ax[2].plot(welch_freqs, 10*np.log10(welch))
    ax[2].set_xlabel('Frequency (Hz)')
    ax[2].set_ylabel('Magnitude (dB)')
    ax[2].set_title('PSD')

    if name is not None:
        plt.suptitle(name)

    print(f'{name}:')
    raw_range = np.max(np.mean(raw_samples, axis=0)) - np.min(np.mean(raw_samples, axis=0))
    print(f'\tSignal Magnitude Range: {raw_range:0.0f} counts')
    raw_std = np.mean(np.std(raw_samples, axis=0))
    print(f'\tSignal STD: {raw_std:0.1f} counts')
    print(f'\tSignal SNR: {10*np.log10(raw_range/raw_std):0.2f} dB')

    plt.tight_layout()


def plotFiltering(positions_1, samples_mm, raw_samples_1, data):
    kernel = np.ones(5)
    positions_2 = np.convolve(positions_1, kernel, 'same') / np.sum(kernel)

    for tr in range(8):
        std = np.std(samples_mm[:, tr])
        pkpk = np.max(samples_mm[:, tr]) - np.min(samples_mm[:, tr])
        print(f'tr{tr}: std = {1e3 * std:0.1f} µm, pk-pk =  {1e3 * pkpk:0.1f} µm')

    print(f'Averaged std: {1e3 * np.mean(np.std(samples_mm, axis=0)):0.1f} µm')

    raw_samples_1 = np.astype(raw_samples_1, np.float64)
    raw_samples_filtered = np.apply_along_axis(lambda time_data: np.convolve(time_data, kernel, 'same'), axis=0, arr=raw_samples_1)
    print('raw_samples_filtered:', raw_samples_filtered.shape)
    positions_3 = estimatePosition(raw_samples_filtered)

    positions_1 = positions_1[5:-5]
    positions_2 = positions_2[5:-5]
    positions_3 = positions_3[5:-5]

    print(
        f'Plain Position Estimate std:                     {np.std(positions_1) * ESTIMATES_TO_MM * 1e3:0.1f} µm, pk-pk: {(np.max(positions_1) - np.min(positions_1)) * ESTIMATES_TO_MM * 1e3:0.1f} µm')
    print(
        f'5-sample moving average on positions:            {np.std(positions_2) * ESTIMATES_TO_MM * 1e3:0.1f} µm, pk-pk: {(np.max(positions_2) - np.min(positions_2)) * ESTIMATES_TO_MM * 1e3:0.1f} µm')
    print(
        f'5-sample moving average then estimate positions: {np.std(positions_3) * ESTIMATES_TO_MM * 1e3:0.1f} µm, pk-pk: {(np.max(positions_3) - np.min(positions_3)) * ESTIMATES_TO_MM * 1e3:0.1f} µm')

    plt.figure()
    plt.plot(positions_1, alpha=0.5)
    plt.plot(positions_2, alpha=0.5)
    plt.plot(positions_3, alpha=0.5)
    rawNoiseAnalysis(raw_samples_1[:], data['sample_period'], 'raw_samples_1[:]')
    rawNoiseAnalysis(raw_samples_filtered[:], data['sample_period'], 'raw_samples_filtered[:]')


def main():
    INPUT_FILE = 'impulse_data/2026-09-15_21-28-48.json'
    with open(INPUT_FILE, "r") as f:
        data = json.load(f)

    raw_samples_1 = np.array(data['samples'])
    print('raw_samples:', raw_samples_1.shape)

    with open('accuracy/00000_154.0000.json', "r") as f:
        data = json.load(f)
    raw_samples_2 = np.array(data['samples'])

    # with open('impulse_data/2026-09-07_20-55-24.json', "r") as f:
    #     data = json.load(f)
    # raw_samples_3 = np.array(data['samples'])

    positions_1 = estimatePosition(raw_samples_1)
    # The sum of the absolute values of transients 0 and 2 from each lane (columns 0, 2, 4, 6) is the norm magnitude of the measurements
    magnitudes = np.sum(np.abs(raw_samples_1[:, [0, 2, 4, 6]]), axis=-1)
    # The transients span +/- magnitudes for every PERIOD_SIZE_MM millimeters of motion.
    tranient_magnitude_to_mm = PERIOD_SIZE_MM / magnitudes

    samples_mm = raw_samples_1 * tranient_magnitude_to_mm[:, np.newaxis]

    rawNoiseAnalysis(raw_samples_1, data['sample_period'], 'raw_samples_1')
    rawNoiseAnalysis(raw_samples_2, data['sample_period'], 'raw_samples_2')
    # rawNoiseAnalysis(raw_samples_3, data['sample_period'], 'raw_samples_3')

    plt.show()


if __name__ == '__main__':
    main()
