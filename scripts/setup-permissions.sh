#!/usr/bin/env bash
# Install the permissions this project needs (run once, with sudo).
#
#   sudo ./scripts/setup-permissions.sh            # udev + usbmon
#   sudo ./scripts/setup-permissions.sh --uninstall
#
# - udev: opens the 8BitDo USB devices (MODE 0660, group input) and the matching
#         hidraw nodes. No dependency on systemd-logind.
# - usbmon : charge le module et rend /sys/kernel/debug/usb/usbmon lisible, pour
#          capturer le trafic (dumpcap/tshark ou `cat .../5u`). Optionnel : la
#          phase de mesure peut se faire sans.

set -euo pipefail

RULE=/etc/udev/rules.d/99-8bitdo-ultimate3mode.rules
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/udev/99-8bitdo-ultimate3mode.rules"

if [[ ${EUID} -ne 0 ]]; then
    echo "error: run this with sudo" >&2
    exit 1
fi

if [[ ${1:-} == "--uninstall" ]]; then
    rm -f "$RULE"
    udevadm control --reload-rules
    echo "udev rule removed."
    exit 0
fi

install -m 0644 "$SRC" "$RULE"
udevadm control --reload-rules
udevadm trigger --subsystem-match=usb --subsystem-match=hidraw --subsystem-match=input
echo "udev rule installed: $RULE"

# --- usbmon ---------------------------------------------------------------
KREL=$(uname -r)
if [[ ! -d /lib/modules/$KREL ]]; then
    echo
    echo "WARNING: the running kernel ($KREL) has no module tree"
    echo "  (/lib/modules/$KREL is missing). usbmon cannot be loaded."
    echo "  Available modules: $(ls -d /lib/modules/*/ 2>/dev/null | xargs -n1 basename | tr '\n' ' ')"
    echo "  -> reboot on an installed kernel (e.g. 7.3.0-3-cachyos) for USB captures."
else
    modprobe usbmon || echo "warning: modprobe usbmon failed" >&2
fi

if ! mountpoint -q /sys/kernel/debug; then
    mount -t debugfs none /sys/kernel/debug 2>/dev/null || true
fi
if [[ -d /sys/kernel/debug/usb/usbmon ]]; then
    chmod 0755 /sys/kernel/debug/usb/usbmon 2>/dev/null || true
    chmod 0644 /sys/kernel/debug/usb/usbmon/* 2>/dev/null || true
    echo "usbmon available: /sys/kernel/debug/usb/usbmon -> $(ls /sys/kernel/debug/usb/usbmon | tr '\n' ' ')"
else
    echo "usbmon unavailable (module not loaded or debugfs not mounted), not blocking."
fi

echo
echo "Check:"
echo "  ls -l /dev/bus/usb/*/*   # should be crw-rw---- root input for 2dc8"
echo "  uv run tools/mode-switch.py --dry-run"
