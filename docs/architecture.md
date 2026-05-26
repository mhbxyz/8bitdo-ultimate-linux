# Architecture

`ultim8do` is a diagnostics-first CLI for 8BitDo Ultimate controllers on Linux.

## Data Flow

1. `devices.py` discovers candidate devices through `pyudev` and augments them with `evdev` metadata.
2. `doctor.py` runs environment checks and aggregates their status.
3. `report.py` converts runtime state into terminal-friendly or JSON-friendly output.
4. `evdev_reader.py` exposes live event monitoring for `/dev/input/event*`.
5. `sdl.py` validates the local SDL mapping database.

## Design Notes

- The code prefers read-only inspection over mutation.
- Udev rules and systemd units are bundled but not auto-installed.
- The virtual controller module is a stub until a stable uinput design exists.
