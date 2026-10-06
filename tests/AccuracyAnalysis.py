import json
import pickle as pkl

import numpy as np
from matplotlib import pyplot as plt

from tqdm import tqdm

from scipy.stats import norm

from scipy import signal as sig

import os

ALLOW_PKL = False

DIRECTORY = './data/accuracy2'
MITUTOYO_DIRECTORY = './data/accuracy2_mitutoyo'

# DIRECTORY = './data/accuracy'
# MITUTOYO_DIRECTORY = './data/accuracy_mitutoyo'

NUM_EMITTERS = 4

PERIOD_SIZE_MM = 5.08

# This is the size of the electrical clearance between emitters/reflectors
# divided by their overall period. For 5 mil clearance on a 25 mil period
# this equals 0.2.
EMITTER_CLEARANCE_FRACTION = 0.2
EMITTER_CORRECTION_MAGNITUDE = 0.04  # Not ideal. Presumably this is a function of plate seperation?

EMITTERS_TO_MM = PERIOD_SIZE_MM / (NUM_EMITTERS*2)


def estimatePosition(measurments):
    '''
    Input: array:
    [transient type index, actual reflector position index] == sum of that transient at that position
    '''

    measurments = measurments.T

    mapped = np.zeros((NUM_EMITTERS, 2, len(measurments[0])))
    mapped[0][0] = measurments[0]
    mapped[1][0] = measurments[1]
    mapped[2][0] = measurments[2]
    mapped[3][0] = measurments[3]

    mapped[0][1] = measurments[4]
    mapped[1][1] = measurments[5]
    mapped[2][1] = measurments[6]
    mapped[3][1] = measurments[7]

    def runEstimate(readings):
        zeros = np.zeros(2)

        for phase in [0, 1]:
            first_sign = readings[0][phase] >= 0
            transition_idx = NUM_EMITTERS

            # Look for the first zero crossing and interpolate
            for test_idx in range(NUM_EMITTERS):
                if ((readings[test_idx][phase] >= 0) != first_sign):
                    transition_idx = test_idx
                    break

            # Handle edge-cases that do not explicitly cross within the first four
            if transition_idx == NUM_EMITTERS:
                # Handle waveforms that do not explicitly cross 0
                x1 = readings[NUM_EMITTERS - 1][phase]
                x2 = -readings[0][phase]
            else:
                x1 = readings[transition_idx - 1][phase]
                x2 = readings[transition_idx][phase]

            interp = -x1 / (x2 - x1)
            zeros[phase] = interp + transition_idx

            # Handle the phase shift
            if phase:
                zeros[phase] -= 0.5

            # Handle overflows above/below four
            zeros[phase] %= 4

        dist = zeros[0] - zeros[1]

        if abs(dist) > 3.75:
            # One phase has overflowed but the other hasn't.
            # Averaging would choose a midpoint (ie. we'd get '2' when we're actually at 4 (=0)).
            # We'll just pick one and run with it.
            return zeros[0]

        return (zeros[0] + zeros[1]) / 2

    # plt.figure()
    # averaged = np.mean(mapped[:, 0], axis=-1)
    # plt.scatter([0, 1, 2, 3], averaged)
    # averaged = np.mean(mapped[:, 1], axis=-1)
    # plt.scatter([-0.5, 0.5, 1.5, 2.5], averaged)

    position_estimates = np.array([runEstimate(mapped[:, :, pos]) for pos in range(len(mapped[0][0]))])

    return position_estimates


def applyClearanceCorrection_Linear(position_estimates: np.ndarray):
    shifted_estimates = position_estimates + EMITTER_CLEARANCE_FRACTION
    estimate_within_emitter_period = np.mod(shifted_estimates, 1)

    correction_offset = np.zeros_like(position_estimates)
    ewep = estimate_within_emitter_period
    ECF = EMITTER_CLEARANCE_FRACTION
    ECM = EMITTER_CORRECTION_MAGNITUDE
    correction_offset[ewep < 2*ECF] = ((ECM / ECF) * ewep[ewep < 2*ECF]) - ECM
    ewep_2 = np.mod(shifted_estimates - 2*ECF, 1)
    correction_offset[ewep >= 2*ECF] = ECM - ((2*ECM/(1-2*ECF)) * ewep_2[ewep >= 2*ECF])

    return position_estimates + correction_offset - EMITTER_CLEARANCE_FRACTION, correction_offset


