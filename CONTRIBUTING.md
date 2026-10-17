# Contributing

Thanks for your interest in this project! It started as a personal learning project, and I'd like it to grow with help from people who know more than I do in some areas.

## How can you help?

Where help is most needed:

- **Mechanical design**: I'm not a mechanical engineer. The current calibration fixture is 3D printed, flexes, and depends on a Prusa printer as its motion stage. Better fixtures, a machined version, or ways to mount the sensor on a real machine would all be valuable. See the [mechanical README](mechanical/README.md).
- Testing: Results from other builds would help a lot. See the [tests README](tests/README.md).
- Firmware: There are still features to add to the firmware, and new ideas are welcome. See the [firmware README](firmware/README.md).

## How to Get Involved

1. **Open an issue first** for anything bigger than a small fix. Describe what you'd like to change and why, so we can agree on the approach before you put time into it.
2. **Send a pull request** with the change. Keep each pull request to one topic.
3. **Share results.** If you build one, I'd love to see photos and measurements in an issue, even if it didn't work well.

## Guidelines

- **Mechanical parts:** Include the source CAD (STEP, and the native file if you have one) along with any STLs.
- **Firmware:** This is a PlatformIO project. Make sure the `release` environment builds before you send a pull request.
- **PCB designs:** Use KiCad 9. Please keep schematic and layout changes in the same pull request, and note any footprint or BOM changes.

## License

By contributing, you agree that your contributions are licensed under the same terms as the rest of the project. See the [License](README.md#license) section of the main README.
