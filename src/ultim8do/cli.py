"""Configuration CLI for the 8BitDo Ultimate 3-mode under Linux (BLE).

    uv run ultim8do dump                          # read and print the record
    uv run ultim8do set --slot 0 --stick-deadzone 12
    uv run ultim8do set --slot 0 --trigger-deadzone 8
    uv run ultim8do set --slot 0 --map a=b --map b=a
    uv run ultim8do set --slot 0 --option swap-sticks
    uv run ultim8do set --slot 1 --enable         # enable profile 1

`set` writes, applies, commits and reads back to verify.
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
    BUTTON_ORDER,
    FLAG_ENABLED,
    FLAG_ERASED,
    KEY_CODES,
    OFF_MAP,
    OFF_MAP_FLAG,
    OFF_OPTIONS,
    OFF_OPTIONS_FLAG,
    OFF_STICKS,
    OFF_STICKS_FLAG,
    OFF_TRIGGERS,
    OFF_TRIGGERS_FLAG,
    OPTION_BITS,
    Record,
    block_offset,
    finalise,
)

OPTION_NAMES = {name.replace(" ", "-"): bit for bit, name in OPTION_BITS.items()}


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
        raise SystemExit("controller not found, press the Xbox button to wake it up")
    return BleakClient(device)


def print_record(record: Record) -> None:
    print(f"record id {record.record_id}")
    print(
        f"header CRC 0x{record.header_crc:04x} (recomputed 0x{record.stored_crc:04x}"
        f"{' - matches' if record.crc_ok else ' - differs'})"
    )
    for profile in record.profiles:
        state = "actif" if profile.enabled else f"inactif (0x{profile.flag:08x})"
        print(f"\n-- profil {profile.index} : {state}")
        if not profile.enabled:
            continue
        cal = ", ".join(f"{value:.0f}" for value in profile.calibration)
        print(f"   calibration : {cal}")
        print(f"   deadzone    : {record.describe_sticks(profile.index)}")
        print(f"   triggers    : {record.describe_triggers(profile.index)}")
        options = record.describe_options(profile.index)
        print(f"   options     : {', '.join(options) if options else '-'}")
        print(f"   remaps      : {', '.join(record.describe_mapping(profile.index))}")


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
                        "crc_ok": record.crc_ok,
                        "profiles": [
                            {
                                "index": p.index,
                                "flag": f"0x{p.flag:08x}",
                                "mapping": p.mapping,
                                "calibration": p.calibration,
                                "sticks": p.sticks,
                                "triggers": p.triggers,
                                "options": p.options,
                            }
                            for p in record.profiles
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
            print(f"\nsaved: {args.save}")
    return 0


def apply_edits(raw: bytes, args) -> bytes:
    record = bytearray(raw)
    base = block_offset(args.slot)
    struct.pack_into("<I", record, base, FLAG_ENABLED)

    if args.disable:
        struct.pack_into("<I", record, base, FLAG_ERASED)
        return finalise(record)

    if args.stick_deadzone is not None:
        value = max(0, min(128, args.stick_deadzone))
        struct.pack_into("<I", record, base + OFF_STICKS_FLAG, FLAG_ENABLED)
        struct.pack_into("<BBBB", record, base + OFF_STICKS, 0, value, 0, value)

    if args.trigger_deadzone is not None:
        value = max(0, min(255, args.trigger_deadzone))
        struct.pack_into("<I", record, base + OFF_TRIGGERS_FLAG, FLAG_ENABLED)
        struct.pack_into("<BBBB", record, base + OFF_TRIGGERS, 0, value, 0, value)

    if args.map:
        struct.pack_into("<I", record, base + OFF_MAP_FLAG, FLAG_ENABLED)
        for spec in args.map:
            button, _, target = spec.partition("=")
            if button not in BUTTON_ORDER:
                raise SystemExit(
                    f"bouton inconnu : {button} (valeurs : {', '.join(BUTTON_ORDER)})"
                )
            if target not in KEY_CODES:
                raise SystemExit(
                    f"fonction inconnue : {target} (valeurs : {', '.join(sorted(KEY_CODES))})"
                )
            offset = base + OFF_MAP + 4 * BUTTON_ORDER.index(button)
            struct.pack_into("<I", record, offset, KEY_CODES[target])

    if args.option:
        struct.pack_into("<I", record, base + OFF_OPTIONS_FLAG, FLAG_ENABLED)
        (current,) = struct.unpack_from("<I", record, base + OFF_OPTIONS)
        for name in args.option:
            if name not in OPTION_NAMES:
                raise SystemExit(
                    f"option inconnue : {name} (valeurs : {', '.join(OPTION_NAMES)})"
                )
            current |= OPTION_NAMES[name]
        struct.pack_into("<I", record, base + OFF_OPTIONS, current)

    return finalise(record)


async def cmd_set(args) -> int:
    device = await wait_for_device(args.wait)
    if device is None:
        raise SystemExit("manette introuvable")
    async with BleakClient(device) as client:
        raw = await ble.read_record(client)
        updated = apply_edits(raw, args)
        await ble.report_state(client, False)
        await ble.write_record(client, updated)
        subs = await ble.commit(client)
        # the pad writes flash after acknowledging, give it some time
        await asyncio.sleep(3.0)
        await ble.report_state(client, True)
        print(f"commits sent: {[hex(s) for s in subs]}")
        print("immediate read back:")
        print_record(Record.parse(await ble.read_record(client)))

    # A reconnect reads what is really stored, not the session cache.
    await asyncio.sleep(2.0)
    async with BleakClient(device) as client:
        stored = Record.parse(await ble.read_record(client))
        print("\nread back after reconnect (flash state):")
        print_record(stored)
        if args.save:
            with open(args.save, "wb") as fh:
                fh.write(await ble.read_record(client))
            print(f"saved: {args.save}")
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
    sett.add_argument("--stick-deadzone", type=int, help="0..128")
    sett.add_argument("--trigger-deadzone", type=int, help="0..255")
    sett.add_argument("--map", action="append", help="e.g. a=b")
    sett.add_argument(
        "--option",
        action="append",
        help=",".join(OPTION_NAMES),
    )
    sett.add_argument("--disable", action="store_true", help="disable the profile")
    sett.add_argument("--save")
    sett.set_defaults(func=cmd_set)

    args = parser.parse_args(argv)
    return asyncio.run(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
