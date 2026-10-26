"""Transport BLE du protocole de configuration 8BitDo (famille « Three/Gamesir »).

L'app Android de 8BitDo configure cette famille **exclusivement en BLE** : le câble
USB ne sert qu'à l'alimentation. La trame est celle du USB sans l'encapsulation HID
(pas d'ID de rapport, pas de préfixe de longueur) :

    requête : 04 | u16 cmd | u16 sub | u16 len | u16 crc | u32 total | u32 offset | data
    réponse : 04 | 00 | u16 cmd | u16 len | u16 crc | u32 total | u32 offset | data

Service   : 00010203-0405-0607-0809-0A0B0C0D1910
Caractér. : 00010203-0405-0607-0809-0A0B0C0D2B11
MTU       : 67 pour cette famille (charge utile ≤ 45 o par trame de config)
"""

from __future__ import annotations

import asyncio
import struct
from dataclasses import dataclass

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

SERVICE_UUID = "00010203-0405-0607-0809-0a0b0c0d1910"
CHAR_UUID = "00010203-0405-0607-0809-0a0b0c0d2b11"

NAME_PREFIXES = ("81HB", "80GG", "82CE", "80NA", "8ap", "80EL", "80GQ")

TRANSFER = 0x04
CMD_WRITE = 0x0001
CMD_READ = 0x0002
CMD_COMMIT = 0x0006
CMD_REPORT_STATE = 0x0007
CMD_COMMIT_SUB = 0x0015

CHUNK = 45
RECORD_SIZE = 1652


def crc16_kermit(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    return crc & 0xFFFF


def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc & 0xFFFF


@dataclass
class Frame:
    raw: bytes

    @property
    def ok(self) -> bool:
        return len(self.raw) >= 18 and self.raw[0] == TRANSFER

    @property
    def command(self) -> int:
        return struct.unpack_from("<H", self.raw, 2)[0]

    @property
    def length(self) -> int:
        return struct.unpack_from("<H", self.raw, 4)[0]

    @property
    def total(self) -> int:
        return struct.unpack_from("<I", self.raw, 8)[0]

    @property
    def offset(self) -> int:
        return struct.unpack_from("<I", self.raw, 12)[0]

    @property
    def data(self) -> bytes:
        return self.raw[16 : 16 + self.length]

    def __str__(self) -> str:
        return (
            f"cmd={self.command} len={self.length} total={self.total} "
            f"offset={self.offset} data={self.data[:16].hex(' ')}"
        )


def build_request(
    command: int, sub: int = 0, data: bytes = b"", total: int = 0, offset: int = 0, crc: int = 0
) -> bytes:
    header = struct.pack("<HHHHII", command, sub, len(data), crc, total, offset)
    return bytes([TRANSFER]) + header + data


async def scan(timeout: float = 8.0) -> list[BLEDevice]:
    found = await BleakScanner.discover(timeout=timeout)
    return [
        d
        for d in found
        if any((d.name or "").startswith(p) for p in NAME_PREFIXES)
        or "8bitdo" in (d.name or "").lower()
    ]


class BleConfig:
    def __init__(self, device: BLEDevice) -> None:
        self.device = device
        self.client = BleakClient(device, timeout=10.0)
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()

    def _on_notify(self, _char, data: bytearray) -> None:
        self._queue.put_nowait(bytes(data))

    async def __aenter__(self) -> "BleConfig":
        await self.client.connect()
        await self.client.start_notify(CHAR_UUID, self._on_notify)
        return self

    async def __aexit__(self, *exc) -> None:
        try:
            await self.client.stop_notify(CHAR_UUID)
        finally:
            await self.client.disconnect()

    async def request(self, payload: bytes, timeout: float = 2.0) -> bytes | None:
        await self.client.write_gatt_char(CHAR_UUID, payload, response=True)
        try:
            return await asyncio.wait_for(self._queue.get(), timeout)
        except asyncio.TimeoutError:
            return None

    async def read_block(self, offset: int, length: int, total: int) -> bytes | None:
        raw = await self.request(build_request(CMD_READ, 0, b"\x00" * length, total, offset))
        if raw is None:
            return None
        frame = Frame(raw)
        return frame.data

    async def read_record(self, total: int = RECORD_SIZE) -> bytes | None:
        buf = bytearray()
        while len(buf) < total:
            chunk = await self.read_block(len(buf), CHUNK, total)
            if not chunk:
                return None
            buf += chunk
        return bytes(buf[:total])

    async def version(self) -> bytes | None:
        """Requête courte `81 05 00 21 01` sans l'encapsulation HID."""
        return await self.request(bytes.fromhex("04 05 00 21 01"))
