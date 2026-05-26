#!/usr/bin/env bash
set -euo pipefail

install -Dm644 "udev/99-8bitdo-ultimate.rules" "/etc/udev/rules.d/99-8bitdo-ultimate.rules"
udevadm control --reload-rules
udevadm trigger --subsystem-match=input --subsystem-match=hidraw || true

printf 'Installed /etc/udev/rules.d/99-8bitdo-ultimate.rules\n'
