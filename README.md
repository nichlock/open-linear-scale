# An Open Source Incremental Linear Encoder

TODO: photo goes here

## Key Details

| Parameter    | Value                               |
| ------------ | ----------------------------------- |
| Encoder Type | Incremental                         |
| Method       | Capacitive                          |
| Resolution   | <2µm (TODO get final numbers here)* |
| Accuracy     | (todo)*                             |
| Output Type  | UART (todo SSI)                     |

## What's Included

- `hardware`: The kicad PCB designs.
- `firmware`: Firmware for the sensor PCB.
- `mechanical`: Mechanical test fixtures.
- `tests`: Python scripts used for testing accuracy.


# Practical Accuracy Measurements

TODO

# Functional Description and Design Details

There are two key pieces of the encoder: The sensor and the reflector.

## Sensor PCB

TODO: annotated picture of top and bottom

The sensor has an STM32L4, a microcontroller with lots of useful analog peripherals.

The sensor has a sensing grid. In the grid is a repeating pattern of 8 seperate TX antennas, called emitters.

The sensor also has an RX antenna. The RX antenna feeds into a charge integrator and a filter.

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

## Analysis

It is ideal to choose a noise floor and derive the required SNR to achieve that noise.

For this design, I wanted a challenge. I chose an ambitious target accuracy of 1µm. That is ideally the noise floor before filtering. I don't necessarily have to achieve it. 

### Mathematical Definitions

**Knowns**

| Variable | Value        | Unit type | Description                                    |
| -------- | ------------ | --------- | ---------------------------------------------- |
| $A$      | 1µm=0.04mil  | Length    | Target Noise Floor                             |
| $s$      | 25mil        | Length    | Emitter period.                                |
| $C_i$    | 12-bit value | Counts    | The four transient conversions.                |
| $C_e$    | ideally low  | Counts    | Noise seen by the ADC measurements, in counts. |

**Unkowns**

| Variable  | Unit type | Description                                                                  |
| --------- | --------- | ---------------------------------------------------------------------------- |
| $V_m$     | Volts     | Voltage pulse magnitude produced by shifting the scale by one emitter width. |
| $C_m$     | Counts    | $V_m$ converted to ADC counts.                                               |
| $C_{MAX}$ | Counts    | The maximum pulse magnitude on the RX pad (four emitters perfectly aligned). |

I define the transient conversions as:

$C_i=V_m\times |x-i|$

Where $i=[0...3]$

We use a zero-crossing to determine a position estimate.

$\hat{P}=\frac{C_{i}}{(C_i-C_{i+1})}$

I compared the error visually and found a worst-case error:

$P_e=\frac{C_e}{C_m}$

The target voltage magnitude when using zero-crossing is:

$C_m=\frac{C_e}{\left(\frac{A}{s}\right)}$

or: 

$s = \frac{A\:\times \:C_m}{C_e}$


Here are some example values for 1µm. For example, if you have 5 ADC counts worth of noise, you need each emitter pulse to contribute 3125 ADC counts.

| $C_e$ | $C_m$ |
| ----- | ----- |
| 1     | 625   |
| 3     | 1875  |
| 5     | 3125  |
| 10    | 6250  |

For a standard deviation of 1µm, you would need to target an SNR of ~34 dB. For a 3.3V supply that's equivalent to 1.3mV.
