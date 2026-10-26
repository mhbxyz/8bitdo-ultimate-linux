"""Low level access to the 8BitDo pad over libusb, plus the GIP transport."""

from __future__ import annotations

import time
from dataclasses import dataclass

import usb.core
import usb.util

from .gip import (
    CMD_ACK,
    MTU,
    OPT_ACK,
    OPT_INTERNAL,
    GipMessage,
)

VID_8BITDO = 0x2DC8
PID_ULTIMATE_3MODE_XBOX = 0x2030

EP_IN = 0x81
EP_OUT = 0x01
INTERFACE = 0


class DeviceNotFound(RuntimeError):
    pass


@dataclass
class DeviceInfo:
    vid: int
    pid: int
    product: str
    serial: str
    bus: int
    address: int


def find_devices(vid: int = VID_8BITDO) -> list[DeviceInfo]:
    out: list[DeviceInfo] = []
    for dev in usb.core.find(find_all=True, idVendor=vid):
        out.append(
            DeviceInfo(
                vid=dev.idVendor,
                pid=dev.idProduct,
                product=_safe_str(dev, dev.iProduct),
                serial=_safe_str(dev, dev.iSerialNumber),
                bus=dev.bus,
                address=dev.address,
            )
        )
    return out


def _safe_str(dev, index: int) -> str:
    try:
        return usb.util.get_string(dev, index) if index else ""
    except (usb.core.USBError, ValueError):
        return ""


class GipTransport:
    """Une session GIP sur l'interface 0 (XGIP).

    The kernel `xpad` driver owns the interface, so we detach it explicitly.
    libusb can do that without privileges as long as the process may open the
    `/dev/bus/usb/...` node, see `udev/99-8bitdo-ultimate3mode.rules`.
    Important: detaching resets the device, so it re-enumerates and any cached
    handle becomes stale. Always look the device up again afterwards.
    """

    def __init__(
        self,
        vid: int = VID_8BITDO,
        pid: int = PID_ULTIMATE_3MODE_XBOX,
        interface: int = INTERFACE,
        detach_kernel_driver: bool = True,
        verbose: bool = False,
    ) -> None:
        self.vid = vid
        self.pid = pid
        self.interface = interface
        self.detach_kernel_driver = detach_kernel_driver
        self.verbose = verbose
        self.dev: usb.core.Device | None = None
        self._ep_in = None
        self._ep_out = None
        self._seq = 0
        self._claimed = False
        self._detached = False

    # -- cycle de vie ---------------------------------------------------
    def open(self) -> "GipTransport":
        dev = usb.core.find(idVendor=self.vid, idProduct=self.pid)
        if dev is None:
            raise DeviceNotFound(f"no device {self.vid:04x}:{self.pid:04x}")
        self.dev = dev

        if self.detach_kernel_driver:
            try:
                if dev.is_kernel_driver_active(self.interface):
                    dev.detach_kernel_driver(self.interface)
                    self._detached = True
            except (NotImplementedError, usb.core.USBError):
                pass

        usb.util.claim_interface(dev, self.interface)
        self._claimed = True

        cfg = dev.get_active_configuration()
        intf = cfg[(self.interface, 0)]
        self._ep_in = usb.util.find_descriptor(
            intf,
            custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress)
            == usb.util.ENDPOINT_IN
            and usb.util.endpoint_type(e.bmAttributes) == usb.util.ENDPOINT_TYPE_INTR,
        )
        self._ep_out = usb.util.find_descriptor(
            intf,
            custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress)
            == usb.util.ENDPOINT_OUT
            and usb.util.endpoint_type(e.bmAttributes) == usb.util.ENDPOINT_TYPE_INTR,
        )
        if self._ep_in is None or self._ep_out is None:
            raise RuntimeError("endpoints interrupt introuvables sur l'interface 0")
        return self

    def close(self) -> None:
        dev = self.dev
        if dev is None:
            return
        if self._claimed:
            try:
                usb.util.release_interface(dev, self.interface)
            except usb.core.USBError:
                pass
            self._claimed = False
        if self._detached:
            try:
                dev.attach_kernel_driver(self.interface)
            except usb.core.USBError:
                pass
            self._detached = False
        try:
            usb.util.dispose_resources(dev)
        except usb.core.USBError:
            pass
        self.dev = None

    def __enter__(self) -> "GipTransport":
        return self.open()

    def __exit__(self, *exc) -> None:
        self.close()

    # -- E/S ------------------------------------------------------------
    def _next_seq(self) -> int:
        self._seq = (self._seq + 1) & 0xFF
        return self._seq

    def send(self, msg: GipMessage) -> None:
        raw = msg.encode()
        if self.verbose:
            print(f"  -> {msg}")
        self._ep_out.write(raw, timeout=1000)

    def recv(self, timeout_ms: int = 1000) -> GipMessage | None:
        try:
            raw = self._ep_in.read(MTU, timeout=timeout_ms)
        except usb.core.USBTimeoutError:
            return None
        except usb.core.USBError:
            return None
        msg = GipMessage.decode(bytes(raw))
        if self.verbose:
            print(f"  <- {msg}")
        return msg

    def write(self, command: int, payload: bytes = b"", options: int = 0) -> int:
        seq = self._next_seq()
        self.send(GipMessage(command, payload, seq, options))
        return seq

    def read_matching(self, seq: int, timeout_ms: int = 1000) -> GipMessage | None:
        """Read until the ACK for sequence `seq` shows up, or another message does."""
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            msg = self.recv(max(1, int((deadline - time.monotonic()) * 1000)))
            if msg is None:
                return None
            if msg.command == CMD_ACK and msg.payload[:1] == bytes([seq]):
                return msg
            # unsolicited message: keep listening
        return None

    def ack(self, msg: GipMessage) -> None:
        """Acquitte un message entrant qui le demande."""
        if msg.options & OPT_ACK and msg.command != CMD_ACK:
            self.send(GipMessage(CMD_ACK, bytes([msg.sequence]), self._next_seq(), OPT_INTERNAL))

    def request(
        self,
        command: int,
        payload: bytes = b"",
        timeout_ms: int = 1000,
        stop_when=lambda m: True,
    ) -> list[GipMessage]:
        """Send `command` and collect replies until the timeout.

        `stop_when(msg)` allows an early exit as soon as a relevant reply lands.
        """
        seq = self.write(command, payload)
        received: list[GipMessage] = []
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            msg = self.recv(max(1, int((deadline - time.monotonic()) * 1000)))
            if msg is None:
                break
            if msg.command == CMD_ACK:
                if msg.payload[:1] == bytes([seq]):
                    continue
                continue
            received.append(msg)
            self.ack(msg)
            if stop_when(msg):
                break
        return received
