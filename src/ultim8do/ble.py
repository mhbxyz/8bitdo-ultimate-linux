"""BLE transport for the 8BitDo configuration protocol ("Three/Gamesir" family).

The 8BitDo Android app configures this family **over BLE only**; the USB cable
only provides power. The frame is the USB one without the HID encapsulation
(no report id, no length prefix):

    request  : 04 | u16 cmd | u16 sub | u16 len | u16 crc | u32 total | u32 offset | data
    response : 04 | 00 | u16 cmd | u16 len | u16 crc | u32 total | u32 offset | data

Service   : 00010203-0405-0607-0809-0A0B0C0D1910
Char.     : 00010203-0405-0607-0809-0A0B0C0D2B11
MTU       : 67 for this family, so at most 45 bytes of config per frame
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
    # Keep only the configuration identities ("81HB-X/D/W"). The pad also
    # advertises a HID identity ("8BitDo Ultimate 3mode Xbox") that does not
    # expose the configuration characteristic.
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
        """Short `81 05 00 21 01` query without the HID encapsulation."""
        return await self.request(bytes.fromhex("04 05 00 21 01"))


class FrameReader:
    """Reassemble BLE frames, which may span several notifications.

    The pad can split a 61 byte reply (16 bytes header + 45 bytes data) across
    several notifications, and sometimes returns fewer than 45 bytes of data. We
    therefore accumulate notifications until the full header is available, then
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
    """Read the whole record, handling short and fragmented replies."""
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
    """Write the record in 45 byte chunks; returns the number of bytes written."""
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
            raise RuntimeError(f"write refused at offset {offset}")
        written += len(chunk)
    return written


# Save sub-codes found in the official binaries:
#   0x67 : getSaveCustomConfigChannel (libadvancelib.so, Android app), verified on
#          hardware: the record survives a power cycle in PC mode.
#   0x15 : famille Bluetooth/2.4G (Ultimate BT, Ultimate 2.4G).
#   0x123 : Ultimate 2 (PC mode, previous generation).
COMMIT_SUBS = (0x67, 0x15)


async def commit(
    client: "BleakClient", total: int = 532, sub: int | None = None
) -> list[int]:
    """Envoie la ou les commandes de sauvegarde en flash.

    `0x67` is the code used by the official app (getSaveCustomConfigChannel) and
    verified on the 3-mode, so the first attempt is the right one. The other codes
    of the family are sent afterwards, they are no-ops when they do not apply.
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
    """Stop (0) or resume (1) the input report stream.

    The official software wraps its writes with this command; on some firmwares
    writes are ignored while reports are active.
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
