# An Open Source Incremental Linear Encoder

TODO: photo goes here

## Key Details

| Parameter    | Value            |
| ------------ | ---------------- |
| Encoder Type | Incremental      |
| Method       | Capacitive       |
| Accuracy     | 40µm (1.6 thou)* |
| Output Type  | UART (todo SSI)  |

*Assuming static room temperature. This is a little conservative for the electrical precision and resolution. For a deep dive on the real measurement error, see [Practical Accuracy Measurements](LINK TODO)

## What's Included

- `hardware`: The kicad PCB designs.
- `firmware`: Firmware for the sensor PCB.
- `mechanical`: Mechanical test fixtures.
- `tests`: Python scripts used for testing accuracy.


# Practical Accuracy Measurements

I measured the error with a Mitutoyo 543-793B-12 digital indicator. More details are in the mechanical readme (TODO link).

I moved the sensor by a total of 9mm in steps of 0.1mm using my 3D printer. The stepsize was not perfect, but it's not a part of the analysis because the indicator tells me a true position of my sensor. I then processed the measurements using a median filter (see the noise section for more information).

![Four Layer Sensor Error](docs/4-layer-sensor-error-median-filtered.png)

There are two parts to the error. The noise, which is shown in blue, and the averaged error, in black.

## Averaged Error

The averaged error has a very long 2-second window, so I'm taking it to be the physical measurement error.

There's a few sources here:
- The largest source is a periodic error that seems to correlate to the posistion. These are the two large triangular deviations around 1~3 and 7~9mm. It might be possible to calibrate this out, but I haven't tried that yet.
- Another source of error is a smaller triangular-looking error per each emitter. This is periodic over one emitter of 0.635mm.
- Finally, a major source of error here is the general drift. From 0~2mm, I think there is a drift of about 20µm. It's hard to say how large this is, but since it's not periodic, it's probably caused by my 3D printed assembly, with little in the way of proper constraints, bending out of shape.

## Noise

The noise is smaller than the averaged error, which is good. I plotted the standard deviation and peak observed error.

![Four Layer Sensor Noise](docs/4-layer-sensor-noise-median-filtered.png)

Below is a PSD of the noise frequencies.

![Four Layer Sensor Noise PSD](docs/4-layer-noise-welch.png)


The noise also has a few sources.

- Most of the noise is white noise. This can be seen in FFTs of the measurements.
- There is one clear frequency where noise is persistent at around 10~14Hz and the next 3 harmonics (on the PSD these are the peaks at the beginning). Sometimes the frequency varies depending on my setup. This low-frequency "noise" is being caused by real physical resonance of my 3D printer's relative z-height by a few µm. I'm working on a better mechanical setup that should help with this. For conservatism, I don't erase it from my analsyis here.
- There is a big spike in the middle of the graph. In short this is caused by assymetric emitter "strengths". When the algorithm jumps from a linearly interpolating using one emitter over another, there is a small change in the output because those emitters don't necesarily predict an identical value. This particular position happened consistnatly jump between two emitters. I believe this can be helped through calibration, but I haven't looked into that yet.

All of these can be helped by averaging and filtering. I only present data here after performing a median filter. An example of completely unfiltered noise is in [this picture](docs/4-layer-sensor-noise-raw.png). I'm keeping the median filter for my analysis because I do think it makes physical sense to keep it long-term.

A final note is on the effect of averaging on this noise. Below is an Allan Deviation.

![Four Layer Sensor Noise PSD](docs/allan-deviation-median-filter.png)

## Error Disposition

I chose to report a conservative number for the precision and resolution. I did that because there is too much uncertainty in my mechancial setup and algorithms for me to feel comfortable listing exact numbers on what I measured.

# Functional Description and Design Details

There are two key pieces of the encoder: The sensor and the reflector.

## Sensor PCB

TODO: annotated picture of top and bottom

The sensor has an STM32L4, a microcontroller with lots of built-in analog peripherals.

The sensor has a sensing grid. In the grid is a repeating pattern of 8 seperate TX antennas, called emitters.

The sensor also has an RX antenna. The RX antenna feeds into a charge integrator and anti-aliasing filter.

TODO: circuit diagram

## Reflector PCB

The reflector PCB has many 'T' shaped copper pads. The goal of these is to 'reflect' the capacitance of the four of the eight repeating emitters into the antenna.

TODO: annotated picture

## Functionality