def applyClearanceCorrection_Sinusoid(position_estimates: np.ndarray):
    ECF = EMITTER_CLEARANCE_FRACTION
    ECM = EMITTER_CORRECTION_MAGNITUDE
    correction_offset = ECM * np.cos(2 * np.pi * (position_estimates - ECF))

    return position_estimates + correction_offset, correction_offset


def plotWrappedEstimates(estimate_positions, commanded_positions):
    estimate_positions -= np.mean(estimate_positions[0])
    estimate_positions %= 4

    # estimate_positions *= PERIOD_SIZE_MM / (NUM_EMITTERS*2)

    commanded_positions %= 4

    _, ax = plt.subplots(2, sharex=True)
    ax[0] = ax[0].twiny()
    for pos in range(len(commanded_positions)):
        ax[0].scatter(np.repeat(commanded_positions[pos], estimate_positions.shape[1]), estimate_positions[pos, :], c=f'C0', alpha=0.01)
    ax[0].plot([np.min(commanded_positions), np.max(commanded_positions)], [np.min(commanded_positions), np.max(commanded_positions)], 'k--')
    ax[0].title.set_text('position estimate')
    for pos in range(len(commanded_positions)):
        ax[1].scatter(np.repeat(pos, estimate_positions.shape[1]), estimate_positions[pos, :], c='C0', alpha=0.01)
    ax[1].plot(commanded_positions, 'k--')
    ax[1].title.set_text('position estimate')


def plotWrappedEstimatesNoScatter(estimate_positions, commanded_positions):
    estimate_positions -= np.mean(estimate_positions[0])
    estimate_positions %= 4
    commanded_positions %= 4

    _, ax = plt.subplots(2, sharex=True)
    ax[0] = ax[0].twiny()
    ax[0].plot(commanded_positions, np.mean(estimate_positions, axis=-1), c=f'C0', alpha=0.01)
    ax[0].plot([np.min(commanded_positions), np.max(commanded_positions)], [np.min(commanded_positions), np.max(commanded_positions)], 'k--')
    ax[0].title.set_text('position estimate')
    ax[1].plot(np.mean(estimate_positions, axis=-1), c=f'C0', alpha=0.01)
    ax[1].plot(commanded_positions, 'k--')
    ax[1].title.set_text('position estimate')


