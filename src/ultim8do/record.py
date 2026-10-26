"""Record de configuration 8BitDo Ultimate 3-mode (BLE, 532 octets).

Disposition, établie sur matériel (firmware 2.00) :

    0x000   2       CRC-16/KERMIT de record[2:532], little-endian
                    -> recalculé par la manette à chaque commit
    0x002   1       réservé (0xFF)
    0x003   1       identifiant du record : 0x01 en mode PC/W,
                    0x03 en mode D (Bluetooth), 0x02 en mode Xbox
    0x004   176     bloc du profil 0
    0x0B4   176     bloc du profil 1
    0x164   176     bloc du profil 2

    4 + 3 × 176 = 532

Chaque bloc porte **un seul profil** : les sections y sont séquentielles (pas de
tableau indexé par slot comme sur l'Ultimate 2) et le bloc se termine par le
marqueur `55 AA`.

Disposition d'un bloc (offsets relatifs au début du bloc) :

    0x00  4   flag du profil : 0x20200911 actif, 0xFFFFFFFF effacé
    0x04  4   inconnu (0xFFFFFFFF sur un profil par défaut)
    0x08  4   inconnu
    0x0C 28   inconnu (nom / mode / crc_value ?)
    0x28  4   flag de la section mapping
    0x2C 80   20 × u32 codes de fonction
    0x7C  4   flag de la section calibration
    0x80 16   4 flottants (~25600 : butées/centres de sticks)
    0x90  4   flag de la section deadzone sticks
    0x94  4   LS début, LS fin, RS début, RS fin (0..128)
    0x98  4   flag de la section deadzone triggers
    0x9C  4   LT début, LT fin, RT début, RT fin (0..255)
    0xA0  4   flag de la section options
    0xA4  4   bits d'options
    0xA8  6   remplissage (0xFF)
    0xAE  2   marqueur 55 AA
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

RECORD_SIZE = 532
HEADER_SIZE = 4
BLOCK_SIZE = 176
SLOTS = 3

FLAG_ENABLED = 0x20200911
FLAG_DISABLED = 0x20190000
FLAG_ERASED = 0xFFFFFFFF
BLOCK_MARKER = b"\x55\xaa"

# -- offsets dans un bloc ---------------------------------------------------
OFF_FLAG = 0x00
OFF_UNKNOWN_A = 0x04
OFF_UNKNOWN_B = 0x08
OFF_BODY = 0x0C  # 28 octets, contenu non identifié
OFF_MAP_FLAG = 0x28
OFF_MAP = 0x2C
MAP_COUNT = 20
OFF_CAL_FLAG = 0x7C
OFF_CAL = 0x80
CAL_COUNT = 4
OFF_STICKS_FLAG = 0x90
OFF_STICKS = 0x94
OFF_TRIGGERS_FLAG = 0x98
OFF_TRIGGERS = 0x9C
OFF_OPTIONS_FLAG = 0xA0
OFF_OPTIONS = 0xA4
OFF_MARKER = 0xAE

# -- codes de fonction du mapping -------------------------------------------
KEY_CODES: dict[str, int] = {
    "none": 0x0,
    "start": 0x1,
    "l3": 0x2,
    "r3": 0x4,
    "select": 0x8,
    "x": 0x10,
    "y": 0x20,
    "right": 0x40,
    "left": 0x80,
    "down": 0x100,
    "up": 0x200,
    "lb": 0x400,
    "rb": 0x800,
    "b": 0x1000,
    "a": 0x2000,
    "lt": 0x4000,
    "rt": 0x8000,
    "menu": 0x10000,
    "home": 0x20000,
    "p5": 0x100000,
    "p3": 0x200000,
    "screenshot": 0x400000,
    "turbo_single": 0x800000,
    "turbo_auto": 0x1000000,
    "p1": 0x2000000,
    "p2": 0x4000000,
    "star": 0x8000000,
    "p4": 0x40000000,
}
CODE_NAMES = {v: k for k, v in KEY_CODES.items()}

BUTTON_ORDER = [
    "a", "b", "x", "y", "lb", "rb", "lt", "rt", "l3", "r3",
    "select", "start", "star", "home", "up", "down", "left", "right",
    "p1", "p2",
]

OPTION_BITS: dict[int, str] = {
    0x1: "invert LS X",
    0x2: "invert LS Y",
    0x4: "invert RS X",
    0x8: "invert RS Y",
    0x10: "swap sticks",
    0x80: "swap triggers",
    0x100: "swap LS / d-pad",
    0x8000: "trigger rumble",
}


def crc16_kermit(data: bytes) -> int:
    """Poly réfléchi 0x8408, init 0xFFFF, pas de xor final (variante 8BitDo)."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    return crc & 0xFFFF


def record_crc(record: bytes) -> int:
    return crc16_kermit(record[2:RECORD_SIZE])


def block_offset(slot: int) -> int:
    return HEADER_SIZE + BLOCK_SIZE * slot


