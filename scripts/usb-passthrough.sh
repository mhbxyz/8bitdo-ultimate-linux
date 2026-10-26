#!/usr/bin/env bash
# Move the USB controller of bus 5 (the pad one) between the host and the VM.
#
#   sudo ./scripts/usb-passthrough.sh on    # hand the controller to vfio (the VM can grab it)
#   sudo ./scripts/usb-passthrough.sh off   # give the controller back to the host
#
# Controller 0000:c8:00.3 is alone in its IOMMU group (group 29). It carries USB
# bus 5, so the pad, a VIA hub, a Terminus hub and the microSD card reader.
# Keyboard, mouse and Bluetooth sit on another controller (0000:c6:00.3) and are
# not affected.
#
# Requirement: a kernel whose modules are installed (7.3.0-3-cachyos or
# 6.18.55-2-cachyos-lts). With kernel 7.2.9-2, /lib/modules is missing and
# vfio-pci cannot be loaded.

set -euo pipefail

PCI=0000:c8:00.3
GROUP=$(basename "$(readlink -f "/sys/bus/pci/devices/$PCI/iommu_group")")
ACTION=${1:-}

if [[ ${EUID} -ne 0 ]]; then
    echo "error: run this with sudo" >&2
    exit 1
fi

case "$ACTION" in
on)
    modprobe vfio-pci
    if [[ -e /sys/bus/pci/devices/$PCI/driver ]]; then
        echo "$PCI" > "/sys/bus/pci/devices/$PCI/driver/unbind"
    fi
    echo vfio-pci > "/sys/bus/pci/devices/$PCI/driver_override"
    echo "$PCI" > /sys/bus/pci/drivers/vfio-pci/bind
    echo "controller $PCI handed to vfio-pci (group $GROUP)"
    ls -l "/dev/vfio/$GROUP"
    echo
    echo "Restart the VM with:"
    echo "  --device=/dev/vfio/vfio --device=/dev/vfio/$GROUP \\"
    echo "  -e ARGUMENTS=\"-device vfio-pci,host=$PCI\""
    ;;
off)
    echo > "/sys/bus/pci/devices/$PCI/driver_override" || true
    if [[ -e "/sys/bus/pci/drivers/vfio-pci/$PCI" ]]; then
        echo "$PCI" > /sys/bus/pci/drivers/vfio-pci/unbind
    fi
    echo "$PCI" > /sys/bus/pci/drivers/xhci_hcd/bind
    echo "controller $PCI given back to the host (xhci_hcd)"
    ;;
*)
    echo "usage: $0 on|off" >&2
    exit 1
    ;;
esac