def focusPlotSingleEstimate(estimate_positions, raw_samples, focal_index):
    _, ax = plt.subplots(3, sharex=True)
    for tr in range(4):
        ax[0].plot(raw_samples[focal_index, :, tr], marker='o')
    ax[0].title.set_text('phase 0')
    for tr in range(4):
        ax[1].plot(raw_samples[focal_index, :, tr + 4], marker='o')
    ax[1].title.set_text('phase 1')
    ax[2].plot(estimate_positions[focal_index, :], marker='o')
    ax[2].title.set_text('Position Estimate')
    [a.grid(True) for a in ax]

    # _, ax = plt.subplots(2, sharex=True)
    # ax[0].plot(np.arange(4), raw_samples[focal_index, time_step, :4], marker='o')
    # ax[0].plot([4], -raw_samples[focal_index, time_step, 0], marker='o')
    # ax[0].title.set_text('phase 0')
    # ax[1].plot(np.arange(4), raw_samples[focal_index, time_step, 4:], marker='o')
    # ax[1].plot([4], -raw_samples[focal_index, time_step, 4], marker='o')
    # ax[1].title.set_text('phase 1')
    # [a.grid(True) for a in ax]

    # N = len(estimate_positions[focal_index, :])

    # sos = sig.bessel(6, 0.1, output='sos')
    # w_plot, h_plot = sig.freqz_sos(sos)
    # wgd_plot, group_delay = sig.group_delay(sig.sos2tf(sos))
    # filtered_estimates = sig.sosfilt(sos, np.repeat(estimate_positions[focal_index, :], 3))
    # filtered_estimates = filtered_estimates[N:2*N]
    # ma_n = N//2
    # moving_avg = np.ones(ma_n) / (ma_n)
    # # filtered_error = filtered_estimates - np.repeat(wrapped_real_positions[:, np.newaxis], filtered_estimates.shape[1], axis=-1)
    # # plottable_filtered_error = (pos_error * EMITTERS_TO_MM)

    # w_magv, h_magv = sig.freqz(moving_avg)
    # w_gd_magv, group_delay_mavg = sig.group_delay((moving_avg, [1]))

    # h_plot[np.abs(h_plot) < 1e-8] = np.nan
    # h_magv[np.abs(h_magv) < 1e-8] = np.nan

    # plt.figure()
    # line1, = plt.plot(w_plot / np.pi, (10 * np.log10(np.abs(h_plot))))
    # line2, = plt.plot(w_magv / np.pi, (10 * np.log10(np.abs(h_magv))))
    # plt.ylabel('Magnitude (dB)')
    # ax = plt.twinx()
    # line3, = ax.plot(wgd_plot / np.pi, group_delay, '--')
    # line4, = ax.plot(w_gd_magv / np.pi, group_delay_mavg, '--')
    # # plt.set_text('Angle (rad)')
    # plt.xlabel('w/nyq')
    # plt.title('Filter')
    # plt.legend([line1, line2, line3, line4], ['Butter Magnitude', 'Moving Average Magnitude', 'Butter Average Group Delay', 'Moving Average Group Delay'])

    # plt.figure()
    # plt.plot(estimate_positions[focal_index, :], marker='o', label='Input')
    # plt.plot(filtered_estimates, marker='o', label='Butter')
    # conv = np.convolve(np.repeat(estimate_positions[focal_index, :], 3), moving_avg)
    # conv = conv[N:2*N]
    # plt.plot(conv, marker='o', label='Moving Average')
    # plt.title('Position Estimate and Filtering')
    # plt.legend()

    fft_freq = np.fft.rfftfreq(len(estimate_positions[focal_index, :]), d=1e-3)
    fft_noise = np.fft.rfft(estimate_positions[focal_index, :])
    _, ax = plt.subplots(1, 2)
    for tr in range(8):
        ax[0].plot(raw_samples[focal_index, :, tr], alpha=0.5)
    ax[0].title.set_text('Time Domain')
    ax[1].plot(fft_freq, 10*np.log10(np.abs(fft_noise)))
    for tr in range(8):
        tr_fft = np.fft.rfft(raw_samples[focal_index, :, tr])
        ax[1].plot(fft_freq, 10*np.log10(np.abs(tr_fft)), alpha=0.5)
    # plt.semilogx()
    ax[1].title.set_text('Noise Frequencies')
    # ax[1].y_label.set_text('Magnitude (dB)')
    # ax[1].x_label.set_text('frequencies')


def plotRawAgainstPos(commanded_positions, estimate_positions, raw_samples):
    _, ax = plt.subplots(2, sharex=True)
    for pos in range(len(commanded_positions)):
        for idx in range(4):
            ax[0].scatter(np.repeat(commanded_positions[pos], raw_samples.shape[1]), raw_samples[pos, :, idx], c=f'C{idx}', alpha=0.1)
    ax[0].title.set_text('phase 0')
    for pos in range(len(commanded_positions)):
        for idx in range(4):
            ax[1].scatter(np.repeat(commanded_positions[pos], raw_samples.shape[1]), raw_samples[pos, :, idx + 4], c=f'C{idx}', alpha=0.1)
    ax[1].title.set_text('phase 1')

    _, ax = plt.subplots(3, sharex=True)
    for tr in range(4):
        ax[0].plot(commanded_positions, np.mean(raw_samples[:, :, tr], axis=-1), c=f'C{tr}', alpha=0.5)
    ax[0].title.set_text('phase 0')
    for tr in range(4):
        ax[1].plot(commanded_positions, np.mean(raw_samples[:, :, tr + 4], axis=-1), c=f'C{tr}', alpha=0.5)
    ax[1].title.set_text('phase 1')
    ax[2].plot(commanded_positions, np.mean(estimate_positions, axis=-1))
    # ax[2].fill_between(commanded_positions, np.min(estimate_positions, axis=-1), np.max(estimate_positions, axis=-1))
    ax[2].plot(commanded_positions, commanded_positions, 'k--', alpha=0.5)
    ax[2].title.set_text('Position Estimate')


