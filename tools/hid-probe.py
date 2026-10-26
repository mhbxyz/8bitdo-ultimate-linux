#!/usr/bin/env python3
"""Probe the HID configuration channel of an 8BitDo pad.

Run it once the pad is in configuration mode (after `tools/mode-switch.py`, the
pad exposes a /dev/hidrawN node under VID 2dc8).

    uv run tools/hid-probe.py                 # detect the 2dc8 hidraw by itself
    uv run tools/hid-probe.py /dev/hidraw3

Kept for reference: on the Ultimate 3-mode no hidraw node ever shows up.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

from ultim8do.config import REPORT_OUT, FrameFormat, HidConfig, parse_version

# fixed short queries, valid across the Ultimate family
SHORT_QUERIES: list[tuple[str, bytes]] = [
    ("version+edition", bytes([0x81, 0x05, 0x00, 0x21, 0x01])),
    ("infos (getRR)", bytes([0x81, 0x04, 0x00, 0x01, 0x00])),
    ("infos (21 01 00 00 06)", bytes([0x81, 0x04, 0x21, 0x01, 0x00, 0x00, 0x06])),
    ("pid", bytes([0x81, 0x05, 0xC1, 0x00])),
    ("mode", bytes([0x81, 0x04, 0x05, 0x01, 0x00])),
    ("mode 2", bytes([0x81, 0x05, 0x08, 0x00])),
    ("init reports", bytes([0x81, 0x11, 0x04, 0x07, 0x00])),
]

CANDIDATE_SIZES = [1652, 1592]


def hidraw_candidates(vid: str = "2dc8") -> list[str]:
    out: list[str] = []
    for node in sorted(pathlib.Path("/sys/class/hidraw").glob("hidraw*")):
        try:
            uevent = (node / "device" / "uevent").read_text()
        except OSError:
            continue
        if f"v0000{vid.upper()}" in uevent.upper():
            out.append(f"/dev/{node.name}")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("hidraw", nargs="?")
    parser.add_argument("--timeout", type=float, default=1.0)
    args = parser.parse_args()

    if args.hidraw:
        candidates = [args.hidraw]
    else:
        candidates = hidraw_candidates()
    if not candidates:
        print("no 2dc8 /dev/hidraw found, the pad is not in configuration mode")
        return 1

    for path in candidates:
        print(f"=== {path} ===")
        with HidConfig(path, timeout=args.timeout) as dev:
            for name, frame in SHORT_QUERIES:
                raw = dev.request_raw(frame)
                shown = raw[:24].hex(" ") if raw else "no reply"
                print(f"  {name:24s} {frame.hex(' '):20s} -> {shown}")
                if raw and name.startswith("version"):
                    print(f"      parsed: {parse_version(raw)}")

            print("  -- lecture du record (taille inconnue) --")
            for total in CANDIDATE_SIZES:
                for fmt in (FrameFormat.ULTIMATE2, FrameFormat.LENGTH):
                    raw = dev.read_block(0, 20, total, fmt=fmt)
                    if raw is None:
                        print(f"    total={total} fmt={fmt.value:10s} -> no reply")
                        continue
                    print(f"    total={total} fmt={fmt.value:10s} -> {raw[:24].hex(' ')}")
                    print(f"      cur_slot={int.from_bytes(raw[2:4], 'little')} "
                          f"flags={raw[:4].hex(' ')}")
                    break
            # XInput reports: restart them after the experiment
            dev.request_raw(bytes([0x81, 0x11, 0x04, 0x07, 0x00]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
