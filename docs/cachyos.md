# CachyOS Notes

## Packages

```bash
sudo pacman -S python python-evdev python-pyudev python-rich python-typer uv
```

## Workflow

```bash
uv sync --extra dev
sudo ./scripts/install-udev-rules.sh
systemctl --user enable --now ultim8do.service
```

## Caveats

- Verify `systemd --user` is active for the current session.
- Re-login or reconnect the controller after udev rule updates.