def plotRawPlain(commanded_positions, raw_samples):
    _, ax = plt.subplots(3, sharex=True)
    for tr in range(4):
        ax[0].plot(np.mean(raw_samples[:, :, tr], axis=-1), c=f'C{tr}', alpha=0.5)
    ax[0].title.set_text('phase 0')
    for tr in range(4):
        ax[1].plot(np.mean(raw_samples[:, :, tr + 4], axis=-1), c=f'C{tr}', alpha=0.5)
    ax[1].title.set_text('phase 1')
    ax[2].plot(commanded_positions, 'k--', alpha=0.5)
    ax[2].title.set_text('Position')


def wrappedDifference(arr, brr, maxval=4):
    '''
    Compute arr-brr in the wrapped domain of [0, maxval).
    '''
    return ((((arr - brr) + (maxval/2)) % maxval) - (maxval/2))


def plotNoiseLevels(estimate_positions, commanded_positions, raw_samples, sample_period):
    processed_std = np.std(estimate_positions, axis=-1)
    raw_std = np.std(raw_samples, axis=1)

    # Erase errors caused by overflows
    processed_std[processed_std > 1] = np.nan

    # estimate_positions -= np.mean(estimate_positions[0])
    # estimate_positions %= 4
    # commanded_positions %= 4

    wrapped_real_positions = (commanded_positions / EMITTERS_TO_MM) % 4
    estimate_positions -= estimate_positions[0]
    estimate_positions %= 4

    reals = np.array(np.repeat(wrapped_real_positions[:, np.newaxis], estimate_positions.shape[1], axis=-1).flat)
    estimates = np.array(estimate_positions.flat)

    pos_error = wrappedDifference(estimates, reals)
    plottable_error = (pos_error * EMITTERS_TO_MM)

    corner = 100
    wn = corner / (0.5/sample_period)
    print(f'Sample rate is {1e-3 / sample_period:0.2f} kHz')
    print(f'Placing corner at wn={corner} Hz ({wn:0.3f})')
    sos = sig.butter(5, wn, output='sos')
    w_plot, h_plot = sig.freqz_sos(sos)
    unwrapped = np.unwrap(estimates, period=4)
    filtered_estimates = sig.sosfilt(sos, x=unwrapped, axis=-1)
    filtered_error = wrappedDifference(filtered_estimates, reals)
    plottable_filtered_error = (filtered_error * EMITTERS_TO_MM)

    print('pos_error:', pos_error.shape)
    plt.figure()
    line1, = plt.plot(plottable_error, alpha=0.5)
    line3, = plt.plot(plottable_filtered_error, alpha=0.8)
    plt.ylabel('Error, mm')
    plt.xlabel('Raw sample index')
    ax = plt.twinx()
    line2, = ax.plot(reals, 'k--', alpha=0.5)
    plt.title('Position estimate error')
    plt.ylabel('Position, mm')
    plt.legend([line1, line2, line3], ['Measurement Error (Left Axis)', 'Truth (Right Axis)', 'Filtered Error'])

    # Compute the PSD for each test case, since computing it for the
    # combined tests ignores the fact that they are not aligned in time.
    pos_error_split = np.reshape(pos_error, estimate_positions.shape)
    cum_freqs_welch, _welch_errors = sig.welch(pos_error_split[0], 1/sample_period)
    cum_error_welch = np.zeros_like(_welch_errors)
    for test in range(len(pos_error_split)):
        _, welch = sig.welch(pos_error_split[test], 1/sample_period)
        cum_error_welch += welch
    plt.figure()
    plt.plot(cum_freqs_welch, 10*np.log10(np.abs(cum_error_welch)), alpha=0.5)
    plt.xlabel('Frequency (Hz)')
    plt.ylabel('Magnitude (dB)')
    plt.title('PSD')

    error_fft = np.fft.rfft(pos_error)
    freqs = np.fft.rfftfreq(len(pos_error), sample_period)
    plt.figure()
    plt.plot(freqs, 10*np.log10(np.abs(error_fft)), alpha=0.5)
    plt.xlabel('Frequency (Hz)')
    plt.ylabel('Magnitude (dB)')
    plt.title('FFT')


