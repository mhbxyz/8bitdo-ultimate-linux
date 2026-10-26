import struct

import pytest

from ultim8do.record import (
    BLOCK_SIZE,
    FLAG_ENABLED,
    FLAG_ERASED,
    OFF_MAP,
    OFF_MAP_FLAG,
    OFF_STICKS,
    OFF_STICKS_FLAG,
    OFF_TRIGGERS,
    OFF_TRIGGERS_FLAG,
    RECORD_SIZE,
    Record,
    blank_record,
    block_offset,
    crc16_kermit,
    finalise,
)


def test_crc16_kermit_known_vector():
    # poly réfléchi 0x8408, init 0xFFFF, pas de xor final (variante 8BitDo)
    assert crc16_kermit(b"123456789") == 0x6F91


def test_crc_matches_hardware_value():
    # valeur réellement renvoyée par la manette pour un record vierge en mode D
    record = bytearray(b"\xff" * RECORD_SIZE)
    record[3] = 0x03
    assert crc16_kermit(bytes(record[2:])) == 0x41A3


def test_record_is_header_plus_three_blocks():
    assert RECORD_SIZE == 4 + 3 * BLOCK_SIZE


def test_finalise_writes_crc_little_endian():
    record = blank_record(0x01)
    struct.pack_into("<I", record, block_offset(0), FLAG_ENABLED)
    out = finalise(record)
    assert struct.unpack_from("<H", out, 0)[0] == crc16_kermit(out[2:])


def test_blank_record_keeps_record_id_and_markers():
    record = blank_record(0x02)
    assert record[2] == 0xFF
    assert record[3] == 0x02
    for slot in range(3):
        start = block_offset(slot) + 0xAE
        assert bytes(record[start : start + 2]) == b"\x55\xaa"


def test_parse_default_profile():
    record = blank_record(0x01)
    base = block_offset(0)
    struct.pack_into("<I", record, base, FLAG_ENABLED)
    struct.pack_into("<I", record, base + OFF_MAP_FLAG, FLAG_ENABLED)
    struct.pack_into("<I", record, base + OFF_STICKS_FLAG, FLAG_ENABLED)
    struct.pack_into("<BBBB", record, base + OFF_STICKS, 0, 128, 0, 128)
    struct.pack_into("<I", record, base + OFF_TRIGGERS_FLAG, FLAG_ENABLED)
    struct.pack_into("<BBBB", record, base + OFF_TRIGGERS, 0, 255, 0, 255)

    parsed = Record.parse(bytes(finalise(record)))
    assert parsed.crc_ok
    assert parsed.profiles[0].enabled
    assert parsed.describe_sticks(0) == "LS 0→128  RS 0→128"
    assert parsed.describe_triggers(0) == "LT 0→255  RT 0→255"
    assert parsed.profiles[1].flag == FLAG_ERASED


def test_mapping_default_has_no_remap():
    record = blank_record(0x01)
    base = block_offset(0)
    struct.pack_into("<I", record, base, FLAG_ENABLED)
    struct.pack_into("<I", record, base + OFF_MAP_FLAG, FLAG_ENABLED)
    mapping = [0x2000, 0x1000, 0x10, 0x20, 0x400, 0x800, 0x4000, 0x8000,
               0x2, 0x4, 0x8, 0x1, 0x8000000, 0x20000, 0x200, 0x100,
               0x80, 0x40, 0x2000000, 0x4000000]
    for i, code in enumerate(mapping):
        struct.pack_into("<I", record, base + OFF_MAP + 4 * i, code)
    parsed = Record.parse(bytes(finalise(record)))
    assert parsed.describe_mapping(0) == []


def test_mapping_remap_detected():
    record = blank_record(0x01)
    base = block_offset(0)
    struct.pack_into("<I", record, base, FLAG_ENABLED)
    struct.pack_into("<I", record, base + OFF_MAP_FLAG, FLAG_ENABLED)
    struct.pack_into("<I", record, base + OFF_MAP, 0x1000)  # A -> B
    parsed = Record.parse(bytes(finalise(record)))
    assert parsed.describe_mapping(0) == ["a→b"]


def test_parse_rejects_short_buffer():
    with pytest.raises(ValueError):
        Record.parse(b"\x00" * 100)
