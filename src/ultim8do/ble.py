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
    # On ne garde que les identités de configuration (« 81HB-X/D/W »). La manette
    # annonce aussi une identité HID « 8BitDo Ultimate 3mode Xbox » qui n'expose
    # pas la caractéristique de configuration.
    return [d for d in found if (d.name or "").startswith(NAME_PREFIXES)]


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


class FrameReader:
    """Réassemble les trames BLE, éventuellement fragmentées sur plusieurs notifications.

    Le pad peut découper une réponse de 61 octets (16 d'en-tête + 45 de données) en
    plusieurs notifications, et renvoyer parfois moins de 45 octets de données. On
    accumule donc les notifications jusqu'à disposer de l'en-tête complet puis de
    `16 + len` octets.
    """

    def __init__(self, queue: "asyncio.Queue[bytes]") -> None:
        self.queue = queue
        self.buffer = bytearray()

    async def next_frame(self, timeout: float = 1.5) -> Frame | None:
        while True:
            if len(self.buffer) >= 16:
                length = struct.unpack_from("<H", self.buffer, 4)[0]
                if len(self.buffer) >= 16 + length:
                    frame = Frame(bytes(self.buffer[: 16 + length]))
                    del self.buffer[: 16 + length]
                    return frame
            try:
                chunk = await asyncio.wait_for(self.queue.get(), timeout)
            except asyncio.TimeoutError:
                return None
            self.buffer += chunk

    def reset(self) -> None:
        self.buffer.clear()


async def read_record(client: "BleakClient", total: int = 532) -> bytes:
    """Lit le record complet (gère les réponses courtes et fragmentées)."""
    queue: asyncio.Queue[bytes] = asyncio.Queue()
    await client.start_notify(CHAR_UUID, lambda _c, data: queue.put_nowait(bytes(data)))
    reader = FrameReader(queue)
    record = bytearray(b"\xFF" * total)
    cursor = 0
    stalls = 0
    while cursor < total and stalls < 4:
        await client.write_gatt_char(
            CHAR_UUID, build_request(CMD_READ, 0, b"\x00" * CHUNK, total, cursor), response=True
        )
        frame = await reader.next_frame(1.5)
        if frame is None or frame.offset != cursor:
            stalls += 1
            reader.reset()
            await asyncio.sleep(0.2)
            continue
        if not frame.data:
            stalls += 1
            cursor = ((cursor // CHUNK) + 1) * CHUNK
            continue
        record[cursor : cursor + len(frame.data)] = frame.data
        cursor += len(frame.data)
        stalls = 0
    return bytes(record)


async def write_record(client: "BleakClient", record: bytes, total: int | None = None) -> int:
    """Écrit le record par tranches de 45 octets ; renvoie le nombre d'octets écrits."""
    queue: asyncio.Queue[bytes] = asyncio.Queue()
    await client.start_notify(CHAR_UUID, lambda _c, data: queue.put_nowait(bytes(data)))
    reader = FrameReader(queue)
    total = len(record) if total is None else total
    written = 0
    for offset in range(0, len(record), CHUNK):
        chunk = record[offset : offset + CHUNK]
        await client.write_gatt_char(
            CHAR_UUID, build_request(CMD_WRITE, 0, chunk, total, offset), response=True
        )
        frame = await reader.next_frame(2.0)
        if frame is None or frame.command != CMD_WRITE:
            raise RuntimeError(f"écriture refusée à l'offset {offset}")
        written += len(chunk)
    return written


COMMIT_SUBS = (0x15, 0x123)  # 0x15 : Bluetooth/2.4G ; 0x123 : mode PC (Windows)


async def commit(
    client: "BleakClient", total: int = 532, sub: int | None = None
) -> list[int]:
    """Envoie la ou les commandes de sauvegarde en flash.

    Le sous-code varie selon le mode : `0x15` pour le record Bluetooth/2.4G,
    `0x123` pour le record PC. On envoie les deux par défaut (le premier no-op
    est sans effet) ; `sub` force un code unique.
    """
    queue: asyncio.Queue[bytes] = asyncio.Queue()
    await client.start_notify(CHAR_UUID, lambda _c, data: queue.put_nowait(bytes(data)))
    reader = FrameReader(queue)
    subs = (sub,) if sub is not None else COMMIT_SUBS
    sent: list[int] = []
    for code in subs:
        await client.write_gatt_char(
            CHAR_UUID,
            bytes([TRANSFER]) + struct.pack("<HHHHII", CMD_COMMIT, code, 0, 0, total, 0),
            response=True,
        )
        frame = await reader.next_frame(5.0)
        if frame is not None:
            sent.append(code)
    return sent


async def report_state(client: "BleakClient", enable: bool, total: int = 532) -> bytes | None:
    """Coupe (0) ou relance (1) le flux de rapports d'entrée.

    Le logiciel officiel encadre ses écritures avec cette commande ; sur certains
    firmwares, les écritures sont ignorées tant que les rapports sont actifs.
    """
    queue: asyncio.Queue[bytes] = asyncio.Queue()
    await client.start_notify(CHAR_UUID, lambda _c, data: queue.put_nowait(bytes(data)))
    reader = FrameReader(queue)
    await client.write_gatt_char(
        CHAR_UUID,
        bytes([TRANSFER])
        + struct.pack("<HHHHII", CMD_REPORT_STATE, 0 if not enable else 1, 0, 0, total, 0),
        response=True,
    )
    frame = await reader.next_frame(2.0)
    return None if frame is None else frame.raw
