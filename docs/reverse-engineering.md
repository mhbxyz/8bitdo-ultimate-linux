# Reverse Engineering

## Safe Workflow

1. Run `uv run ultim8do report --json` to capture baseline metadata.
2. Use `uv run ultim8do monitor /dev/input/eventX --limit 50` to inspect event traffic.
3. Optionally install the `hid` extra and use `hid-recorder` or `hid-decode` for HID-level investigation.

For control mapping and vendor-specific button checks:

```bash
uv run ultim8do test --path /dev/input/eventX --raw --duration 20
uv run ultim8do test --path /dev/input/eventX --guided
```

If the kernel exposes the controller as `Generic X-Box pad` through `xpad`, Linux is seeing an Xbox-compatible/XInput interface. In that mode, vendor-specific 8BitDo controls such as underside buttons, paddles, or gyro may be absent from `evdev` entirely.

If underside buttons do not appear even in `--raw`, treat them as `not exposed through evdev in this mode` and investigate:

- another controller mode like `DInput`, `Switch`, or `Bluetooth`
- whether a matching `hidraw` node appears in that mode
- HID-level traffic with `hid-recorder` if `hidraw` becomes available

## Suggested Tools

- `evtest`
- `udevadm`
- `hid-recorder`
- `hid-decode`

## Documentation Expectations

- Record transport mode: USB, Bluetooth, or 2.4G dongle.
- Record kernel version and distribution.
- Record any custom SDL mapping needed for gameplay clients.
