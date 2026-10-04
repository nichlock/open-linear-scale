# SPC Firmware Test

Reads a Mitutoyo SPC gauge with a NUCLEO-F446RE and prints each reading over the ST-Link USB serial port.

## Wiring

| Gauge pin | Signal | Nucleo pin | Mode |
|---|---|---|---|
| 1 | GND | GND | |
| 2 | DATA | D4 | Input, internal pull-up |
| 3 | CK | D3 | Input, internal pull-up |
| 5 | REQ | D2 | Open-drain output |

REQ is open-drain, so the gauge's internal 1.55 V pull-up sets the high level. No external parts are needed.

## Build and run

```sh
pio run -t upload
pio device monitor
```

Serial runs at 115200 baud. A new line prints about every 10 ms.

## Output

| Line | Meaning |
|---|---|
| `12.3450` | Measured value, with the gauge's sign and decimal point |
| `FAULT: no connection (timeout)` | No clock from the gauge within 200 ms of a request |
| `FAULT: invalid data` | A full frame arrived, but its first four digits were not all `F` |

The unit digit (mm or in) is ignored.
