# An Open Source Incremental Linear Encoder

TODO: improve photos and pick one

![Header image of the sensor and reflector PCB](docs/header-no-bg.png)

# Overview

| Parameter    | Value            |
| ------------ | ---------------- |
| Encoder Type | Incremental      |
| Method       | Capacitive       |
| Accuracy     | 40µm (1.6 thou)* |
| Output Type  | UART (todo SSI)  |

*At a constant room temperature. This figure is a little conservative compared to the electrical precision and resolution. See [Practical Accuracy Measurements](#practical-accuracy-measurements) for a summary of the measured error.

## Quickstart

1. Order the 4-layer sensor and the reflector ([hardware](hardware/README.md)).
2. Assemble.
3. Flash the [firmware](firmware/README.md#building-and-flashing).
4. Apply Kapton for the [0.1mm gap](#mechanical-integration).
5. Set the [trimmer](hardware/README.md#trimmer).
6. Run `LiveView.py` ([tests](tests/README.md)).

## Why Make This

This sensor came out of a long-running personal project. I started by reverse-engineering digital capacitive calipers, and I wanted to publish a working capacitive encoder because I had trouble finding much public information about them.

I hope this project is useful to someone, but my real goal was to learn, not to replace existing pro-grade encoders.

## What's Included

This is a capacitive encoder, the same technology found in older pro-grade capacitive linear scales. Today, capacitive encoders are mostly found in hobby-grade digital calipers.

It is also incremental. It measures position precisely within each 5.08mm period, and counts how many periods it has passed through. At power-up it assumes it is at position zero, so it needs zeroing or homing every time it starts.

The design is split into folders by discipline:

- `hardware`: The KiCad PCB designs.
- `firmware`: Firmware for the sensor PCB.
- `mechanical`: Mechanical test fixtures.
- `tests`: Test and analysis scripts.

Each folder has its own README with deeper dives into its topics.

## Technical Overview

<!-- PHOTO: sensor (grid side up) next to the reflector (pad side up), so the two matching patterns are visible -->

The encoder has two parts: a **sensor PCB** that moves along the axis, and a passive **reflector PCB** fixed along its length. They should not touch. The copper faces sit about 0.1mm apart.

**Sensing.** The underside of the sensor has a repeating row of transmit electrodes, called *emitters*, with eight per 5.08mm period. It also has one long receive (RX) antenna. The reflector's T-shaped pads couple groups of emitters to the RX antenna. Where the reflector sits relative to the sensor decides which emitters couple, and how strongly.

<!-- PHOTO/DIAGRAM: annotated close-up of the emitter grid, RX antenna and reflector pads -->

**Measurement cycle.** The STM32 steps its 8 emitter pins through a fixed 16-step pattern. At each step, some emitters switch low-to-high or high-to-low. Charge couples through the reflector into the RX antenna. A charge integrator captures it, a low-pass filter smooths it, and the ADC oversamples it. The steps run at 16kHz, so a full sequence completes at 1kHz.

**Position estimate.** Each sequence gives a position within one period. The [Functional Description](#functional-description) explains how. Unwrapping successive estimates gives a continuous position. For this to work, the sensor must move less than a quarter of a period (1.27mm) per sequence. At the default 1kHz, that limits speed to about 1.2m/s.

**Output.** UART at 460800 baud. The firmware currently streams raw lane data, and the scripts in `tests/` compute the position on the host. On-sensor position output and an SSI interface are planned.

![System Block Diagram](docs/plots/system-block-diagram.png)

The sections below cover each of these steps in detail.

## Status and Limitations

As a capacitive encoder, it is sensitive to liquid between the boards. At these accuracies, thermal expansion over long distances also matters. Plan for both when you integrate it.

When I started, I hoped for a 1µm noise floor and 10µm electrical accuracy. I'm still working towards that, along with these features:

- Automatic electrical calibration.
- Temperature compensation.
- Less reliance on the STM32L4's analog peripherals, which are getting harder to source. The plan is a more standard STM32 with a discrete analog frontend.
- Improvements to the layout and mechanical design.
- Absolute position sensing.

I'd welcome help with these! Especially the mechanical design, which is far outside my expertise. See [CONTRIBUTING.md](CONTRIBUTING.md) for how to get involved.

# Practical Accuracy Measurements

I measured the error against a Mitutoyo 543-793B-12 digital indicator. The [mechanical README](mechanical/README.md) has more detail on the setup.

I moved the sensor 9mm in 0.1mm steps using my 3D printer. The steps weren't perfect, but that doesn't matter because the indicator gives the true position. I then processed the measurements with a 3-step median filter.

![Four Layer Sensor Error](docs/4-layer-sensor-error-median-filtered.png)

The error has two parts: noise (blue) and averaged error (black).

- **Averaged error** is dominated by a periodic error that correlates with position (the large triangular deviations around 1–3mm and 7–9mm). There is also a smaller error that repeats every emitter (0.635mm), and drift that most likely comes from my 3D printed test assembly.
- **Noise** is smaller than the averaged error. It is mostly white noise, plus a low-frequency resonance of my 3D printer and occasional jumps caused by asymmetric emitter "strengths".

I read the accuracy figure visually from the plots and rounded it conservatively. My mechanical setup and algorithms have too much uncertainty to quote exact numbers. The [tests README](tests/README.md#accuracy-analysis) has the full analysis, including noise PSDs and an Allan deviation.

# Functional Description

The encoder has two key pieces: the sensor and the reflector.

## Sensor PCB

TODO: annotated picture of top and bottom

The sensor is built around an STM32L4, a microcontroller with many built-in analog peripherals.

Its sensing grid is a repeating pattern of 8 separate transmit antennas, the emitters. Alongside them is an RX antenna, which feeds a charge integrator and an anti-alias filter (see [Analog Frontend](#analog-frontend)).

The sensor PCB can be fabricated as a 2-layer board. In practice, though, the shielding from the internal ground layers improved position accuracy a lot, so I recommend the 4-layer build.

## Reflector PCB

The reflector has a row of T-shaped copper pads. They "reflect" the capacitance of four of the eight repeating emitters into the RX antenna.

The reflector can be as long as you can afford. I have only tested a 50mm reflector, for convenience and because I can only measure high accuracy over short distances. To make it longer, repeat the existing pattern of T's and space-filling rectangles in the PCB design.

TODO: annotated picture

## Measurement Cycle

The diagram below gives an overview of each step of the measurement.

![Functional Diagram](docs/plots/functional-diagram.png)

The emitters switch at 16kHz, stepping through 16 states. After all 16, the measurements go through the position algorithm. The timing diagram below shows an example of the 16 states.

![Measurement Sequence Timing Diagram](docs/plots/timing-diagram.png)

The integrator output always has roughly this shape. As the position changes, it appears phase-shifted relative to the zero position.

I use the term **transient** for a change in the emitter states, and the change it induces on the RX antenna. In the algorithms, a transient is the measurement after the [cancellations](#combined-symmetric-measurements) are applied. The firmware uses a few more specific terms for its samples, defined in the [firmware README](firmware/README.md#sample-naming).

# The Position Algorithm

This section builds up the reasoning behind each step of the position algorithm. The steps themselves are best read in the code.

The sensor measures how the reflector lines up with the emitters, which are coupled to the RX antenna through capacitance.

Consider a single emitter. If the reflector overlaps it, there is a strong capacitance from the emitter to the RX antenna. If not, there is no extra capacitance. When an overlapped emitter switches from low to high, the RX antenna sees a pulse.

When the emitter is only partly overlapped, the coupling falls roughly linearly with movement.

![Single Emitter Capacitance](docs/plots/readme-single-emitter-cap.png)

With more emitters, the effect adds up linearly. By driving the first four emitters low-to-high and the next four high-to-low, the size of the pulse tells us where the reflector is.

In the plot, "coupling" goes negative. That means the reflector is aligned with the emitters making the negative transition, not that the capacitance is negative.

![Differential Emitter Coupling vs. Position](docs/plots/readme-differential-emitter-cap.png)

That is technically enough to get a position, but there are two problems:

1. We don't know the pulse size of a fully overlapped emitter, and it changes over time.
2. Because the pattern repeats, each pulse size matches two possible positions. In the plot below, a measurement could mean 3.1 or 4.9, and we can't tell which.

![Position Ambiguity From a Single Pulse](docs/plots/readme-position-ambiguity.png)

Taking more measurements solves both problems. Instead of sampling one location, we "slide" the pattern across all eight emitters, giving eight pulse sizes. The second four are the negatives of the first four, so they combine into four pulses.

![Sliding Pulse Samples](docs/plots/readme-sliding-samples.png)

Each of the four pulses gives two candidate positions, and we could pick the one they all agree on. Near the edges, though, noise makes that choice unreliable. The resulting error is larger than the noise itself, and it is nonlinear.

Finding the zero crossing of the line through the pulses avoids the nonlinearity and gives lower noise. Depending on the convention, there may be a constant offset (-2 in the plot below).

![Zero Crossing of Sampled Pulses](docs/plots/readme-sampled-waveforms.png)

A few practical problems remain:

1. The samples don't always cross zero.
2. A digital line can't repeatedly step in the same direction.
3. The emitters and reflector pads need clearance between them.

## Pulse Sequences That Don't Cross Zero

The signal is periodic, so we can wrap the first pulse around after the last one and interpolate there. A virtual sample at location 4, equal to the negative of location 0, always creates a zero crossing if there wasn't one already.

![Wrapped Samples Creating a Zero Crossing](docs/plots/readme-wrapped-samples.png)

## Repeated Positive/Negative Pulses

True sliding pulses would need the emitter voltages to keep stepping up. A digital line can only go low-to-high once; it has to go high-to-low before it can rise again.

My solution is a partial transient between the full ones, which flips three emitters in each half. Why not flip just one? Because this extra transient can also give a position. Three emitters make a larger signal, and one that works with the same interpolation method.

![Sliding Samples With Three-Emitter Transients](docs/plots/readme-sliding-samples-hidden.png)

The three-emitter transients give a pulse sequence much like the four-emitter one. They only reach 3/4 of the magnitude, but within that range the signal looks the same, so the same zero-crossing method gives a position.

That estimate is shifted ahead by 0.5 emitters, so adding 0.5 brings it into line.

![Zero Crossing With Three-Emitter Transients](docs/plots/readme-sampled-waveforms-hidden.png)

## Non-Zero Spacing

The emitters and reflector pads need electrical clearance between them.

A naive parallel-plate model would say the signal doesn't change while an edge passes over this gap, so positions inside it can't be recovered.

In reality, as long as the gap is small compared to the copper width, fringing at the copper edges adds significant capacitance. The transition is smooth, but unfortunately not a straight line.

Separating the sensor and reflector reduces the problem. I usually use about 0.1mm. The plot below shows the error that remains, despite fringing, when the PCBs touch.

![Fringing Error With PCBs Touching](docs/close-emitter-fringing-error.png)

## Combined Symmetric Measurements

The design takes advantage of a few symmetries in the emitter pattern.

Of the 8 emitters, the second half is always driven as the inverse of the first half. The emitter states are states in time, but what we measure is the difference from one state to the next. The [firmware README](firmware/README.md#emitter-states-and-lanes) shows how this maps to the code.

![Emitter State Transitions](docs/plots/emitter-state-transitions-diagonal.png)

The second half of the sequence is also an inverted repeat of the first half. Each transient in the second half is the negative of its partner in the first half, so subtracting the two doubles the signal.

The transients also interleave. They alternate between flipping three emitters in each half and flipping four. I call these two interleaved sets **lanes**, which leaves two lanes of four values each. Most of my analysis only considers four emitters and four transients, because that describes most of the signal.

Each lane gives one zero-crossing estimate with its own offset. After applying the offsets, the estimates are averaged.

The offsets are relative. It doesn't matter which lane is treated as the reference, as long as the difference between them is consistent.

# Analog Frontend

The RX antenna receives a voltage pulse. Its height depends on the capacitive coupling, and how long it lasts depends on resistive leakage.

![RX Input Chain Schematic](docs/schematics/rx-chain.png)

You can sample that pulse directly with the ADC, but only for low accuracy. It needs very short sample windows and can't be anti-alias filtered well, so it picks up a lot of noise.

Instead, the RX antenna feeds a **charge integrator**. The ratio of its two capacitors sets its gain, and one of them is a trimmer for adjustment. The integrator turns the short pulse into a held step. The ADC can then oversample over a long window, which improves SNR.

An **anti-alias filter** follows the integrator. It removes the above-Nyquist electrical noise that the integrator passes through.

The firmware measures the change from one integrator state to the next, so the integrator never needs a reset.

The [hardware README](hardware/README.md#sensor-analog-frontend-design-details) covers the design in more detail with rationale.

# Mechanical Integration

![Prusa Calibration Assembly](docs/mechanical/cal-prusa-assembled.jpg)

The sensor and reflector PCBs are both aligned with 3mm pins and mounted with M3 fasteners.

The sensor and reflector need a gap between them. I aim for 0.1mm. Without it, the signal is larger, but [physical nonlinearities](#non-zero-spacing) wipe out any SNR benefit.

I haven't measured how sensitive the sensor is to a gap, sideways offset or tilt. The effect doesn't seem large, and in theory the design should tolerate all three reasonably well.

I tried a 3D printed shim to set the gap, but two layers of Kapton tape turned out to be much easier and more accurate.

![Sensor PCB With Kapton Shim](mechanical/calibration-prusa/assembly-photos/2-cal-prusa-pcb-with-kapton.jpg)

The [mechanical README](mechanical/README.md) covers a typical mechanical stackup and the test fixtures.

# License

This project uses two licenses:

| Folders                      | License                                     |
| ---------------------------- | ------------------------------------------- |
| `hardware/`, `mechanical/`   | [CERN-OHL-P-2.0](LICENSE-CERN-OHL-P)        |
| `firmware/`, `tests/`, `docs/` | [MIT](LICENSE-MIT)                        |

Both are permissive. You can use, modify, make and sell the designs and code, including commercially, as long as you keep the copyright and license notices.

Some files are covered by their own licenses instead:

- `firmware/src/cube-mx-autogen/` contains files generated by STM32CubeMX, © STMicroelectronics, under their own license terms.

See [LICENSE](LICENSE) for the summary.
