#!/usr/bin/env python3
"""GIP test bench for the 8BitDo Ultimate 3-mode.

The pad exposes the XGIP interface (ff/47/d0) and only speaks GIP: the "Xbox 360"
packets are ignored, and it emits nothing until it has received a GIP_CMD_POWER
(0x05) with mode ON (0x00).

    uv run tools/gip-probe.py listen            # handshake + dump frames for 3 s
    uv run tools/gip-probe.py send 0b 81 05 00 21 01
    uv run tools/gip-probe.py ack-scan          # which commands get acknowledged
    uv run tools/gip-probe.py hid 81 05 00 21 01   # HID_REPORT + replies
"""

from __future__ import annotations

import argparse
import sys
import time

import usb.core
import usb.util

VID, PID = 0x2DC8, 0x2030
EP_IN, EP_OUT = 0x81, 0x01

CMD_NAMES = {
    0x01: "ACK",
    0x02: "ANNOUNCE",
    0x03: "STATUS",
    0x04: "IDENTIFY",
    0x05: "POWER",
    0x06: "AUTHENTICATE",
    0x07: "VIRTUAL_KEY",
    0x08: "AUDIO_CONTROL",
    0x09: "RUMBLE",
    0x0A: "LED",
    0x0B: "HID_REPORT",
    0x0C: "FIRMWARE",
    0x0D: "AUDIO_SAMPLES",
    0x0E: "AUDIO_DATA",
    0x1E: "SERIAL_NUMBER",
    0x20: "INPUT",
    0x60: "AUDIO_SAMPLES_60",
}


class Gip:
    def __init__(self, pid: int = PID) -> None:
        self.dev = usb.core.find(idVendor=VID, idProduct=pid)
        if self.dev is None:
            raise SystemExit(f"{VID:04x}:{pid:04x} absent")
        self.detached = False
        self.seq = 0

    def open(self) -> "Gip":
        if self.dev.is_kernel_driver_active(0):
            self.dev.detach_kernel_driver(0)
            self.detached = True
        usb.util.claim_interface(self.dev, 0)
        return self

    def close(self) -> None:
        try:
            usb.util.release_interface(self.dev, 0)
        except usb.core.USBError:
            pass
        if self.detached:
            try:
                usb.util.dispose_resources(self.dev)
                self.dev.attach_kernel_driver(0)
            except usb.core.USBError:
                pass

    def next_seq(self) -> int:
        self.seq = (self.seq + 1) & 0xFF or 1
        return self.seq

    def send(self, cmd: int, payload: bytes = b"", options: int = 0x20, seq: int | None = None) -> int:
        seq = self.next_seq() if seq is None else seq
        frame = bytes([cmd, options, seq, len(payload)]) + payload
        self.dev.write(EP_OUT, frame.ljust(64, b"\x00"), timeout=1000)
        return seq

    def power_on(self) -> None:
        self.send(0x05, b"\x00", options=0x20)
        time.sleep(0.25)

    def drain(self, duration: float = 0.6) -> list[bytes]:
        out: list[bytes] = []
        end = time.monotonic() + duration
        while time.monotonic() < end:
            try:
                out.append(bytes(self.dev.read(EP_IN, 64, timeout=150)))
            except usb.core.USBTimeoutError:
                continue
        return out

    @staticmethod
    def describe(raw: bytes) -> str:
        name = CMD_NAMES.get(raw[0], f"0x{raw[0]:02x}")
        return f"{name:13s} opt=0x{raw[1]:02x} seq={raw[2]:3d} len={raw[3]:3d} {raw[4:4 + raw[3]].hex(' ')}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["listen", "send", "ack-scan", "hid"])
    ap.add_argument("args", nargs="*", help="bytes in hexadecimal")
    ap.add_argument("--pid", type=lambda s: int(s, 0), default=PID)
    ap.add_argument("--duration", type=float, default=2.0)
    a = ap.parse_args()

    gip = Gip(a.pid).open()
    try:
        print("handshake (GIP power-on)…")
        gip.power_on()
        for raw in gip.drain(0.4):
            print("  <-", Gip.describe(raw))

        if a.action == "listen":
            print(f"listening for {a.duration}s:")
            for raw in gip.drain(a.duration):
                print("  <-", Gip.describe(raw))

        elif a.action == "send":
            if not a.args:
                return 1
            cmd = int(a.args[0], 16)
            payload = bytes(int(x, 16) for x in a.args[1:])
            seq = gip.send(cmd, payload, options=0x00)
            print(f"-> {CMD_NAMES.get(cmd, hex(cmd))} seq={seq} payload={payload.hex(' ')}")
            for raw in gip.drain(a.duration):
                print("  <-", Gip.describe(raw))

        elif a.action == "hid":
            payload = bytes(int(x, 16) for x in a.args)
            seq = gip.send(0x0B, payload, options=0x00)
            print(f"-> HID_REPORT seq={seq} len={len(payload)} {payload.hex(' ')}")
            for raw in gip.drain(a.duration):
                print("  <-", Gip.describe(raw))

        elif a.action == "ack-scan":
            print("envoi de chaque commande avec le drapeau ACK (0x10) :")
            for cmd in sorted(CMD_NAMES):
                gip.send(cmd, b"", options=0x10)
                time.sleep(0.08)
            for raw in gip.drain(1.5):
                print("  <-", Gip.describe(raw))
    finally:
        gip.close()
        print("(xpad reattached)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
