# ultim8do

Linux tooling for inspecting and validating 8BitDo Ultimate controllers.

## Features

- Enumerate candidate 8BitDo input devices through `pyudev` and `evdev`
- Read live `/dev/input/event*` traffic for a selected device
- Run an interactive control test to validate button and axis mappings
- Run a `doctor` command to check Python, permissions, udev rules, and SDL mappings
- Generate human-readable or JSON reports for bug reports and reverse engineering notes
- Ship Arch packaging metadata, udev rules, and an optional user service

## Stack

- Python 3.12+
- `uv` for dependency management and execution
- `Typer` for the CLI
- `rich` for terminal rendering
- `python-evdev` for `/dev/input/event*`
- `pyudev` for udev inspection
- optional `hid-tools` support through the `hid` extra

## Quick Start

```bash
uv sync --extra dev
uv run ultim8do --help
uv run ultim8do doctor
uv run ultim8do list
```

To install optional HID helpers:

```bash
uv sync --extra dev --extra hid
```

## Common Commands

```bash
uv run ultim8do doctor
uv run ultim8do list --json
uv run ultim8do test
uv run ultim8do inspect /dev/input/event5
uv run ultim8do monitor /dev/input/event5 --limit 20
uv run ultim8do test --path /dev/input/event5 --json --duration 5
uv run ultim8do report --json
uv run ultim8do sdl validate
uv run ultim8do udev path
```

## Udev Rules

Install the bundled rule with root privileges:

```bash
sudo ./scripts/install-udev-rules.sh
```

Or through `make`:

```bash
sudo make install-udev
```

The script installs `udev/99-8bitdo-ultimate.rules` to `/etc/udev/rules.d/` and reloads udev.

## Scope

This repository focuses on inspection and diagnostics first. `virtual_pad.py` intentionally exposes only a placeholder API so the project does not create virtual controllers by default.

## Repository Layout

```text
8bitdo-ultimate-linux/
├── docs/
├── mappings/
├── scripts/
├── src/ultim8do/
├── systemd/
├── tests/
└── udev/
```

## Development

```bash
make sync
make test
make doctor
```

The test suite uses fixtures only and does not require a physical controller.