The alignment of the reflector to the emitters is what the sensor is measuring. The refector and pickup are connected by capacitance.

Consider a single emitter. If the reflector is overlapping that emitter, there is a strong capacitance from the emitter to the recieving antenna. If the reflector is not overlapping that emitter, there is no extra capacitance. When the emitter is overlapped, and a digital transition from low to high is applied, the recieving antenna sees a pulse.

There is a period where the emitter is only partially overlapped by the reflector. The area of overlap decreases roughly linearly with the movement.

TODO: diagram of the capacitance vs. position

With more emitters, the effect stacks linearly. If there are two emitters, double the capacitance is seen.

By driving the first four emitters low-to-high and the next four high-to-low, we can tell where the reflector is based on the size of the pulse.

TODO: diagram of the time-domain signals for various positions showing how we get a position

That's technically enough to get a position. But there are two problems.
1. We don't know the pulse size of a fully overlapped emitter, and it will vary with time.
2. Because of the repeating nature of the design, a measured pulse size actually has two possible positions.

TODO: diagramatically show these

Both of these problems are solved by adding more measurements. Instead of only sampling one location, we 'slide' the pattern across all eight emitters. We then get eight discrete pulse sizes. The second four of these are the negative equivalent to the first four. So these are combined to get four pulses.

TODO: diagram of the four pulses

We can now solve for two positions "choices" using each of the four pulses. We can then determine the common solution across all four pulses. But that can create problems near edges due to noise, which creates a measurement error greater than the signal noise level. It's also nonlinear.

As it happens, a way to get lower noise and to avoid the nonlinearity is to find the zero crossing of the line drawn by the pulses.

TODO: diagram of a nonlinear 'skip', and of the linear interp operation

## Practical Matters

There are some practical matters to consider in the design:

1. The pulses do not always cross zero.
2. We can't directly apply a set of sliding pulses.
3. The emitters and reflectors have non-zero spacing.

### Pulse Sequences That Don't Cross Zero

TODO: photo of non-zero-crossing and the wrapped zero. it should be clear than you can't interp the non-crossing values

Fortunately there is an easy solution here. Because this is periodic, all we need to do is wrap the first pulse after the last pulse and interpolate there. That will always produce a zero crossing if there wasn't already one.

### Practical Sliding Pulses

If we want to apply real sliding pulses, we would need to repeatedly step up the emitter voltages. We can only go low-to-high once in a row. There needs to be a high-to-low transition before another low-to-high can happen.

TODO: image of this

The solution I landed on was a partial transient that flips three of the emitters. Why not flip one emitter? We can actually use the three emitters.

The pulsed three emitters give a similar pulse sequence to the four emitters. The only difference is that it can only reach 3/4ths of the magnitude that the four-emitter sequence can reach. But within that range, the signal looks exactly the same. We can use the same zero-crossing algorithm to determine a position. We only need to subtract 0.5 from the estimate.

TODO: comparison of the four vs three emitters

### Non-Zero Spacing

The emitter and reflector pattern need to have electrical clearance.

If we take the naive assumption of parallel plate capacitance, we would conclude that the measurement signal simply does not change here, and a position between these locations cannot be recovered.

In reality, assuming the spacing is small relative to the copper width, fringing at the copper edges contributes significantly to capacitance. There is actually a smooth and mostly linear transition here.

TODO: Diagram of clearance. Show naive assumption and practical fringing.

## Analog Input

We have a capacitive pulse on the recieving antenna.

TODO: diagram of the rx circuitry with what the signal looks like

### ADC-Only Samples

One way to measure this is to put it directly in to an ADC. At first, this was all I did.

This method works well enough for low-accuracy applications. There are two problems:
1. The ADC needs to use very small sample windows, leading to susceptibility to high-frequency noise.
2. The signal can't be conditioned easily. It's possible to put this through a filter. This would require a follower opamp with a relatively high slew rate to capture the short-lived initial pulse. Also, the shape of the pulse is not conducive to anti-alias filtering. I was getting massive problems with power supply noise while testing near my 3D printer.

### Charge Integrator

A major improvement to this design was the charge integrator. This allows us to widen the ADC window all the way to a zeroth order hold.

The charge integrator creates a gain that is the ratio of the two capacitors. I used a trimmer capacitor for adjustable gain.

This doesn't solve anti-aliasing alone, so an anti-alias filter is added on. The filter slews the signal significantly, but this still results in a better SNR in the presence of my 3D printer's 23kHz noise.
