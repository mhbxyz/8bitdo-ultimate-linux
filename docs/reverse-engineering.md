# Reverse Engineering

## Safe Workflow

1. Run `uv run ultim8do report --json` to capture baseline metadata.
2. Use `uv run ultim8do monitor /dev/input/eventX --limit 50` to inspect event traffic.
3. Optionally install the `hid` extra and use `hid-recorder` or `hid-decode` for HID-level investigation.

## Suggested Tools

- `evtest`
- `udevadm`
- `hid-recorder`
- `hid-decode`

## Documentation Expectations

- Record transport mode: USB, Bluetooth, or 2.4G dongle.
- Record kernel version and distribution.
- Record any custom SDL mapping needed for gameplay clients.
