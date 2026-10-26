#!/usr/bin/env bash
# Surveille les (re)énumérations des périphériques 8BitDo (VID 2dc8).
# Affiche PID, produit, interfaces et nœuds hidraw/input associés.
set -u
last=""
while true; do
    now=$(for d in /sys/bus/usb/devices/*/idVendor; do
              [ -f "$d" ] && [ "$(cat "$d")" = "2dc8" ] || continue
              dir=$(dirname "$d")
              printf '%s:%s %s %s\n' "$(cat "$dir/idVendor")" "$(cat "$dir/idProduct")" \
                     "$(cat "$dir/product" 2>/dev/null | tr -d ' ')" "$(basename "$dir")"
          done | sort)
    if [ "$now" != "$last" ]; then
        date '+%H:%M:%S'
        echo "$now" | sed 's/^/  /'
        for d in /sys/bus/usb/devices/*; do
            [ -f "$d/idVendor" ] && [ "$(cat "$d/idVendor")" = "2dc8" ] || continue
            for i in "$d":*; do
                [ -d "$i" ] || continue
                drv=$(basename "$(readlink -f "$i/driver" 2>/dev/null)" 2>/dev/null)
                printf '    %s class=%s driver=%s\n' "$(basename "$i")" \
                       "$(cat "$i/bInterfaceClass" 2>/dev/null)" "${drv:-none}"
            done
        done
        for h in /sys/class/hidraw/hidraw*; do
            [ -e "$h" ] || continue
            grep -q 2DC8 "$h/device/uevent" 2>/dev/null && echo "    hidraw: $(basename "$h")"
        done
        echo
        last="$now"
    fi
    sleep 0.5
done