def blank_record(record_id: int = 0x01) -> bytearray:
    record = bytearray(b"\xFF" * RECORD_SIZE)
    record[2] = 0xFF
    record[3] = record_id
    for slot in range(SLOTS):
        record[block_offset(slot) + OFF_MARKER : block_offset(slot) + OFF_MARKER + 2] = BLOCK_MARKER
    return record


def finalise(record: bytearray) -> bytes:
    """Met à jour le CRC d'en-tête et renvoie le record prêt à écrire."""
    struct.pack_into("<H", record, 0, record_crc(record))
    return bytes(record)


@dataclass
class Profile:
    index: int
    flag: int = FLAG_ERASED
    mapping_flag: int = FLAG_ERASED
    mapping: list[int] = field(default_factory=lambda: [0] * MAP_COUNT)
    calibration: tuple[int, ...] = ()
    sticks_flag: int = FLAG_ERASED
    sticks: tuple[int, int, int, int] = (0, 0, 0, 0)
    triggers_flag: int = FLAG_ERASED
    triggers: tuple[int, int, int, int] = (0, 0, 0, 0)
    options_flag: int = FLAG_ERASED
    options: int = 0

    @property
    def enabled(self) -> bool:
        return self.flag == FLAG_ENABLED

    @property
    def base(self) -> int:
        return block_offset(self.index)


@dataclass
class Record:
    record_id: int
    profiles: list[Profile]
    header_crc: int = 0
    stored_crc: int = 0

    @property
    def crc_ok(self) -> bool:
        return self.header_crc == self.stored_crc

    @classmethod
    def parse(cls, record: bytes) -> "Record":
        if len(record) < RECORD_SIZE:
            raise ValueError(f"record trop court : {len(record)} < {RECORD_SIZE}")
        (header_crc,) = struct.unpack_from("<H", record, 0)
        profiles: list[Profile] = []
        for slot in range(SLOTS):
            base = block_offset(slot)
            (flag,) = struct.unpack_from("<I", record, base + OFF_FLAG)
            (map_flag,) = struct.unpack_from("<I", record, base + OFF_MAP_FLAG)
            mapping = list(
                struct.unpack_from(f"<{MAP_COUNT}I", record, base + OFF_MAP)
            )
            calibration = struct.unpack_from(f"<{CAL_COUNT}f", record, base + OFF_CAL)
            (sticks_flag,) = struct.unpack_from("<I", record, base + OFF_STICKS_FLAG)
            sticks = struct.unpack_from("<BBBB", record, base + OFF_STICKS)
            (trig_flag,) = struct.unpack_from("<I", record, base + OFF_TRIGGERS_FLAG)
            triggers = struct.unpack_from("<BBBB", record, base + OFF_TRIGGERS)
            (opt_flag,) = struct.unpack_from("<I", record, base + OFF_OPTIONS_FLAG)
            (options,) = struct.unpack_from("<I", record, base + OFF_OPTIONS)
            profiles.append(
                Profile(
                    index=slot,
                    flag=flag,
                    mapping_flag=map_flag,
                    mapping=mapping,
                    calibration=tuple(calibration),
                    sticks_flag=sticks_flag,
                    sticks=tuple(sticks),  # type: ignore[arg-type]
                    triggers_flag=trig_flag,
                    triggers=tuple(triggers),  # type: ignore[arg-type]
                    options_flag=opt_flag,
                    options=options,
                )
            )
        return cls(
            record_id=record[3],
            profiles=profiles,
            header_crc=header_crc,
            stored_crc=record_crc(record),
        )

    # -- rendu lisible ---------------------------------------------------
    def describe_sticks(self, slot: int) -> str:
        p = self.profiles[slot]
        if p.sticks_flag != FLAG_ENABLED:
            return "désactivé"
        ls_start, ls_end, rs_start, rs_end = p.sticks
        return f"LS {ls_start}→{ls_end}  RS {rs_start}→{rs_end}"

    def describe_triggers(self, slot: int) -> str:
        p = self.profiles[slot]
        if p.triggers_flag != FLAG_ENABLED:
            return "désactivé"
        lt_start, lt_end, rt_start, rt_end = p.triggers
        return f"LT {lt_start}→{lt_end}  RT {rt_start}→{rt_end}"

    def describe_mapping(self, slot: int) -> list[str]:
        p = self.profiles[slot]
        if p.mapping_flag != FLAG_ENABLED:
            return ["désactivé"]
        out = []
        for button, code in zip(BUTTON_ORDER, p.mapping):
            if code in (0, FLAG_ERASED):
                continue
            name = CODE_NAMES.get(code, f"0x{code:x}")
            if name == button:
                continue
            out.append(f"{button}→(rien)" if name == "none" else f"{button}→{name}")
        return out

    def describe_options(self, slot: int) -> list[str]:
        p = self.profiles[slot]
        if p.options_flag != FLAG_ENABLED:
            return ["désactivé"]
        return [name for bit, name in OPTION_BITS.items() if p.options & bit]
