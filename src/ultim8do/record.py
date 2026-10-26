"""Record de configuration 8BitDo Ultimate 3-mode (BLE, 532 octets).

Disposition, établie sur matériel (firmware 2.00, mode D) :

    offset  taille  contenu
    0x000   2       CRC-16/KERMIT de record[2:532], little-endian
                    -> recalculé par la manette à chaque commit
    0x002   1       réservé (0xFF)
    0x003   1       identifiant du record : 0x03 en mode D, 0x02 en mode X/PC
    0x004   ...     structure de configuration (cf. BASE ci-dessous)

La structure de configuration reprend celle de la famille Ultimate
(Ultimate 2 / 2.4G / BT), mais **sans la section macros** : le FAQ officiel
indique que la 3-mode ne gère ni turbo ni macro, ce qui retire 1176 octets
(1652 -> 476). D'où 4 + 476 = 480, complété à 532 par 52 octets de sections
supplémentaires (gyro / LED).

Les offsets ci-dessous sont exprimés **dans la structure**, il faut ajouter
`BASE` (= 4) pour les atteindre dans le record brut.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

RECORD_SIZE = 532
BASE = 4  # en-tête : crc16 (2) + réservé (1) + id de record (1)

FLAG_ENABLED = 0x20200911
FLAG_DISABLED = 0x20190000
FLAG_ERASED = 0xFFFFFFFF

SLOTS = 3

# -- offsets dans la structure (ajouter BASE pour le record brut) ------------
OFF_SLOT_FLAGS = 0x000  # 3 × u32
OFF_CRC_VALUE = 0x00C  # u32, CRC propre au modèle (non validé d'après les tests)
OFF_GAMEPAD_MODE = 0x010  # u16 : 1 = DInput/Android, 3 = Windows/XInput (à confirmer)
OFF_CUR_SLOT = 0x012  # u16 : profil actif (0..2)
OFF_NAMES = 0x014  # 3 × 32 o, UTF-16LE
OFF_RUMBLE = 0x074  # 3 × 12 o : flag, float gauche, float droite
OFF_STICKS = 0x098  # 3 × 8 o  : flag, LS début/fin, RS début/fin (0..128)
OFF_TRIGGERS = 0x0B0  # 3 × 8 o : flag, LT début/fin, RT début/fin (0..255)
OFF_SPECIAL = 0x0C8  # 3 × 8 o : flag, bits de fonctionnalités
OFF_MAPPING = 0x0E0  # 3 × 92 o : flag, 22 × u32 codes de fonction
STRUCT_SIZE = OFF_MAPPING + 92 * SLOTS  # 476

# -- codes de fonction du mapping ------------------------------------------
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
    "p4": 0x40000000,
}
CODE_NAMES = {v: k for k, v in KEY_CODES.items()}

BUTTON_ORDER = [
    "a", "b", "x", "y", "lb", "rb", "lt", "rt", "l3", "r3",
    "select", "start", "star", "home", "up", "down", "left", "right",
    "p1", "p2", "p3", "p4",
]

SPECIAL_BITS: dict[int, str] = {
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
    """CRC-16/KERMIT : poly réfléchi 0x8408, init 0xFFFF, pas de xor final."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    return crc & 0xFFFF


def record_crc(record: bytes) -> int:
    return crc16_kermit(record[2:RECORD_SIZE])


def blank_record(record_id: int = 0x03) -> bytearray:
    record = bytearray(b"\xFF" * RECORD_SIZE)
    record[2] = 0xFF
    record[3] = record_id
    return record


def finalise(record: bytearray) -> bytes:
    """Met à jour le CRC d'en-tête et renvoie le record prêt à écrire."""
    struct.pack_into("<H", record, 0, record_crc(record))
    return bytes(record)


@dataclass
class Section:
    flag: int
    raw: bytes


@dataclass
class Slot:
    index: int
    flag: int = FLAG_ERASED
    name: str = ""
    rumble: tuple[int, float, float] = (0, 0.0, 0.0)
    sticks: tuple[int, int, int, int, int] = (0, 0, 0, 0, 0)
    triggers: tuple[int, int, int, int, int] = (0, 0, 0, 0, 0)
    special: tuple[int, int] = (0, 0)
    mapping: list[int] = field(default_factory=lambda: [0] * 22)

    @property
    def enabled(self) -> bool:
        return self.flag == FLAG_ENABLED


@dataclass
class Record:
    record_id: int
    mode: int
    cur_slot: int
    slots: list[Slot]
    trailing: bytes = b""
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
        record_id = record[3]
        mode, cur_slot = struct.unpack_from("<HH", record, BASE + OFF_GAMEPAD_MODE)
        slots: list[Slot] = []
        for i in range(SLOTS):
            (flag,) = struct.unpack_from("<I", record, BASE + OFF_SLOT_FLAGS + 4 * i)
            name_raw = record[
                BASE + OFF_NAMES + 32 * i : BASE + OFF_NAMES + 32 * (i + 1)
            ]
            name = name_raw.decode("utf-16-le", "replace").split("\x00")[0]
            rumble_flag, rumble_l, rumble_r = struct.unpack_from(
                "<Iff", record, BASE + OFF_RUMBLE + 12 * i
            )
            sticks = struct.unpack_from("<IBBBB", record, BASE + OFF_STICKS + 8 * i)
            trig = struct.unpack_from("<IBBBB", record, BASE + OFF_TRIGGERS + 8 * i)
            special = struct.unpack_from("<II", record, BASE + OFF_SPECIAL + 8 * i)
            mapping = list(
                struct.unpack_from("<I22I", record, BASE + OFF_MAPPING + 92 * i)[1:]
            )
            slots.append(
                Slot(
                    index=i,
                    flag=flag,
                    name=name,
                    rumble=(rumble_flag, rumble_l, rumble_r),
                    sticks=tuple(sticks),  # type: ignore[arg-type]
                    triggers=tuple(trig),  # type: ignore[arg-type]
                    special=tuple(special),  # type: ignore[arg-type]
                    mapping=mapping,
                )
            )
        trailing = bytes(record[BASE + STRUCT_SIZE :])
        return cls(
            record_id=record_id,
            mode=mode,
            cur_slot=cur_slot,
            slots=slots,
            trailing=trailing,
            header_crc=header_crc,
            stored_crc=record_crc(record),
        )

    def describe_sticks(self, slot: int) -> str:
        flag, ls_start, ls_end, rs_start, rs_end = self.slots[slot].sticks
        if flag != FLAG_ENABLED:
            return "désactivé"
        return f"LS {ls_start}→{ls_end}  RS {rs_start}→{rs_end}"

    def describe_triggers(self, slot: int) -> str:
        flag, lt_start, lt_end, rt_start, rt_end = self.slots[slot].triggers
        if flag != FLAG_ENABLED:
            return "désactivé"
        return f"LT {lt_start}→{lt_end}  RT {rt_start}→{rt_end}"

    def describe_mapping(self, slot: int) -> list[str]:
        out = []
        for button, code in zip(BUTTON_ORDER, self.slots[slot].mapping):
            name = CODE_NAMES.get(code, f"0x{code:x}")
            if name not in ("none", button):
                out.append(f"{button}→{name}" if name != "none" else f"{button}→(rien)")
        return out

    def describe_special(self, slot: int) -> list[str]:
        flag, bits = self.slots[slot].special
        if flag != FLAG_ENABLED:
            return ["désactivé"]
        return [name for bit, name in SPECIAL_BITS.items() if bits & bit]
