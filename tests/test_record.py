import struct

import pytest

from ultim8do.record import (
    BASE,
    FLAG_ENABLED,
    OFF_MAPPING,
    OFF_NAMES,
    OFF_SLOT_FLAGS,
    OFF_STICKS,
    RECORD_SIZE,
    Record,
    blank_record,
    crc16_kermit,
    finalise,
)


def test_crc16_kermit_known_vector():
    # poly réfléchi 0x8408, init 0xFFFF, pas de xor final (variante 8BitDo de KERMIT)
    assert crc16_kermit(b"123456789") == 0x6F91


def test_crc_matches_hardware_value():
    # valeur réellement renvoyée par la manette pour un record vierge en mode D
    record = bytearray(b"\xff" * RECORD_SIZE)
    record[3] = 0x03
    assert crc16_kermit(bytes(record[2:])) == 0x41A3


def test_finalise_writes_crc_little_endian():
    record = blank_record(0x03)
    struct.pack_into("<I", record, BASE + OFF_SLOT_FLAGS, FLAG_ENABLED)
    out = finalise(record)
    assert struct.unpack_from("<H", out, 0)[0] == crc16_kermit(out[2:])


def test_blank_record_keeps_record_id():
    record = blank_record(0x02)
    assert record[3] == 0x02
    assert record[2] == 0xFF
    assert len(record) == RECORD_SIZE


def test_parse_roundtrip_profile_name():
    record = blank_record(0x03)
    struct.pack_into("<I", record, BASE + OFF_SLOT_FLAGS, FLAG_ENABLED)
    name = "SALON".encode("utf-16-le")
    record[BASE + OFF_NAMES : BASE + OFF_NAMES + len(name)] = name

    parsed = Record.parse(bytes(finalise(record)))
    assert parsed.slots[0].enabled
    assert parsed.slots[0].name == "SALON"
    assert parsed.crc_ok


def test_parse_deadzone():
    record = blank_record(0x03)
    struct.pack_into("<IBBBB", record, BASE + OFF_STICKS, FLAG_ENABLED, 0, 12, 4, 20)
    parsed = Record.parse(bytes(finalise(record)))
    assert parsed.slots[0].sticks == (FLAG_ENABLED, 0, 12, 4, 20)
    assert "LS 0→12" in parsed.describe_sticks(0)


def test_parse_mapping_remap():
    record = blank_record(0x03)
    struct.pack_into("<I", record, BASE + OFF_MAPPING, FLAG_ENABLED)
    struct.pack_into("<I", record, BASE + OFF_MAPPING + 4, 0x2000)  # A -> A
    struct.pack_into("<I", record, BASE + OFF_MAPPING + 8, 0x1000)  # B -> B
    parsed = Record.parse(bytes(finalise(record)))
    assert parsed.describe_mapping(0) == []


def test_trailing_area_preserved():
    record = blank_record(0x03)
    parsed = Record.parse(bytes(finalise(record)))
    assert parsed.trailing == b"\xff" * 28


def test_parse_rejects_short_buffer():
    with pytest.raises(ValueError):
        Record.parse(b"\x00" * 100)
