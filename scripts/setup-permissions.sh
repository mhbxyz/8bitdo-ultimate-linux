#!/usr/bin/env bash
# Installe les droits nécessaires au projet (à lancer une fois, avec sudo).
#
#   sudo ./scripts/setup-permissions.sh            # udev + usbmon
#   sudo ./scripts/setup-permissions.sh --uninstall
#
# - udev : ouvre /dev/bus/usb/** des périphériques 8BitDo à l'utilisateur de la session
#          (TAG+="uaccess", pas de groupe à maintenir, ACL posée par systemd-logind).
# - usbmon : charge le module et rend /sys/kernel/debug/usb/usbmon lisible, ce qui permet
#          de capturer le trafic USB avec dumpcap/tshark (ou `cat /sys/kernel/debug/usb/usbmon/5u`).

set -euo pipefail

RULE=/etc/udev/rules.d/99-8bitdo-ultimate3mode.rules
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/udev/99-8bitdo-ultimate3mode.rules"

if [[ ${EUID} -ne 0 ]]; then
    echo "erreur : à lancer avec sudo" >&2
    exit 1
fi

if [[ ${1:-} == "--uninstall" ]]; then
    rm -f "$RULE"
    udevadm control --reload-rules
    echo "règle udev supprimée."
    exit 0
fi

install -m 0644 "$SRC" "$RULE"
udevadm control --reload-rules
udevadm trigger --subsystem-match=usb --subsystem-match=hidraw
echo "règle udev installée : $RULE"

# --- usbmon ---------------------------------------------------------------
modprobe usbmon || echo "avertissement : modprobe usbmon a échoué" >&2
if ! mountpoint -q /sys/kernel/debug; then
    mount -t debugfs none /sys/kernel/debug 2>/dev/null || true
fi
if [[ -d /sys/kernel/debug/usb/usbmon ]]; then
    chmod 0755 /sys/kernel/debug/usb/usbmon 2>/dev/null || true
    chmod 0644 /sys/kernel/debug/usb/usbmon/* 2>/dev/null || true
    echo "usbmon disponible : /sys/kernel/debug/usb/usbmon (bus 5 → fichier 5u)"
    ls /sys/kernel/debug/usb/usbmon
else
    echo "avertissement : usbmon indisponible (debugfs non monté ?)" >&2
fi

echo
echo "Connectez le pad puis vérifiez avec :"
echo "  ./tools/dump-device.sh"
