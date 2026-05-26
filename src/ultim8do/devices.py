"""Device discovery helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import pyudev
from evdev import InputDevice, list_devices

from .constants import EIGHTBITDO_VENDOR_ID


def normalize_hex_identifier(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip().lower()
    if not text:
        return None
    text = text[2:] if text.startswith("0x") else text
    try:
        return int(text, 16)
    except ValueError:
        return None


def is_supported_vendor_id(vendor_id: int | None) -> bool:
    return vendor_id == EIGHTBITDO_VENDOR_ID


@dataclass(slots=True)
class InputDeviceInfo:
    path: str
    name: str
    subsystem: str | None = None
    vendor_id: int | None = None
    product_id: int | None = None
    bus_type: int | None = None
    serial: str | None = None
    syspath: str | None = None
    properties: dict[str, str] = field(default_factory=dict)

    @property
    def is_8bitdo(self) -> bool:
        return is_supported_vendor_id(self.vendor_id)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["is_8bitdo"] = self.is_8bitdo
        return payload


def device_info_from_udev_device(device: pyudev.Device) -> InputDeviceInfo:
    parent = device.find_parent("usb", "usb_device")
    vendor_id = normalize_hex_identifier(
        device.properties.get("ID_VENDOR_ID") or (parent.attributes.asstring("idVendor") if parent else None)
    )
    product_id = normalize_hex_identifier(
        device.properties.get("ID_MODEL_ID") or (parent.attributes.asstring("idProduct") if parent else None)
    )
    serial = device.properties.get("ID_SERIAL_SHORT") or (parent.properties.get("ID_SERIAL_SHORT") if parent else None)
    return InputDeviceInfo(
        path=device.device_node or device.sys_name,
        name=device.properties.get("NAME", "").strip('"') or device.properties.get("ID_MODEL_FROM_DATABASE") or device.sys_name,
        subsystem=device.subsystem,
        vendor_id=vendor_id,
        product_id=product_id,
        serial=serial,
        syspath=device.sys_path,
        properties={
            key: value
            for key, value in device.properties.items()
            if key.startswith("ID_") or key in {"DEVNAME", "SUBSYSTEM"}
        },
    )


def list_udev_devices(context: pyudev.Context | None = None) -> list[InputDeviceInfo]:
    context = context or pyudev.Context()
    devices: list[InputDeviceInfo] = []
    for subsystem in ("input", "hidraw"):
        for device in context.list_devices(subsystem=subsystem):
            if not device.device_node:
                continue
            info = device_info_from_udev_device(device)
            if info.is_8bitdo:
                devices.append(info)
    return sorted(devices, key=lambda item: item.path)


def list_evdev_devices() -> list[InputDeviceInfo]:
    devices: list[InputDeviceInfo] = []
    for path in list_devices():
        try:
            input_device = InputDevice(path)
        except OSError:
            continue
        try:
            info = input_device.info
            devices.append(
                InputDeviceInfo(
                    path=path,
                    name=input_device.name or path,
                    subsystem="input",
                    vendor_id=info.vendor,
                    product_id=info.product,
                    bus_type=info.bustype,
                    syspath=getattr(input_device, "phys", None),
                )
            )
        finally:
            input_device.close()
    return sorted(devices, key=lambda item: item.path)


def list_candidate_devices() -> list[InputDeviceInfo]:
    detected = {device.path: device for device in list_udev_devices()}
    for device in list_evdev_devices():
        if device.is_8bitdo:
            detected.setdefault(device.path, device)
    return sorted(detected.values(), key=lambda item: item.path)


def get_device_by_path(path: str) -> InputDeviceInfo | None:
    for device in list_candidate_devices():
        if device.path == path:
            return device
    return None
