#!/usr/bin/env python3
"""Sonde le canal de configuration BLE d'une manette 8BitDo (81HB-*).

    uv run tools/ble-probe.py scan            # liste les manettes visibles
    uv run tools/ble-probe.py version         # requêtes courtes, dump brut
    uv run tools/ble-probe.py read            # lit et analyse le record (1652 o)
    uv run tools/ble-probe.py read --size 1592

Le record est sauvegardé dans capture/record-ble.bin.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import struct
import sys

from bleak import BleakClient
from bleak.backends.device import BLEDevice

from ultim8do.ble import CHAR_UUID, RECORD_SIZE, scan

CHUNK = 45

VERSION_FRAMES: dict[str, bytes] = {
    "00 21 01": bytes.fromhex("00 21 01"),
    "04 05 00 21 01": bytes.fromhex("04 05 00 21 01"),
    "81 05 00 21 01": bytes.fromhex("81 05 00 21 01"),
}


def hexdump(data: bytes, width: int = 16) -> str:
    lines = []
    for off in range(0, len(data), width):
        chunk = data[off : off + width]
        text = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"  {off:04x}  {chunk.hex(' '):<{width * 3}}  {text}")
    return "\n".join(lines)


def build_read(offset: int, length: int, total: int) -> bytes:
    return (
        bytes([0x04])
        + struct.pack("<HHHHII", 0x0002, 0, length, 0, total, offset)
        + b"\x00" * length
    )


async def pick(address: str | None = None) -> BLEDevice | None:
    if address:
        return BLEDevice(address, address, None)
    print("scan BLE (8 s)…")
    devices = await scan(8.0)
    for d in devices:
        print(f"  {d.address}  « {d.name} »")
    return devices[0] if devices else None


async def read_record(client: BleakClient, total: int) -> bytes | None:
    queue: asyncio.Queue[bytes] = asyncio.Queue()
    await client.start_notify(CHAR_UUID, lambda _c, data: queue.put_nowait(bytes(data)))
    buf = bytearray()
    while len(buf) < total:
        offset = len(buf)
        try:
            await client.write_gatt_char(CHAR_UUID, build_read(offset, CHUNK, total), response=True)
        except Exception as exc:  # noqa: BLE001
            print(f"  écriture impossible à l'offset {offset} : {exc}", file=sys.stderr)
            break
        try:
            raw = await asyncio.wait_for(queue.get(), 1.5)
        except asyncio.TimeoutError:
            print(f"  pas de réponse à l'offset {offset}", file=sys.stderr)
            break
        length = struct.unpack_from("<H", raw, 4)[0]
        echoed_offset = struct.unpack_from("<I", raw, 12)[0]
        if echoed_offset != offset:
            print(f"  offset inattendu {echoed_offset} (attendu {offset})", file=sys.stderr)
        buf += raw[16 : 16 + length]
        if len(buf) % (CHUNK * 6) == 0 or len(buf) >= total:
            print(f"  {len(buf):4d}/{total}", flush=True)
    return bytes(buf[:total]) if len(buf) >= total else None


def analyse(record: bytes) -> None:
    flags = [struct.unpack_from("<I", record, 4 * i)[0] for i in range(4)]
    print("flags    :", " ".join(f"0x{f:08x}" for f in flags))
    print("mode     :", struct.unpack_from("<H", record, 0x10)[0])
    print("cur_slot :", struct.unpack_from("<H", record, 0x12)[0])
    for slot in range(3):
        raw = record[0x14 + 32 * slot : 0x14 + 32 * (slot + 1)]
        le = raw.decode("utf-16-le", "replace").split("\x00")[0]
        be = raw.decode("utf-16-be", "replace").split("\x00")[0]
        print(f"  slot{slot} : le={le!r} be={be!r}")
    print("\npremiers 96 octets :")
    print(hexdump(record[:96]))


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["scan", "version", "read"])
    ap.add_argument("--address")
    ap.add_argument("--size", type=int, default=RECORD_SIZE)
    args = ap.parse_args()

    if args.action == "scan":
        for d in await scan(10.0):
            print(f"{d.address}  « {d.name} »")
        return 0

    device = await pick(args.address)
    if device is None:
        print("manette introuvable — appuyer sur le bouton Xbox pour la réveiller", file=sys.stderr)
        return 1

    async with BleakClient(device) as client:
        print(f"connecté à « {getattr(device, 'name', '?')} »")
        if args.action == "version":
            for label, frame in VERSION_FRAMES.items():
                queue: asyncio.Queue[bytes] = asyncio.Queue()
                await client.start_notify(CHAR_UUID, lambda _c, d: queue.put_nowait(bytes(d)))
                await client.write_gatt_char(CHAR_UUID, frame, response=True)
                try:
                    raw = await asyncio.wait_for(queue.get(), 1.0)
                    print(f"  {label:18s} → {raw.hex(' ')}")
                except asyncio.TimeoutError:
                    print(f"  {label:18s} → pas de réponse")
                await client.stop_notify(CHAR_UUID)
            return 0

        print(f"lecture du record ({args.size} o)…")
        record = await read_record(client, args.size)
        if record is None:
            return 1
        with open("capture/record-ble.bin", "wb") as fh:
            fh.write(record)
        print(f"enregistré : capture/record-ble.bin ({len(record)} o, md5 {hashlib.md5(record).hexdigest()})")
        analyse(record)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