def unwrapEstimates(estimate_positions):
    '''
    This function will unwrap the position estimate.

    It assumes that the first position is exactly zero, 
    then steps along each timestep of each test instance 
    to convert the value from a 4-wrapped value to a 
    realistic distance.

    Example position data, moving in the negative direction:
    [ 
      [ 2.0 2.1 2.1 1.9 ] # Test performed around 2
      [ 1.0 1.1 0.8 0.9 ] # Test around 1
      [ 0.1 3.9 0.1 3.9 ] # Test around 0 (=4)
      [ 3.0 2.9 3.1 3.0 ] # Test around -1 (=3)
    ]

    Result:
    [ 
      [ 0.0  0.1  0.1 -0.1 ] # Starts at zero distance
      [-1.0 -0.9 -1.2 -1.1 ] # Moved -1
      [-1.9 -2.1 -1.9 -2.1 ] # -2
      [-3.0 -3.1 -2.9 -3.0 ] # -3
    ]
    '''
    # Unwrap noise within each test, then unwrap the test means across tests
    unwrapped = np.unwrap(estimate_positions, period=4, axis=1)
    means = np.mean(unwrapped, axis=1)
    unwrapped += (np.unwrap(means, period=4) - means)[:, np.newaxis]
    return unwrapped - unwrapped[0, 0]


def loadMitutoyoData(directory=MITUTOYO_DIRECTORY):
    '''
    Load the Mitutoyo gauge readings captured alongside each sensor sample set.

    Returns arrays (one entry per file, in capture order) of:
    commanded_positions, measured_positions, measured_stds
    '''
    files = [f for f in os.listdir(directory) if f.endswith('.json')]
    files.sort(key=lambda fname: int(fname[:-5].split('_')[0]))

    commanded_positions = []
    measured_positions = []
    measured_stds = []
    for filename in files:
        with open(os.path.join(directory, filename), 'r') as f:
            data = json.load(f)
        commanded_positions.append(data['commanded_position'])
        measured_positions.append(data['measured_position'])
        measured_stds.append(data['measured_std'])

    return np.array(commanded_positions), np.array(measured_positions), np.array(measured_stds)


