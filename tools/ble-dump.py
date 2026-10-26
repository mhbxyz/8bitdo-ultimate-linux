#!/usr/bin/env python3
"""Lit le record de configuration 8BitDo en BLE, en une seule session.

La manette n'annonce que quelques secondes après réveil et se rendort dès que la
liaison tombe : ce script attend son annonce (scan en boucle), se connecte, lit
les 1652 octets, analyse et sauvegarde — sans jamais relâcher la connexion entre
deux trames.

    uv run tools/ble-dump.py                 # attend jusqu'à 180 s
    uv run tools/ble-dump.py --wait 300
    uv run tools/ble-dump.py --address E4:17:D8:18:09:23
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import struct
import sys
import time

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

from ultim8do.ble import CHAR_UUID, RECORD_SIZE, FrameReader, scan

CHUNK = 45


def build_read(offset: int, length: int, total: int) -> bytes:
    return (
        bytes([0x04])
        + struct.pack("<HHHHII", 0x0002, 0, length, 0, total, offset)
        + b"\x00" * length
    )


def build_commit(sub: int = 0x0015, total: int = RECORD_SIZE) -> bytes:
    return bytes([0x04]) + struct.pack("<HHHHII", 0x0006, sub, 0, 0, total, 0)


async def wait_for_pad(wait: float, address: str | None) -> BLEDevice | None:
    end = time.monotonic() + wait
    while time.monotonic() < end:
        if address:
            dev = await BleakScanner.find_device_by_address(address, timeout=5.0)
            if dev is not None:
                return dev
        else:
            found = await scan(5.0)
            if found:
                return found[0]
            if any(True for _ in ()):  # pragma: no cover
                pass
        print("  …toujours rien, nouvelle passe de scan", flush=True)
    return None


async def read_record(client: BleakClient, total: int, attempts: int = 4) -> bytes | None:
    """Lit le record complet.

    Le pad renvoie en général 45 octets par trame, mais parfois moins (frontière de
    chunk interne). On avance donc au premier octet non lu ; si la réponse est vide
    on retombe sur le multiple de 45 suivant.
    """
    queue: asyncio.Queue[bytes] = asyncio.Queue()
    await client.start_notify(CHAR_UUID, lambda _c, data: queue.put_nowait(bytes(data)))
    reader = FrameReader(queue)
    record = bytearray(total)
    written = bytearray(total)  # 1 = octet effectivement reçu
    cursor = 0
    stalls = 0
    while cursor < total and stalls < attempts:
        try:
            await client.write_gatt_char(CHAR_UUID, build_read(cursor, CHUNK, total), response=True)
        except Exception as exc:  # noqa: BLE001
            print(f"  écriture impossible à {cursor} : {exc}", file=sys.stderr)
            return None
        frame = await reader.next_frame(1.5)
        if frame is None or frame.offset != cursor:
            stalls += 1
            reader.reset()
            print(
                f"  trame inattendue à {cursor} "
                f"(offset={getattr(frame, 'offset', None)}, len={getattr(frame, 'length', None)})",
                flush=True,
            )
            await asyncio.sleep(0.2)
            continue
        data = frame.data
        if data:
            record[cursor : cursor + len(data)] = data
            written[cursor : cursor + len(data)] = b"\x01" * len(data)
            cursor += len(data)
            stalls = 0
            if cursor % (CHUNK * 12) < CHUNK:
                print(f"  {cursor:4d}/{total}", flush=True)
        else:
            # réponse vide : on tente le prochain multiple de 45
            stalls += 1
            cursor = ((cursor // CHUNK) + 1) * CHUNK
            await asyncio.sleep(0.1)
    got = sum(written)
    print(f"  {got} octets reçus sur {total}", flush=True)
    if got < total * 0.95:
        print("  lecture incomplète", file=sys.stderr)
    return bytes(record)


def analyse(record: bytes) -> dict:
    out: dict = {
        "size": len(record),
        "md5": hashlib.md5(record).hexdigest(),
        "slot_flags": [f"0x{struct.unpack_from('<I', record, 4 * i)[0]:08x}" for i in range(4)],
        "gamepad_mode": struct.unpack_from("<H", record, 0x10)[0],
        "cur_slot": struct.unpack_from("<H", record, 0x12)[0],
    }
    names = {}
    for slot in range(3):
        raw = record[0x14 + 32 * slot : 0x14 + 32 * (slot + 1)]
        names[f"slot{slot}"] = {
            "utf16-le": raw.decode("utf-16-le", "replace").split("\x00")[0],
            "utf16-be": raw.decode("utf-16-be", "replace").split("\x00")[0],
        }
    out["profile_names"] = names
    return out


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--address")
    ap.add_argument("--size", type=int, default=RECORD_SIZE)
    ap.add_argument("--wait", type=float, default=180.0)
    ap.add_argument("--commit", action="store_true", help="envoie aussi la commande de sauvegarde")
    args = ap.parse_args()

    print(f"attente de la manette (max {args.wait:.0f}s)…", flush=True)
    device = await wait_for_pad(args.wait, args.address)
    if device is None:
        print("manette jamais annoncée", file=sys.stderr)
        return 1
    print(f"trouvée : « {device.name} » {device.address}", flush=True)

    async with BleakClient(device) as client:
        print("connecté", flush=True)
        record = await read_record(client, args.size)
        if record is None:
            return 1
        meta = analyse(record)
        with open("capture/record-ble.bin", "wb") as fh:
            fh.write(record)
        with open("capture/record-ble.json", "w") as fh:
            json.dump(meta, fh, indent=2)
        print(json.dumps(meta, indent=2))
        if args.commit:
            await client.write_gatt_char(CHAR_UUID, build_commit(), response=True)
            print("commit envoyé")
        await asyncio.sleep(0.5)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
