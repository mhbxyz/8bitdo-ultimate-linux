"""GIP transport (Xbox Game Input Protocol).

In Xbox mode the 8BitDo pad exposes the XGIP interface (class ff/47/d0) with two
64 byte interrupt endpoints. Every GIP message fits in one 64 byte frame:

    0        command      (u8)
    1        options      (u8)  ACK / INTERNAL / CHUNK
    2        sequence     (u8)
    3        length       (u8)  payload length, header excluded
    4..      payload

Messages larger than 60 useful bytes are split (CHUNK). Not implemented here:
8BitDo only sends small configuration frames.
"""

from __future__ import annotations

from dataclasses import dataclass, field

MTU = 64
HEADER_LEN = 4
MAX_PAYLOAD = MTU - HEADER_LEN

CMD_ACK = 0x01
CMD_ANNOUNCE = 0x02
CMD_STATUS = 0x03
CMD_IDENTIFY = 0x04
CMD_POWER = 0x05
CMD_AUTHENTICATE = 0x06
CMD_VIRTUAL_KEY = 0x07
CMD_AUDIO_CONTROL = 0x08
CMD_LED = 0x0A
CMD_HID_REPORT = 0x0B
CMD_FIRMWARE = 0x0C
CMD_AUDIO_SAMPLES = 0x0D
CMD_AUDIO_DATA = 0x0E
CMD_INPUT = 0x20

OPT_ACK = 0x10
OPT_INTERNAL = 0x20
OPT_CHUNK = 0x40
OPT_CHUNK_LAST = 0x80

CMD_NAMES = {
    CMD_ACK: "ACK",
    CMD_ANNOUNCE: "ANNOUNCE",
    CMD_STATUS: "STATUS",
    CMD_IDENTIFY: "IDENTIFY",
    CMD_POWER: "POWER",
    CMD_AUTHENTICATE: "AUTHENTICATE",
    CMD_VIRTUAL_KEY: "VIRTUAL_KEY",
    CMD_AUDIO_CONTROL: "AUDIO_CONTROL",
    CMD_LED: "LED",
    CMD_HID_REPORT: "HID_REPORT",
    CMD_FIRMWARE: "FIRMWARE",
    CMD_AUDIO_SAMPLES: "AUDIO_SAMPLES",
    CMD_AUDIO_DATA: "AUDIO_DATA",
    CMD_INPUT: "INPUT",
}


@dataclass
class GipMessage:
    command: int
    payload: bytes = b""
    sequence: int = 0
    options: int = 0

    def encode(self) -> bytes:
        payload = self.payload
        assert len(payload) <= MAX_PAYLOAD, "payload too long for a single frame"
        header = bytes([self.command, self.options, self.sequence, len(payload)])
        return (header + payload).ljust(MTU, b"\x00")

    @classmethod
    def decode(cls, raw: bytes) -> "GipMessage":
        length = raw[3]
        return cls(
            command=raw[0],
            options=raw[1],
            sequence=raw[2],
            payload=bytes(raw[HEADER_LEN : HEADER_LEN + length]),
        )

    @property
    def command_name(self) -> str:
        return CMD_NAMES.get(self.command, f"0x{self.command:02x}")

    def __str__(self) -> str:
        hexp = self.payload.hex(" ")
        return f"{self.command_name:14s} seq={self.sequence:3d} opt=0x{self.options:02x} {hexp}"


@dataclass
class GipAck:
    acknowledged_sequence: int
    payload: bytes = field(default_factory=bytes)
    client_sequence: int = 0
