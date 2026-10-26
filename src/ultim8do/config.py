"""Client for the HID configuration channel (report 0x81 out / 0x02 in).

Used once the pad has been switched to configuration mode: it then exposes a
`/dev/hidrawN` node on which we write 64 byte reports starting with 0x81 and read
reports starting with 0x02.

The Ultimate family uses three different framings; they are wrapped behind
`FrameFormat` so they can be tried one after another on an unknown model.

Kept for reference: on the Ultimate 3-mode this HID channel never appears (no
hidraw node in Xbox mode), the real channels are BLE and GIP.
"""

from __future__ import annotations

import os
import select
import struct
import time
from dataclasses import dataclass
from enum import Enum

REPORT_OUT = 0x81
REPORT_IN = 0x02
PACKET_LEN = 64

CMD_INFO = 0x0001
CMD_READ = 0x0002
CMD_WRITE = 0x0001
CMD_REPORT = 0x0007
CMD_COMMIT = 0x0006

FLAG_ENABLED = 0x20200911


def crc16_modbus(data: bytes) -> int:
    """CRC-16/MODBUS (reflected polynomial 0xA001, init 0xFFFF)."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


class FrameFormat(Enum):
    """Framing variants found across the Ultimate family."""

    ULTIMATE2 = "ultimate2"  # 81 04 | cmd | sub | len | crc | total | offset | data
    LENGTH = "length"  # 81 n 04 | cmd | sub | len(u32) | total | offset | data
    SHORT = "short"  # 81 <n> <cmd> <param> …


@dataclass
class Response:
    raw: bytes

    @property
    def report_id(self) -> int:
        return self.raw[0]

    @property
    def cmd(self) -> int:
        return struct.unpack_from("<H", self.raw, 4)[0] if len(self.raw) >= 6 else -1

    @property
    def sub(self) -> int:
        return struct.unpack_from("<H", self.raw, 6)[0] if len(self.raw) >= 8 else -1

    def __str__(self) -> str:
        return self.raw[:32].hex(" ") + (" …" if len(self.raw) > 32 else "")


class HidConfig:
    def __init__(self, path: str, timeout: float = 1.0, crc: bool = True) -> None:
        self.path = path
        self.timeout = timeout
        self.crc = crc
        self.fd = os.open(path, os.O_RDWR)

    def close(self) -> None:
        os.close(self.fd)

    def __enter__(self) -> "HidConfig":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- E/S ------------------------------------------------------------
    def send_raw(self, payload: bytes) -> None:
        packet = payload.ljust(PACKET_LEN, b"\x00")
        assert len(packet) == PACKET_LEN
        os.write(self.fd, packet)

    def recv_raw(self, timeout: float | None = None) -> bytes | None:
        timeout = self.timeout if timeout is None else timeout
        ready, _, _ = select.select([self.fd], [], [], timeout)
        if not ready:
            return None
        return os.read(self.fd, PACKET_LEN)

    def request_raw(self, payload: bytes, timeout: float | None = None) -> bytes | None:
        self.send_raw(payload)
        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        while time.monotonic() < deadline:
            raw = self.recv_raw(max(0.0, deadline - time.monotonic()))
            if raw is None:
                return None
            return raw
        return None

    # -- trames ---------------------------------------------------------
    def short_query(self, body: bytes) -> bytes | None:
        """Fixed short query: `81 <n> <...>`, e.g. 81 05 00 21 01."""
        assert body[0] == REPORT_OUT
        return self.request_raw(body)

    def read_block(
        self,
        offset: int,
        length: int,
        total: int,
        fmt: FrameFormat = FrameFormat.ULTIMATE2,
        timeout: float | None = None,
    ) -> bytes | None:
        if fmt is FrameFormat.ULTIMATE2:
            header = struct.pack("<HHHHII", CMD_READ, 0, length, 0, total, offset)
            payload = bytes([REPORT_OUT, 0x04]) + header
        elif fmt is FrameFormat.LENGTH:
            header = struct.pack("<HHII", CMD_READ, 0, length, total) + struct.pack("<I", offset)
            payload = bytes([REPORT_OUT, 17 + 0, 0x04]) + header
        else:
            raise ValueError("unsupported format for a read")
        raw = self.request_raw(payload, timeout)
        if raw is None:
            return None
        data_start = 18 if fmt is FrameFormat.ULTIMATE2 else 19
        return raw[data_start:]

    def write_block(
        self,
        offset: int,
        data: bytes,
        total: int,
        fmt: FrameFormat = FrameFormat.ULTIMATE2,
        sub: int = 0,
        timeout: float | None = None,
    ) -> bytes | None:
        if len(data) > 45:
            raise ValueError("a write is limited to 45 bytes")
        crc = crc16_modbus(data) if (self.crc and fmt is FrameFormat.ULTIMATE2) else 0
        if fmt is FrameFormat.ULTIMATE2:
            header = struct.pack("<HHHHII", CMD_WRITE, sub, len(data), crc, total, offset)
            payload = bytes([REPORT_OUT, 0x04]) + header + data
        else:
            header = struct.pack("<HHII", CMD_WRITE, sub, len(data), total) + struct.pack("<I", offset)
            payload = bytes([REPORT_OUT, 17 + len(data), 0x04]) + header + data
        return self.request_raw(payload, timeout)

    def commit(self, fmt: FrameFormat = FrameFormat.ULTIMATE2, sub: int = 0x123) -> bytes | None:
        return self.write_block(0, b"", 0, fmt=fmt, sub=sub, timeout=5.0)

    def report_state(self, enable: bool, total: int = 0) -> bytes | None:
        """Stop (0) or resume (1) input reports around writes."""
        return self.write_block(0, b"", total, sub=1 if enable else 0)


def parse_version(raw: bytes) -> tuple[float, int, int] | None:
    """Extract (version, beta, pid) from a `02 22` or `02 04 ... 21 01` reply."""
    if len(raw) < 24:
        return None
    if raw[0] != REPORT_IN:
        return None
    if raw[1] == 0x22:
        fw = struct.unpack_from("<H", raw, 2)[0] / 100
        beta = raw[4]
        pid = struct.unpack_from("<H", raw, 6)[0]
        return fw, beta, pid
    if raw[1] == 0x04 and raw[4] == 0x21:
        fw = struct.unpack_from("<H", raw, 19)[0] / 100
        beta = raw[21]
        pid = struct.unpack_from("<H", raw, 23)[0]
        return fw, beta, pid
    return None
