#!/usr/bin/env python3
"""Bascule la manette 8BitDo en mode configuration (équivalent du « knock » officiel).

En mode Xbox la manette n'expose aucun canal de configuration : le logiciel 8BitDo
la force à ré-énumérer en lui envoyant une init Xbox puis une rafale de rumble sur
l'endpoint interrupt OUT. Elle revient alors avec un autre PID et un canal HID
(report 0x81) sur lequel passent les trames de configuration.

    uv run tools/mode-switch.py            # envoie la séquence et attend la ré-énumération
    uv run tools/mode-switch.py --dry-run  # affiche seulement les paquets
    uv run tools/mode-switch.py --pid 0x2030
"""

from __future__ import annotations

import argparse
import sys
import time

import usb.core
import usb.util

VID = 0x2DC8
PID_3MODE_XBOX = 0x2030

# Séquence relevée dans les captures USBPcap du logiciel officiel (famille Ultimate).
INIT_SEQUENCE: list[bytes] = [
    bytes.fromhex("01 03 02"),  # init LED Xbox
    bytes.fromhex("02 08 03"),  # init contrôleur
    bytes.fromhex("01 03 02"),  # init LED Xbox (bis)
    bytes.fromhex("01 03 06"),  # déclencheur du mode configuration
    bytes.fromhex("00 08 00 01 00 00 00 00"),  # rumble gauche
    bytes.fromhex("00 08 00 00 01 00 00 00"),  # rumble droit
    bytes.fromhex("00 08 00 01 01 00 00 00"),  # les deux
    bytes.fromhex("00 08 00 05 01 00 00 00"),  # fort
    bytes.fromhex("00 08 00 00 00 00 00 00"),  # arrêt
]

DELAY = 0.015  # 15 ms entre paquets, comme le logiciel officiel


def devices(vid: int = VID) -> list[usb.core.Device]:
    return list(usb.core.find(find_all=True, idVendor=vid))


def describe(dev: usb.core.Device) -> str:
    try:
        product = usb.util.get_string(dev, dev.iProduct) if dev.iProduct else ""
    except (usb.core.USBError, ValueError):
        product = "?"
    return (
        f"{dev.idVendor:04x}:{dev.idProduct:04x} bus {dev.bus} addr {dev.address} "
        f"« {product} »"
    )


def send_sequence(pid: int, interface: int, endpoint: int, delay: float) -> None:
    dev = usb.core.find(idVendor=VID, idProduct=pid)
    if dev is None:
        sys.exit(f"périphérique {VID:04x}:{pid:04x} introuvable")

    print(f"cible : {describe(dev)}")
    if dev.is_kernel_driver_active(interface):
        print(f"détachement du pilote noyau sur l'interface {interface}")
        dev.detach_kernel_driver(interface)

    usb.util.claim_interface(dev, interface)
    try:
        for i, packet in enumerate(INIT_SEQUENCE, 1):
            print(f"  [{i}/{len(INIT_SEQUENCE)}] {packet.hex(' ')}")
            dev.write(endpoint, packet, timeout=1000)
            time.sleep(delay)
    except usb.core.USBError as exc:
        # la manette peut se déconnecter en plein milieu : c'est le comportement attendu
        print(f"  (transfert interrompu : {exc})")
    finally:
        try:
            usb.util.release_interface(dev, interface)
        except usb.core.USBError:
            pass


def wait_reenumeration(previous: list[tuple[int, int]], timeout: float) -> list[usb.core.Device]:
    deadline = time.monotonic() + timeout
    seen = set(previous)
    while time.monotonic() < deadline:
        current = devices()
        new = [d for d in current if (d.idVendor, d.idProduct) not in seen]
        if new:
            return new
        time.sleep(0.2)
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=lambda s: int(s, 0), default=PID_3MODE_XBOX)
    parser.add_argument("--interface", type=int, default=0)
    parser.add_argument("--endpoint", type=lambda s: int(s, 0), default=0x01)
    parser.add_argument("--delay", type=float, default=DELAY)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("séquence de bascule :")
    for packet in INIT_SEQUENCE:
        print(f"  {packet.hex(' ')}")
    if args.dry_run:
        return 0

    before = [(d.idVendor, d.idProduct) for d in devices()]
    send_sequence(args.pid, args.interface, args.endpoint, args.delay)

    print("attente de la ré-énumération…")
    found = wait_reenumeration(before, args.timeout)
    if not found:
        print(
            "aucun nouveau périphérique 2dc8:* détecté.\n"
            "Débranchez/rebranchez la manette pour revenir en mode Xbox.",
            file=sys.stderr,
        )
        return 1

    for dev in found:
        print(f"nouveau : {describe(dev)}")
        for cfg in dev:
            for intf in cfg:
                print(
                    f"  interface {intf.bInterfaceNumber} alt {intf.bAlternateSetting} "
                    f"class {intf.bInterfaceClass:02x}/{intf.bInterfaceSubClass:02x}/"
                    f"{intf.bInterfaceProtocol:02x} eps={intf.bNumEndpoints}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
