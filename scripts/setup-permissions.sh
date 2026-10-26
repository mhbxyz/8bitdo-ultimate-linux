#!/usr/bin/env bash
# Installe les droits nécessaires au projet (à lancer une fois, avec sudo).
#
#   sudo ./scripts/setup-permissions.sh            # udev + usbmon
#   sudo ./scripts/setup-permissions.sh --uninstall
#
# - udev : ouvre les périphériques USB 8BitDo (MODE 0660, groupe input) et les
#          nœuds hidraw correspondants. Pas de dépendance à systemd-logind.
# - usbmon : charge le module et rend /sys/kernel/debug/usb/usbmon lisible, pour
#          capturer le trafic (dumpcap/tshark ou `cat .../5u`). Optionnel : la
#          phase de mesure peut se faire sans.

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
udevadm trigger --subsystem-match=usb --subsystem-match=hidraw --subsystem-match=input
echo "règle udev installée : $RULE"

# --- usbmon ---------------------------------------------------------------
KREL=$(uname -r)
if [[ ! -d /lib/modules/$KREL ]]; then
    echo
    echo "AVERTISSEMENT : le noyau en cours ($KREL) n'a pas d'arborescence de modules"
    echo "  (/lib/modules/$KREL absent). usbmon ne peut pas être chargé."
    echo "  Modules disponibles : $(ls -d /lib/modules/*/ 2>/dev/null | xargs -n1 basename | tr '\n' ' ')"
    echo "  → redémarrer sur un noyau installé (ex. 7.3.0-3-cachyos) pour les captures USB."
else
    modprobe usbmon || echo "avertissement : modprobe usbmon a échoué" >&2
fi

if ! mountpoint -q /sys/kernel/debug; then
    mount -t debugfs none /sys/kernel/debug 2>/dev/null || true
fi
if [[ -d /sys/kernel/debug/usb/usbmon ]]; then
    chmod 0755 /sys/kernel/debug/usb/usbmon 2>/dev/null || true
    chmod 0644 /sys/kernel/debug/usb/usbmon/* 2>/dev/null || true
    echo "usbmon disponible : /sys/kernel/debug/usb/usbmon -> $(ls /sys/kernel/debug/usb/usbmon | tr '\n' ' ')"
else
    echo "usbmon indisponible (module non chargé ou debugfs non monté) — non bloquant."
fi

echo
echo "Vérification :"
echo "  ls -l /dev/bus/usb/*/*   # doit être crw-rw---- root input pour 2dc8"
echo "  uv run tools/mode-switch.py --dry-run"