def main():
    files = os.listdir(DIRECTORY)
    files = list(filter(lambda x: 'Accuracy' not in x, files))
    files.sort(key=lambda fname: float(fname[:-5].split('_')[0]))

    print(f'Loading {len(files)} sample sets')

    commanded_positions = [float(fname[:-5].split('_')[-1]) for fname in files]
    commanded_positions = np.array(commanded_positions)

    commanded_positions -= commanded_positions[0]

    try:
        gauge_commanded, gauge_measured, gauge_std = loadMitutoyoData()
        print(f'Loaded {len(gauge_measured)} Mitutoyo readings')
    except:
        gauge_measured = -commanded_positions

    estimate_positions = []
    raw_samples = []

    sample_period = np.nan

    backup = os.path.join(DIRECTORY, 'AccuracyAnalysis.pkl')
    if os.path.exists(backup) and ALLOW_PKL:
        with open(backup, 'rb') as f:
            raw_samples, estimate_positions, sample_period = pkl.load(f)
    else:

        for filename in tqdm(files):
            with open(os.path.join(DIRECTORY, filename), "r") as f:
                try:
                    data = json.load(f)
                    raw = np.array(data['samples'])
                    pos = estimatePosition(raw)
                    estimate_positions.append(pos)
                    raw_samples.append(raw)
                    sample_period = data['sample_period']
                except:
                    pass
        with open(backup, 'wb') as f:
            pkl.dump((raw_samples, estimate_positions, sample_period), f)

    estimate_positions = np.array(estimate_positions)
    raw_samples = np.array(raw_samples)

    print('estimate_positions:', estimate_positions.shape)
    print('raw_samples:', raw_samples.shape)

    # plotNoiseLevels(estimate_positions.copy(), commanded_positions.copy(), raw_samples.copy(), sample_period)

    # Bring the real positions into units common to the estimates
    # so that they can be wrapped around 4 for easier viewing
    # commanded_positions /= EMITTERS_TO_MM

    # plotWrappedEstimates(4 - estimate_positions.copy(), commanded_positions.copy())
    # plotWrappedEstimatesNoScatter(estimate_positions.copy(), commanded_positions.copy())
    # focusPlotSingleEstimate(estimate_positions.copy(),
    #                         raw_samples.copy(),
    #                         1)
    # focusPlotSingleEstimate(estimate_positions.copy(),
    #                         raw_samples.copy(),
    #                         2)
    # focusPlotSingleEstimate(estimate_positions.copy(),
    #                         raw_samples.copy(),
    #                         3)
    # focusPlotSingleEstimate(estimate_positions.copy(),
    #                         raw_samples.copy(),
    #                         600)
    # focusPlotSingleEstimate(estimate_positions.copy(),
    #                         raw_samples.copy(),
    #                         1000)

    unwrapped = unwrapEstimates(NUM_EMITTERS - estimate_positions)

    unwrapped *= EMITTERS_TO_MM
    commanded_positions = -(commanded_positions-commanded_positions[0])
    gauge_measured -= gauge_measured[0]

    averaged_unwrapped = np.mean(unwrapped, axis=-1)
    averaged_error = (averaged_unwrapped - gauge_measured)

    lin_estimates, l_corr = applyClearanceCorrection_Linear(NUM_EMITTERS - estimate_positions)
    lin_unwrapped = unwrapEstimates(lin_estimates)
    lin_unwrapped *= EMITTERS_TO_MM
    lin_averaged = np.mean(lin_unwrapped, axis=-1)
    lin_averaged_error = lin_averaged - gauge_measured

    plt.figure()
    plt.plot(averaged_unwrapped, label='unwrapped')
    plt.plot(gauge_measured, label='gauge_measured')
    plt.plot(lin_averaged, label='lin_averaged')
    plt.plot(commanded_positions, '--k', label='commanded_positions')
    plt.legend()

    # sin_estimates, s_corr = applyClearanceCorrection_Sinusoid(NUM_EMITTERS - estimate_positions)
    # sin_unwrapped = unwrapEstimates(sin_estimates)
    # sin_averaged_error = np.mean(sin_unwrapped, axis=-1) - gauge_measured

    plt.figure()
    plt.plot(gauge_measured, averaged_error, label='Error')
    # plt.plot(gauge_measured, lin_averaged_error, label='Linear Correction')
    # plt.plot(gauge_measured, np.mean(l_corr, axis=-1), '--', color='C1', label='Linear Factor')
    extended_real_positions = np.repeat(gauge_measured[:, np.newaxis], unwrapped.shape[-1], axis=-1)
    flattened_error = np.array((unwrapped - extended_real_positions).flat)
    plt.scatter(extended_real_positions-extended_real_positions[0], flattened_error, label='Flat error')
    plt.title('Error to Measured')
    plt.ylabel('Error (mm)')
    plt.xlabel('Offset (mm)')
    plt.twinx()
    # plt.plot(gauge_measured, np.mean(estimate_positions, axis=-1), label='Emitter Position')
    for tr in range(8):
        plt.plot(gauge_measured, np.mean(raw_samples, axis=1)[:, [tr]], label=f'TR{tr}')
    plt.ylabel('Emitter Position')

    plt.legend()

    # plt.figure()
    # plt.plot(np.mean(unwrapped, axis=-1), averaged_error)
    # plt.grid()
    # plt.title('Error')
    # plt.ylabel('Error (emitter widths)')
    # plt.xlabel('Emitter Position (emitter widths)')

    plt.figure()
    plt.scatter(np.mean(estimate_positions, axis=-1), averaged_error)
    plt.grid()
    plt.title('New Error')
    plt.ylabel('Error (emitter widths)')
    plt.xlabel('Emitter Position (emitter widths)')

    # plt.figure()
    # plt.scatter(np.mean(estimate_positions, axis=-1), averaged_error)
    # plt.grid()
    # plt.title('Error')
    # plt.ylabel('Error (emitter widths)')
    # plt.xlabel('Emitter Position (emitter widths)')

    # error_fft = np.fft.rfft(averaged_error)
    # lin_error_fft = np.fft.rfft(lin_averaged_error)
    # error_frequencies = np.fft.rfftfreq(len(averaged_error), commanded_positions[1] - commanded_positions[0])
    # error_periods = 1 / error_frequencies
    # plt.figure()
    # plt.plot(error_periods, 10*np.log10(np.abs(error_fft)), label='Original')
    # plt.plot(error_periods, 10*np.log10(np.abs(lin_error_fft)), label='Linear Correction')
    # plt.semilogx()
    # plt.grid()
    # plt.title("Periodic Spacial Error")
    # plt.ylabel('Error (dB)')
    # plt.xlabel('Error Period (emitter widths)')
    # plt.legend()

    plt.show()


if __name__ == '__main__':
    main()
