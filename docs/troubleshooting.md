# Troubleshooting

## `PermissionError` on `/dev/input/event*`

- Confirm the current session has `uaccess` applied by logind.
- Replug the controller after installing the udev rule.
- On systems without `uaccess`, ensure the user can read devices through the `input` group.

## Controller not detected

- Run `uv run ultim8do list --verbose`.
- Inspect `udevadm info --attribute-walk --name=/dev/input/eventX` for vendor and product identifiers.
- Some 8BitDo Ultimate variants expose different product IDs depending on USB, Bluetooth, or 2.4G mode.

## Udev rule changes not applied

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=input --subsystem-match=hidraw
```

## SDL mapping validation warnings

The bundled mapping file is intentionally minimal. Add one mapping per line using the SDL `gamecontrollerdb.txt` format, then rerun `uv run ultim8do sdl validate`.
