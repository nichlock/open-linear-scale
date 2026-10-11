# An Open Source Incremental Linear Encoder

TODO: photo goes here

# Overview

| Parameter    | Value            |
| ------------ | ---------------- |
| Encoder Type | Incremental      |
| Method       | Capacitive       |
| Accuracy     | 40µm (1.6 thou)* |
| Output Type  | UART (todo SSI)  |

*Assuming static room temperature. This is a little conservative for the electrical precision and resolution. For a summary of the real measurement error, see [Practical Accuracy Measurements](#practical-accuracy-measurements).

## Quickstart

1. Order the 4-layer sensor and the reflector ([hardware](hardware/README.md)).
2. Assemble.
3. Flash the [firmware](firmware/README.md#building-and-flashing).
4. Apply Kapton for the [0.1mm gap](#mechanical-integration).
5. Set the [trimmer](hardware/README.md#trimmer).
6. Run `LiveView.py` ([tests](tests/README.md)).

## Why make this

This sensor is the outcome of a personal project I've had for a while. I started by simply reverse-engineering digital capacitive calipers, and I wanted to publish a functional capacitive encoder since I had trouble finding much information on them publicly available.

I hope this project can be useful to someone, but my real goal was to learn more, not to replace existing pro-grade encoders.

## What's Included

This is an incremental capacitive encoder. It's the same technology as what you would find on older pro-grade capacitive linear scales. These days incremental capacitive encoders are mostly found on hobby-grade digital calipers.

This sensor is incremental. It detects a position precisely within periods of 5.08mm. Outside of those periods, it coarsely counts number of 5.08mm periods it has passed through. At power-up, it assumes it is at position zero. The sensor would require zeroing/homing on every power-up because of that.

There are a few disciplines of the design work. These are split up in the directories:
- `hardware`: The kicad PCB designs.
- `firmware`: Firmware for the sensor PCB.
- `mechanical`: Mechanical test fixtures.

There is also test code in the `tests` directory.

Each has its own readme with deeper-dives into some topics.

## Technical Overview

<!-- PHOTO: sensor (grid side up) next to the reflector (pad side up), so the two matching patterns are visible -->

The encoder has two parts: a **sensor PCB** that moves along the axis, and a passive **reflector PCB** fixed along its length. They should not touch. The copper faces sit about 0.1 mm apart.

**Sensing.** The underside of the sensor has a repeating row of transmit electrodes, called *emitters*. There are eight per 5.08 mm period. The sensor also has one long receive (RX) antenna. The reflector has T-shaped pads which couple groups of emitters to the RX antenna. The position of the reflector relative to the sensor changes emitters couple and how strongly they couple.

<!-- PHOTO/DIAGRAM: annotated close-up of the emitter grid, RX antenna and reflector pads -->

**Measurement cycle.** The STM32 steps the emitters through a fixed 16-step pattern on its 8 emitter GPIO pins. At each step, some emitters transition high-to-low or low-to-high. A charge couples through the reflector into the RX antenna and is captured by a charge integrator. The integrated charge is low-pass filtered and oversampled by the ADC. One full sequence takes 1 ms by default. The steps run at 16 kHz, so a full sequence completes at 1 kHz.

**Position estimate.** The [Functional Description](#functional-description) section details how a position within the period is derived from the pulses. Successive estimates are unwrapped into a continuous position, so the sensor must move less than a quarter of a period (1.27 mm) per sequence. That works out to about 1.2 m/s at the default 1 ms sequence.

**Output.** UART at 460800 baud. The firmware currently streams the raw lane data, and the scripts in `tests/` compute the position on the host. On-sensor position output and an SSI interface are planned.

![System Block Diagram](docs/plots/system-block-diagram.png)

The sections below cover each of these steps in detail.

## Status and Limitations

This is a capacitive encoder. It is sensitive to liquid ingress. At these sensitivities, there are also concerns of thermal expansion over large distances. These should be considered in the implementation.

When I set out on this project, I hoped for a noise floor of 1µm and an electrical accuracy of 10µm. I'm still working towards that. There's a few more features that I'm working on:
- Automatic Electrical Calibration.
- Temperature compensation.
- Reduce reliance on the STM32L4's analog peripherals (since it is becoming harder to get), and replace with a more standard STM32 and a discrete analog frontend.
- Various improvements to the layout and mechanical design.
- Absolute position sensing.

# Practical Accuracy Measurements

I measured the error with a Mitutoyo 543-793B-12 digital indicator. More details are in the [mechanical readme](mechanical/README.md).

I moved the sensor by a total of 9mm in steps of 0.1mm using my 3D printer. The stepsize was not perfect, but it's not a part of the analysis because the indicator tells me a true position of my sensor. I then processed the measurements using a 3-step median filter.

![Four Layer Sensor Error](docs/4-layer-sensor-error-median-filtered.png)

There are two parts to the error. The noise, which is shown in blue, and the averaged error, in black.

- The averaged error is dominated by a periodic error that correlates with position (the large triangular deviations around 1~3 and 7~9mm), a smaller error that repeats every emitter (0.635mm), and drift that is most likely from my 3D printed test assembly.
- The noise is smaller than the averaged error. It is mostly white noise, plus a low-frequency resonance of my 3D printer and occasional jumps caused by asymmetric emitter "strengths".

I chose to report a rough conservative number for the accuracy, read visually from the plots, because there is too much uncertainty in my mechanical setup and algorithms to list exact numbers. The full analysis, including noise PSDs and an Allan deviation, is in the [tests README](tests/README.md#accuracy-analysis).

# Functional Description

There are two key pieces of the encoder: The sensor and the reflector.

## Sensor PCB

TODO: annotated picture of top and bottom

The sensor has an STM32L4, a microcontroller with lots of built-in analog peripherals.

The sensor has a sensing grid. In the grid is a repeating pattern of 8 separate TX antennas, called emitters.

The sensor also has an RX antenna. The RX antenna feeds into a charge integrator and anti-aliasing filter.

![RX Input Chain Schematic](docs/schematics/rx-chain.png)

The sensor PCB was designed to be fully compatible with a 2-layer fabrication. But in practice the shielding of the internal ground layers helped the position accuracy a lot, so I recommend the full 4 layer build.

## Reflector PCB

The reflector PCB has many 'T' shaped copper pads. The goal of these is to 'reflect' the capacitance of the four of the eight repeating emitters into the antenna.

It's possible to make the reflector as long as you can afford. I have only tested on a reflector with a 50mm travel for convenience (and because I can only measure high accuracy in small increments). To make it longer, you would simply have to copy a repeat of the existing pattern of T's and space-filling rectangles in the PCB design.

TODO: annotated picture

## Measurement Cycle

The measurement cycle runs a 16-step measurement sequence that is covered in detail below. This is an overview of each step of the sensing algorithm.

![Functional Diagram](docs/plots/functional-diagram.png)

The sensing hardware operates on a 16kHz signal. There are 16 pulses that it runs through. Once it runs all 16 pulses, it puts those measurements through the position algorithm. The timing diagram below illustrates an example of the 16 states.

![Measurement Sequence Timing Diagram](docs/plots/timing-diagram.png)

The integrator output always looks something like the shown image, but as the position varies, it will look like it is phase-shifted compared to the zero position.

I use the term **transient** for the change in the emitter states and the change it induces on the receiving antenna. When used in the algorithms, it represents the measurement after the [cancellations](#combined-symmetric-measurements) are performed. The firmware uses a few more specific terms for its samples, which are defined in the [firmware README](firmware/README.md#sample-naming).

# The Position Algorithm

I go over the position algorithm here. Rather than simply explain the steps, which is better done by the implementation in code, my goal here is to build up the rationale behind why each step is needed.

The alignment of the reflector to the emitters is what the sensor is measuring. The reflector and pickup are connected by capacitance.

Consider a single emitter. If the reflector is overlapping that emitter, there is a strong capacitance from the emitter to the receiving antenna. If the reflector is not overlapping that emitter, there is no extra capacitance. When the emitter is overlapped, and a digital transition from low to high is applied, the receiving antenna sees a pulse.

There is a period where the emitter is only partially overlapped by the reflector. The area of overlap decreases roughly linearly with the movement.

![Single Emitter Capacitance](docs/plots/readme-single-emitter-cap.png)

With more emitters, the effect stacks linearly. By driving the first four emitters low-to-high and the next four high-to-low, we can tell where the reflector is based on the size of the pulse.

In the plot, "coupling" goes negative. This just means that the sensor is aligned with the "negative" voltage transient of the sensor, not negative capacitance.

![Differential Emitter Coupling vs. Position](docs/plots/readme-differential-emitter-cap.png)

That's technically enough to get a position. But there are two problems.
1. We don't know the pulse size of a fully overlapped emitter, and it will vary with time.
2. Because of the repeating nature of the design, a measured pulse size actually has two possible positions. For example, in the picture below we would measure positions of 3.1 or 4.9, and we don't know which we have.

![Position Ambiguity From a Single Pulse](docs/plots/readme-position-ambiguity.png)

Both of these problems are solved by adding more measurements. Instead of only sampling one location, we 'slide' the pattern across all eight emitters. We then get eight discrete pulse sizes. The second four of these are the negative equivalent to the first four. So these are combined to get four pulses.

![Sliding Pulse Samples](docs/plots/readme-sliding-samples.png)

We can now solve for two positions "choices" using each of the four pulses. We can then determine the common solution across all four pulses. But that can create problems near edges due to noise, which creates a measurement error greater than the signal noise level. It's also nonlinear.

A way to get lower noise and to avoid the nonlinearity is to find the zero crossing of the line drawn by the pulses. Depending on the convention there might be a constant offset (-2 in the picture below).

![Zero Crossing of Sampled Pulses](docs/plots/readme-sampled-waveforms.png)

There are some practical matters left consider in the design and algorithm:

1. The samples do not always cross zero.
2. We can't repeatedly apply positive or negative pulses on a digital line.
3. The emitters and reflectors have non-zero spacing.

## Pulse Sequences That Don't Cross Zero

Fortunately there is an easy solution here. Because this is periodic, all we need to do is wrap the first pulse after the last pulse and interpolate there. We create a virtual sample at location 4 that is equal to the negative of location 0. That will always produce a zero crossing if there wasn't already one.

![Wrapped Samples Creating a Zero Crossing](docs/plots/readme-wrapped-samples.png)

## Repeated Positive/Negative Pulses

If we want to apply real sliding pulses, we would need to repeatedly step up the emitter voltages. We can only go low-to-high once in a row. There needs to be a high-to-low transition before another low-to-high can happen.

The solution I landed on was a partial transient that flips three of the emitters. Why not flip one emitter? We still want to use this extra transient to derive position information. Otherwise it is somewhat wasted. Three emitters create a larger signal, and one where we can still derive a position using the same interpolation method.

![Sliding Samples With Three-Emitter Transients](docs/plots/readme-sliding-samples-hidden.png)

The pulsed three emitters give a similar pulse sequence to the four emitters. The only difference is that it can only reach 3/4ths of the magnitude that the four-emitter sequence can reach. But within that range, the signal looks exactly the same. We can use the same zero-crossing algorithm to determine a position. 

The estimate is slightly different: it's shifted ahead by an extra 0.5 emitters. We only need to add 0.5 to the estimate to get a match.

![Zero Crossing With Three-Emitter Transients](docs/plots/readme-sampled-waveforms-hidden.png)

## Non-Zero Spacing

The emitter and reflector pattern need to have electrical clearance.

If we take the naive assumption of parallel plate capacitance, we would conclude that the measurement signal simply does not change here, and a position between these locations cannot be recovered.

In reality, assuming the spacing is small relative to the copper width, fringing at the copper edges contributes significantly to capacitance. There is actually a smooth transition here. Unfortunately the transition is not simply a "straight line".

This is less of an issue if the sensor and reflector are separated. I usually separate by about 0.1mm. I tried plotting the error without that separation. The image below gives an example of the error, despite fringing, that will happen without a spacing (with the PCBs touching).

![Fringing Error With PCBs Touching](docs/close-emitter-fringing-error.png)

## Combined Symmetric Measurements

There are a few symmetries that I take advantage of in the sensor and signals.

We have 8 emitters that we pulse high and low. The second half of the emitters is always the inverse of the first half.

The emitter states are states in time, but what we measure is based on the difference between one state and the next. The [firmware README](firmware/README.md#emitter-states-and-lanes) shows how this maps to the code.

![Emitter State Transitions](docs/plots/emitter-state-transitions-diagonal.png)

Notice that the second half is an inverted repeat of the first half. 

Also, there is also an interleaved pattern. The first transient has six emitters changing, the second four, then three, four, and so on. I've called these two patterns "lanes".

We're left with two lanes of four values each. In most of my analysis, I only consider four emitters and four transient patterns, because that mostly describes the signals we get.

Finally, from each transient in each lane, we can get a position estimate as described above. We get 8 estimates. Each one has its own offset. After applying the offset, we can average all of these together. 

(Note that the offsets are all relative. It's not critical whether an offset starts at one transient or another. It's just important that the difference relative to each other is consistent.)

# Analog Frontend

We receive a voltage pulse on the receiving antenna. The height of the pulse depends on the capacitive coupling, and the length of time that the pulse lasts depends on the resistive leakage.

![RX Input Chain Schematic](docs/schematics/rx-chain.png)

Sampling that pulse directly with the ADC works for low accuracy, but it needs very short sample windows and can't be anti-alias filtered well, so it is vulnerable to noise. Instead, the RX antenna feeds a **charge integrator**, whose gain is set by the ratio of its two capacitors (one is a trimmer for adjustable gain). The integrator turns the short pulse into a held step, which lets the ADC oversample over a long window for better SNR. An **anti-alias filter** after the integrator handles the above-Nyquist electrical noise that the integrator passes through. The firmware measures the change from one integrator state to the next, so the integrator never needs to be reset.

The design rationale, VREF and the trimmer setup are covered in more detail in the [hardware README](hardware/README.md#analog-frontend).

# Mechanical Integration

TODO: Photo of design

The sensor PCB and reflector PCB were both designed to be aligned using 3mm pins and then mounted using M3 fasteners.

There needs to be a separation between the sensor PCB and the reflector. I aim for 0.1mm. Without this, this signal is larger, but [physical nonlinearities](#non-zero-spacing) eat up any SNR benefit.

I have not determined the sensitivity to this gap, to offset, or to tilt. It does not seem to be massive. In theory it should perform relatively well against these.

I tried 3D printing a shim for this, but I found that a much easier and more accurate way to create that separation was two layers of Kapton tape.

TODO: photo of kapton'd sensor board

A typical mechanical stackup, and the test fixtures, are covered in the [mechanical README](mechanical/README.md).

# License

TODO: hardware (`hardware/`, `mechanical/`) under CERN-OHL-P-2.0, firmware and software (`firmware/`, `tests/`) under MIT. Files generated by STM32CubeMX keep STMicroelectronics' license.
