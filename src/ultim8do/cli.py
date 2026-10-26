"""CLI de configuration de la 8BitDo Ultimate 3-mode sous Linux (BLE).

    uv run ultim8do dump                          # lit et affiche le record courant
    uv run ultim8do set --slot 0 --name SALON
    uv run ultim8do set --slot 0 --stick-deadzone 12 --trigger-deadzone 8
    uv run ultim8do set --slot 0 --map a=b --map b=a
    uv run ultim8do profile 1                     # active le profil 1

`set` écrit, commite et relit pour vérifier.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import struct
import sys
import time

from bleak import BleakClient

from . import ble
from .record import (
    BASE,
    BUTTON_ORDER,
    FLAG_ENABLED,
    KEY_CODES,
    OFF_CUR_SLOT,
    OFF_MAPPING,
    OFF_NAMES,
    OFF_SLOT_FLAGS,
    OFF_STICKS,
    OFF_TRIGGERS,
    Record,
    finalise,
)


async def wait_for_device(timeout: float):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        found = await ble.scan(5.0)
        if found:
            return found[0]
    return None


async def connected(timeout: float) -> BleakClient:
    device = await wait_for_device(timeout)
    if device is None:
        raise SystemExit("manette introuvable — appuyer sur le bouton Xbox pour la réveiller")
    return BleakClient(device)


def print_record(record: Record) -> None:
    print(f"record id {record.record_id} · mode {record.mode} · profil actif {record.cur_slot}")
    print(
        f"CRC en-tête 0x{record.header_crc:04x} (recalculé 0x{record.stored_crc:04x}"
        f"{' — cohérent' if record.crc_ok else " — recalculé par la manette"})"
    )
    for slot in record.slots:
        state = "actif" if slot.enabled else f"inactif (0x{slot.flag:08x})"
        print(f"\n-- profil {slot.index} : {state}")
        if not slot.enabled:
            continue
        print(f"   nom       : {slot.name!r}")
        print(f"   deadzone  : {record.describe_sticks(slot.index)}")
        print(f"   triggers  : {record.describe_triggers(slot.index)}")
        special = record.describe_special(slot.index)
        print(f"   options   : {', '.join(special) if special else '—'}")
        mapping = record.describe_mapping(slot.index)
        print(f"   remaps    : {', '.join(mapping) if mapping else '—'}")


async def cmd_dump(args) -> int:
    client = await connected(args.wait)
    async with client:
        raw = await ble.read_record(client)
        record = Record.parse(raw)
        if args.json:
            print(
                json.dumps(
                    {
                        "record_id": record.record_id,
                        "mode": record.mode,
                        "cur_slot": record.cur_slot,
                        "crc_ok": record.crc_ok,
                        "slots": [
                            {
                                "index": s.index,
                                "flag": f"0x{s.flag:08x}",
                                "name": s.name,
                                "sticks": s.sticks,
                                "triggers": s.triggers,
                                "special": s.special,
                                "mapping": s.mapping,
                            }
                            for s in record.slots
                        ],
                    },
                    indent=2,
                )
            )
        else:
            print_record(record)
        if args.save:
            with open(args.save, "wb") as fh:
                fh.write(raw)
            print(f"\nenregistré : {args.save}")
    return 0


def apply_edits(raw: bytes, args) -> bytes:
    record = bytearray(raw)
    slot = args.slot
    flags_off = BASE + OFF_SLOT_FLAGS + 4 * slot
    (flag,) = struct.unpack_from("<I", record, flags_off)
    if flag != FLAG_ENABLED:
        struct.pack_into("<I", record, flags_off, FLAG_ENABLED)

    if args.name is not None:
        name = args.name.encode("utf-16-le")[:32].ljust(32, b"\x00")
        start = BASE + OFF_NAMES + 32 * slot
        record[start : start + 32] = name

    if args.stick_deadzone is not None:
        dz = max(0, min(128, args.stick_deadzone))
        struct.pack_into("<IBBBB", record, BASE + OFF_STICKS + 8 * slot, FLAG_ENABLED, 0, dz, 0, dz)

    if args.trigger_deadzone is not None:
        dz = max(0, min(255, args.trigger_deadzone))
        struct.pack_into(
            "<IBBBB", record, BASE + OFF_TRIGGERS + 8 * slot, FLAG_ENABLED, 0, dz, 0, dz
        )

    if args.map:
        base_map = BASE + OFF_MAPPING + 92 * slot
        for spec in args.map:
            button, _, target = spec.partition("=")
            if button not in BUTTON_ORDER:
                raise SystemExit(f"bouton inconnu : {button} (valeurs : {', '.join(BUTTON_ORDER)})")
            if target not in KEY_CODES:
                raise SystemExit(
                    f"fonction inconnue : {target} (valeurs : {', '.join(sorted(KEY_CODES))})"
                )
            struct.pack_into("<I", record, base_map + 4 + 4 * BUTTON_ORDER.index(button), KEY_CODES[target])
        struct.pack_into("<I", record, base_map, FLAG_ENABLED)

    if args.cur_slot is not None:
        struct.pack_into("<H", record, BASE + OFF_CUR_SLOT, args.cur_slot)

    return finalise(record)


async def cmd_set(args) -> int:
    client = await connected(args.wait)
    async with client:
        raw = await ble.read_record(client)
        updated = apply_edits(raw, args)
        await ble.write_record(client, updated)
        await ble.commit(client)
        print("écrit + commité — relecture de contrôle :\n")
        raw_after = await ble.read_record(client)
        after = Record.parse(raw_after)
        print_record(after)
        if args.save:
            with open(args.save, "wb") as fh:
                fh.write(raw_after)
            print(f"enregistré : {args.save}")
    return 0


async def cmd_profile(args) -> int:
    client = await connected(args.wait)
    async with client:
        raw = await ble.read_record(client)
        record = bytearray(raw)
        struct.pack_into("<H", record, BASE + OFF_CUR_SLOT, args.index)
        await ble.write_record(client, finalise(record))
        await ble.commit(client)
        print(f"profil actif réglé sur {args.index}")
        print_record(Record.parse(await ble.read_record(client)))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ultim8do", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    dump = sub.add_parser("dump", help="lit et affiche le record")
    dump.add_argument("--wait", type=float, default=120.0)
    dump.add_argument("--json", action="store_true")
    dump.add_argument("--save")
    dump.set_defaults(func=cmd_dump)

    sett = sub.add_parser("set", help="modifie un profil puis commit")
    sett.add_argument("--wait", type=float, default=120.0)
    sett.add_argument("--slot", type=int, default=0, choices=range(3))
    sett.add_argument("--name")
    sett.add_argument("--stick-deadzone", type=int)
    sett.add_argument("--trigger-deadzone", type=int)
    sett.add_argument("--map", action="append", help="ex. a=b")
    sett.add_argument("--cur-slot", type=int, choices=range(3))
    sett.add_argument("--save")
    sett.set_defaults(func=cmd_set)

    prof = sub.add_parser("profile", help="active un profil")
    prof.add_argument("index", type=int, choices=range(3))
    prof.add_argument("--wait", type=float, default=120.0)
    prof.set_defaults(func=cmd_profile)

    args = parser.parse_args(argv)
    return asyncio.run(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
