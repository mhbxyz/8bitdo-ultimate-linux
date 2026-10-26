#!/usr/bin/env bash
# Bascule le contrôleur USB du bus 5 (celui de la manette) entre l'hôte et la VM.
#
#   sudo ./scripts/usb-passthrough.sh on    # donne le contrôleur à vfio (la VM peut le prendre)
#   sudo ./scripts/usb-passthrough.sh off   # rend le contrôleur à l'hôte
#
# Le contrôleur 0000:c8:00.3 est seul dans son groupe IOMMU (groupe 29) : il porte
# le bus USB 5, donc la manette, un hub VIA, un hub Terminus et le lecteur de
# cartes microSD. Clavier, souris et Bluetooth sont sur un autre contrôleur
# (0000:c6:00.3) et ne sont pas affectés.
#
# Prérequis : un noyau dont les modules sont installés (7.3.0-3-cachyos ou
# 6.18.55-2-cachyos-lts). Avec le noyau 7.2.9-2, /lib/modules est absent et
# vfio-pci ne peut pas être chargé.

set -euo pipefail

PCI=0000:c8:00.3
GROUP=$(basename "$(readlink -f "/sys/bus/pci/devices/$PCI/iommu_group")")
ACTION=${1:-}

if [[ ${EUID} -ne 0 ]]; then
    echo "erreur : à lancer avec sudo" >&2
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
    echo "contrôleur $PCI confié à vfio-pci (groupe $GROUP)"
    ls -l "/dev/vfio/$GROUP"
    echo
    echo "Relance la VM avec :"
    echo "  --device=/dev/vfio/vfio --device=/dev/vfio/$GROUP \\"
    echo "  -e ARGUMENTS=\"-device vfio-pci,host=$PCI\""
    ;;
off)
    echo > "/sys/bus/pci/devices/$PCI/driver_override" || true
    if [[ -e "/sys/bus/pci/drivers/vfio-pci/$PCI" ]]; then
        echo "$PCI" > /sys/bus/pci/drivers/vfio-pci/unbind
    fi
    echo "$PCI" > /sys/bus/pci/drivers/xhci_hcd/bind
    echo "contrôleur $PCI rendu à l'hôte (xhci_hcd)"
    ;;
*)
    echo "usage: $0 on|off" >&2
    exit 1
    ;;
esac
