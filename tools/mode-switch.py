#!/usr/bin/env python3
"""Bascule la manette 8BitDo en mode configuration (équivalent du « knock » officiel).

En mode Xbox la manette n'expose aucun canal de configuration : le logiciel 8BitDo
la force à ré-énumérer en lui envoyant une init Xbox puis une rafale de rumble sur
l'endpoint interrupt OUT. Elle revient alors avec un autre PID et un canal HID
(report 0x81) sur lequel passent les trames de configuration.

    uv run tools/mode-switch.py                # 1 tentative
    uv run tools/mode-switch.py --repeat 3     # insiste, comme sur l'Ultimate 2.4G
    uv run tools/mode-switch.py --dry-run

Le pilote `xpad` est détaché le temps de la séquence puis remis en place si la
manette est toujours là (sinon il faut rebrancher le câble).
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


def devices() -> list[usb.core.Device]:
    return list(usb.core.find(find_all=True, idVendor=VID))


def snapshot() -> list[tuple[int, int, int]]:
    return [(d.idProduct, d.bus, d.address) for d in devices()]


def describe(dev: usb.core.Device) -> str:
    try:
        product = usb.util.get_string(dev, dev.iProduct) if dev.iProduct else ""
    except (usb.core.USBError, ValueError):
        product = "?"
    return f"{dev.idVendor:04x}:{dev.idProduct:04x} bus {dev.bus} addr {dev.address} « {product} »"


def send_knock(pid: int, interface: int, endpoint: int, delay: float, repeat: int) -> None:
    dev = usb.core.find(idVendor=VID, idProduct=pid)
    if dev is None:
        sys.exit(f"périphérique {VID:04x}:{pid:04x} introuvable")

    print(f"cible : {describe(dev)}")
    detached = False
    try:
        if dev.is_kernel_driver_active(interface):
            print(f"détachement de xpad (interface {interface})")
            dev.detach_kernel_driver(interface)
            detached = True
    except (NotImplementedError, usb.core.USBError) as exc:
        print(f"  (is_kernel_driver_active : {exc})")

    usb.util.claim_interface(dev, interface)
    gone = False
    try:
        for attempt in range(1, repeat + 1):
            if repeat > 1:
                print(f"-- tentative {attempt}/{repeat}")
            for i, packet in enumerate(INIT_SEQUENCE, 1):
                print(f"  [{i}/{len(INIT_SEQUENCE)}] {packet.hex(' ')}")
                try:
                    dev.write(endpoint, packet, timeout=1000)
                except usb.core.USBError as exc:
                    print(f"  transfert interrompu ({exc}) — la manette a probablement décroché")
                    gone = True
                    break
                time.sleep(delay)
            if gone:
                break
            time.sleep(0.4)
            if usb.core.find(idVendor=VID, idProduct=pid) is None:
                print("  la manette n'est plus sur le bus")
                gone = True
                break
    finally:
        if not gone:
            try:
                usb.util.release_interface(dev, interface)
            except usb.core.USBError:
                pass
            if detached:
                try:
                    usb.util.dispose_resources(dev)
                    dev.attach_kernel_driver(interface)
                    print("  xpad rattaché")
                except usb.core.USBError as exc:
                    print(f"  rattachement de xpad impossible ({exc}) — rebrancher le câble")


def wait_reenumeration(timeout: float) -> list[usb.core.Device]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = [d for d in devices() if (d.idProduct, d.bus, d.address) not in BEFORE]
        if current:
            return current
        time.sleep(0.2)
    return []


BEFORE: list[tuple[int, int, int]] = []


def main() -> int:
    global BEFORE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=lambda s: int(s, 0), default=PID_3MODE_XBOX)
    parser.add_argument("--interface", type=int, default=0)
    parser.add_argument("--endpoint", type=lambda s: int(s, 0), default=0x01)
    parser.add_argument("--delay", type=float, default=DELAY)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        print("séquence de bascule :")
        for packet in INIT_SEQUENCE:
            print(f"  {packet.hex(' ')}")
        return 0

    BEFORE = snapshot()
    print("périphériques 2dc8 avant :", BEFORE)
    send_knock(args.pid, args.interface, args.endpoint, args.delay, args.repeat)

    print("attente de la ré-énumération…")
    found = wait_reenumeration(args.timeout)
    if not found:
        print(
            "aucun nouveau périphérique 2dc8:* détecté.",
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
