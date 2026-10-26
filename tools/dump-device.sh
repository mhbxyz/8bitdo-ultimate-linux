#!/usr/bin/env bash
# Photographie l'état USB des périphériques 8BitDo présents.
set -u
VID=${1:-2dc8}
echo "=== lsusb ==="
lsusb | grep -i -E "8bitdo|$VID" || echo "(aucun)"
for d in /sys/bus/usb/devices/*; do
    [ -f "$d/idVendor" ] && [ "$(cat "$d/idVendor")" = "$VID" ] || continue
    echo
    echo "=== $(basename "$d") ==="
    for f in idVendor idProduct product manufacturer serial bcdDevice speed version \
             bDeviceClass bDeviceSubClass bDeviceProtocol bNumInterfaces bNumConfigurations; do
        [ -f "$d/$f" ] && printf '  %-18s %s\n' "$f" "$(cat "$d/$f")"
    done
    for i in "$d":*; do
        [ -d "$i" ] || continue
        drv=$(basename "$(readlink -f "$i/driver" 2>/dev/null)" 2>/dev/null)
        printf '  interface %-16s class=%s/%s/%s driver=%s\n' "$(basename "$i")" \
               "$(cat "$i/bInterfaceClass")" "$(cat "$i/bInterfaceSubClass")" \
               "$(cat "$i/bInterfaceProtocol")" "${drv:-none}"
    done
    lsusb -v -d "$(cat "$d/idVendor"):$(cat "$d/idProduct")" 2>/dev/null | sed -n '/Descriptor:/,$p' | head -60
done
echo
echo "=== hidraw ==="
for h in /sys/class/hidraw/hidraw*; do
    [ -e "$h" ] || continue
    grep -q -i "$VID" "$h/device/uevent" 2>/dev/null && {
        echo "$(basename "$h") : $(grep HID_NAME "$h/device/uevent" | cut -d= -f2-)"
        echo "  report descriptor : $(cat "$h/device/report_descriptor" 2>/dev/null | xxd -p | head -c 200)…"
    }
done
