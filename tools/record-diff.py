#!/usr/bin/env python3
"""Compare two 8BitDo record dumps and show the bytes that changed.

    uv run tools/record-diff.py capture/before.bin capture/after.bin

Acts as an oracle: dump the record, change ONE setting with the official
software, dump again, and the modified bytes give the offset and the encoding of
that field.
"""

from __future__ import annotations

import argparse
import struct
import sys

from ultim8do.record import BLOCK_SIZE, HEADER_SIZE, SLOTS, block_offset


def offset_label(index: int) -> str:
    """Traduit un offset brut en position lisible dans la structure connue."""
    if index < HEADER_SIZE:
        return f"header (+0x{index:02x})"
    for slot in range(SLOTS):
        base = block_offset(slot)
        if base <= index < base + BLOCK_SIZE:
            return f"bloc {slot} +0x{index - base:02x}"
    return f"hors blocs (+0x{index:03x})"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                    formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("before")
    parser.add_argument("after")
    args = parser.parse_args()

    try:
        before = open(args.before, "rb").read()
        after = open(args.after, "rb").read()
    except OSError as exc:
        print(exc, file=sys.stderr)
        return 1

    if len(before) != len(after):
        print(f"different sizes: {len(before)} vs {len(after)}", file=sys.stderr)

    changed = [
        (i, b, a)
        for i, (b, a) in enumerate(zip(before, after))
        if b != a
    ]
    if not changed:
        print("no difference")
        return 0

    print(f"{len(changed)} byte(s) changed\n")
    # regrouper les octets contigus
    runs: list[list[tuple[int, int, int]]] = []
    for item in changed:
        if runs and item[0] == runs[-1][-1][0] + 1:
            runs[-1].append(item)
        else:
            runs.append([item])

    for run in runs:
        start, end = run[0][0], run[-1][0]
        old = bytes(b for _, b, _ in run)
        new = bytes(a for _, _, a in run)
        label = offset_label(start)
        extra = ""
        if len(run) in (2, 4, 8):
            fmt = {2: "<H", 4: "<I", 8: "<Q"}[len(run)]
            extra = (
                f"  u{len(run) * 8}: 0x{struct.unpack(fmt, old)[0]:x}"
                f" -> 0x{struct.unpack(fmt, new)[0]:x}"
            )
        print(f"  0x{start:03x}..0x{end:03x} ({len(run):2d} o) {label}")
        print(f"      before: {old.hex(' ')}")
        print(f"      after : {new.hex(' ')}{extra}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
