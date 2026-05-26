"""Device discovery helpers."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pyudev
from evdev import InputDevice, ecodes, list_devices

from .constants import EIGHTBITDO_VENDOR_ID, KNOWN_EIGHTBITDO_NAMES, KNOWN_EIGHTBITDO_PRODUCT_IDS

BUS_BLUETOOTH = 0x05
BUS_USB = 0x03


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


def is_known_product_id(product_id: int | None) -> bool:
    return product_id in KNOWN_EIGHTBITDO_PRODUCT_IDS


def _normalize_text(value: str | None) -> str:
    return (value or "").strip().casefold()


def _name_matches_8bitdo(name: str | None) -> bool:
    normalized = _normalize_text(name)
    return any(candidate.casefold() in normalized for candidate in KNOWN_EIGHTBITDO_NAMES)


def _gamepad_capability_names(capabilities: dict[str, list[str]]) -> set[str]:
    names: set[str] = set()
    for values in capabilities.values():
        names.update(values)
    return names


def _has_gamepad_axes(capabilities: dict[str, list[str]]) -> bool:
    names = _gamepad_capability_names(capabilities)
    return "ABS_X" in names and "ABS_Y" in names


def _has_gamepad_buttons(capabilities: dict[str, list[str]]) -> bool:
    names = _gamepad_capability_names(capabilities)
    if "BTN_GAMEPAD" in names:
        return True
    return any(name in names for name in {"BTN_SOUTH", "BTN_EAST", "BTN_NORTH", "BTN_WEST", "BTN_A", "BTN_B"})


def _is_gamepad(capabilities: dict[str, list[str]]) -> bool:
    return _has_gamepad_axes(capabilities) and _has_gamepad_buttons(capabilities)


def detection_reasons_for_device(device: "InputDeviceInfo") -> list[str]:
    reasons: list[str] = []
    if _name_matches_8bitdo(device.name):
        reasons.append("name")
    if is_supported_vendor_id(device.vendor_id):
        reasons.append("vendor_id")
    if is_known_product_id(device.product_id):
        reasons.append("product_id")
    if _is_gamepad(device.capabilities) and reasons:
        reasons.append("gamepad_capabilities")
    return reasons


def looks_like_8bitdo_controller(device: "InputDeviceInfo") -> bool:
    return bool(detection_reasons_for_device(device))


def _format_capabilities(raw_capabilities: dict[int, list[Any]]) -> tuple[dict[str, list[str]], list[str]]:
    formatted: dict[str, list[str]] = {}
    flat_names: set[str] = set()
    for event_type, entries in raw_capabilities.items():
        event_name = ecodes.EV.get(event_type, str(event_type))
        type_map = ecodes.bytype.get(event_type, {})
        names: list[str] = []
        for entry in entries:
            code = entry[0] if isinstance(entry, tuple) else entry
            mapped = type_map.get(code, str(code)) if isinstance(type_map, dict) else str(code)
            aliases = mapped if isinstance(mapped, tuple) else (mapped,)
            for alias in aliases:
                alias_name = str(alias)
                names.append(alias_name)
                flat_names.add(alias_name)
        formatted[event_name] = sorted(set(names))
    return formatted, sorted(flat_names)


def _normalize_hid_id(value: str | None) -> tuple[int | None, int | None]:
    if not value:
        return None, None
    parts = value.split(":")
    if len(parts) != 3:
        return None, None
    return normalize_hex_identifier(parts[1]), normalize_hex_identifier(parts[2])


def _guess_transport(name: str, bus_type: int | None, properties: dict[str, str]) -> str:
    normalized_name = _normalize_text(name)
    id_bus = _normalize_text(properties.get("ID_BUS"))
    model = _normalize_text(properties.get("ID_MODEL"))
    if bus_type == BUS_BLUETOOTH or id_bus == "bluetooth":
        return "Bluetooth"
    if bus_type == BUS_USB or id_bus == "usb":
        if "2.4g" in normalized_name or "2.4g" in model or "dongle" in normalized_name or "dongle" in model:
            return "2.4G"
        return "USB"
    return "unknown"


def _readable(path: str | None) -> bool | None:
    if not path:
        return None
    return os.access(path, os.R_OK)


def _resolve_parent(device: pyudev.Device) -> pyudev.Device | None:
    return device.find_parent("usb", "usb_device") or device.find_parent("hid") or device.parent


def _read_attribute(device: pyudev.Device | None, attribute: str) -> str | None:
    if device is None:
        return None
    try:
        return device.attributes.asstring(attribute)
    except (KeyError, OSError, UnicodeDecodeError):
        return None


def _guess_name(device: pyudev.Device, parent: pyudev.Device | None) -> str:
    for key in ("product", "name"):
        value = _read_attribute(parent, key)
        if value:
            return value
    for key in ("NAME", "HID_NAME", "ID_MODEL_FROM_DATABASE", "ID_MODEL", "PRODUCT"):
        value = device.properties.get(key)
        if value:
            return str(value).strip('"')
    return device.sys_name


def _build_group_key(device: "InputDeviceInfo") -> str:
    if device.serial:
        return f"serial:{device.serial}"
    if device.uniq:
        return f"uniq:{device.uniq}"
    if device.parent_path:
        return f"parent:{device.parent_path}"
    if device.properties.get("ID_PATH"):
        return f"id_path:{device.properties['ID_PATH']}"
    if device.phys:
        return f"phys:{device.phys.rsplit('/input', 1)[0]}"
    vendor = f"{device.vendor_id:04x}" if device.vendor_id is not None else "unknown"
    product = f"{device.product_id:04x}" if device.product_id is not None else "unknown"
    return f"fallback:{vendor}:{product}:{_normalize_text(device.name)}"


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
    phys: str | None = None
    uniq: str | None = None
    driver: str | None = None
    readable: bool | None = None
    parent_path: str | None = None
    transport: str = "unknown"
    properties: dict[str, str] = field(default_factory=dict)
    capabilities: dict[str, list[str]] = field(default_factory=dict)
    capability_names: list[str] = field(default_factory=list)

    @property
    def is_8bitdo(self) -> bool:
        return looks_like_8bitdo_controller(self)

    @property
    def detection_reasons(self) -> list[str]:
        return detection_reasons_for_device(self)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["is_8bitdo"] = self.is_8bitdo
        payload["detection_reasons"] = self.detection_reasons
        return payload


@dataclass(slots=True)
class ControllerInfo:
    name: str
    transport: str
    vendor_id: int | None = None
    product_id: int | None = None
    serial: str | None = None
    evdev_path: str | None = None
    joystick_path: str | None = None
    hidraw_path: str | None = None
    evdev_readable: bool | None = None
    joystick_readable: bool | None = None
    hidraw_readable: bool | None = None
    capabilities: dict[str, list[str]] = field(default_factory=dict)
    detection_reasons: list[str] = field(default_factory=list)
    tests: dict[str, str] = field(default_factory=dict)
    paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def device_info_from_udev_device(device: pyudev.Device) -> InputDeviceInfo:
    parent = _resolve_parent(device)
    hid_vendor, hid_product = _normalize_hid_id(device.properties.get("HID_ID"))
    vendor_id = normalize_hex_identifier(
        device.properties.get("ID_VENDOR_ID")
        or _read_attribute(parent, "idVendor")
        or hid_vendor
    )
    product_id = normalize_hex_identifier(
        device.properties.get("ID_MODEL_ID")
        or _read_attribute(parent, "idProduct")
        or hid_product
    )
    serial = device.properties.get("ID_SERIAL_SHORT") or (parent.properties.get("ID_SERIAL_SHORT") if parent else None)
    bus_type = None
    for value in (
        device.properties.get("ID_BUS"),
        parent.properties.get("ID_BUS") if parent else None,
    ):
        if _normalize_text(value) == "bluetooth":
            bus_type = BUS_BLUETOOTH
        elif _normalize_text(value) == "usb":
            bus_type = BUS_USB
    properties = {
        key: value
        for key, value in device.properties.items()
        if key.startswith("ID_") or key.startswith("HID_") or key in {"DEVNAME", "SUBSYSTEM"}
    }
    name = _guess_name(device, parent)
    transport = _guess_transport(name, bus_type, properties)
    return InputDeviceInfo(
        path=device.device_node or device.sys_name,
        name=name,
        subsystem=device.subsystem,
        vendor_id=vendor_id,
        product_id=product_id,
        bus_type=bus_type,
        serial=serial,
        syspath=device.sys_path,
        phys=device.properties.get("PHYS") or device.properties.get("HID_PHYS"),
        uniq=device.properties.get("UNIQ") or device.properties.get("HID_UNIQ"),
        driver=device.properties.get("ID_USB_DRIVER") or device.driver or (parent.driver if parent else None),
        readable=_readable(device.device_node),
        parent_path=parent.sys_path if parent else None,
        transport=transport,
        properties=properties,
    )


def _device_info_from_node_path(path: str, context: pyudev.Context | None = None) -> InputDeviceInfo | None:
    context = context or pyudev.Context()
    try:
        device = pyudev.Devices.from_device_file(context, path)
    except pyudev.DeviceNotFoundByFileError:
        return None
    return device_info_from_udev_device(device)


def list_udev_devices(context: pyudev.Context | None = None) -> list[InputDeviceInfo]:
    context = context or pyudev.Context()
    devices: list[InputDeviceInfo] = []
    for subsystem in ("input", "hidraw"):
        for device in context.list_devices(subsystem=subsystem):
            if not device.device_node:
                continue
            devices.append(device_info_from_udev_device(device))
    return sorted(devices, key=lambda item: item.path)


def list_evdev_devices() -> list[InputDeviceInfo]:
    context = pyudev.Context()
    devices: list[InputDeviceInfo] = []
    for path in sorted(list_devices()):
        fallback = _device_info_from_node_path(path, context=context)
        try:
            input_device = InputDevice(path)
        except OSError:
            if fallback is not None:
                devices.append(fallback)
            continue
        try:
            raw_capabilities = input_device.capabilities()
            capabilities, capability_names = _format_capabilities(raw_capabilities)
            base = fallback or InputDeviceInfo(path=path, name=input_device.name or path, subsystem="input")
            base.name = input_device.name or base.name
            base.vendor_id = input_device.info.vendor or base.vendor_id
            base.product_id = input_device.info.product or base.product_id
            base.bus_type = input_device.info.bustype or base.bus_type
            base.phys = input_device.phys or base.phys
            base.uniq = input_device.uniq or base.uniq
            base.syspath = getattr(input_device, "path", None) or base.syspath
            base.readable = True
            base.capabilities = capabilities
            base.capability_names = capability_names
            base.transport = _guess_transport(base.name, base.bus_type, base.properties)
            devices.append(base)
        finally:
            input_device.close()
    return sorted(devices, key=lambda item: item.path)


def list_joystick_devices(context: pyudev.Context | None = None) -> list[InputDeviceInfo]:
    context = context or pyudev.Context()
    devices: list[InputDeviceInfo] = []
    for path in sorted(Path("/dev/input").glob("js*")):
        info = _device_info_from_node_path(str(path), context=context)
        if info is None:
            continue
        info.subsystem = "joystick"
        info.transport = _guess_transport(info.name, info.bus_type, info.properties)
        devices.append(info)
    return devices


def list_hidraw_devices(context: pyudev.Context | None = None) -> list[InputDeviceInfo]:
    context = context or pyudev.Context()
    devices: list[InputDeviceInfo] = []
    for device in context.list_devices(subsystem="hidraw"):
        if not device.device_node:
            continue
        info = device_info_from_udev_device(device)
        info.subsystem = "hidraw"
        devices.append(info)
    return sorted(devices, key=lambda item: item.path)


def _classify_tests(capabilities: dict[str, list[str]]) -> dict[str, str]:
    names = _gamepad_capability_names(capabilities)
    triggers = {"ABS_Z", "ABS_RZ", "ABS_BRAKE", "ABS_GAS"}
    trigger_count = len(triggers & names)
    if trigger_count >= 2:
        triggers_state = "detected"
    elif trigger_count == 1:
        triggers_state = "partial"
    else:
        triggers_state = "missing"
    rumble = "detected" if "FF_RUMBLE" in names else "unknown"
    gyro = "detected" if {"ABS_RZ_GYRO", "ABS_GYRO_X", "ABS_GYRO_Y", "ABS_GYRO_Z"} & names else "missing"
    back_buttons = "detected" if {"BTN_TRIGGER_HAPPY1", "BTN_TRIGGER_HAPPY2", "BTN_TRIGGER_HAPPY3", "BTN_TRIGGER_HAPPY4"} & names else "missing"
    return {
        "buttons": "detected" if _has_gamepad_buttons(capabilities) else "missing",
        "axes": "detected" if _has_gamepad_axes(capabilities) else "missing",
        "triggers": triggers_state,
        "rumble": rumble,
        "gyro": gyro,
        "back_buttons": back_buttons,
    }


def list_detected_controllers() -> list[ControllerInfo]:
    context = pyudev.Context()
    nodes_by_path: dict[str, InputDeviceInfo] = {}
    for collection in (list_udev_devices(context), list_evdev_devices(), list_joystick_devices(context), list_hidraw_devices(context)):
        for device in collection:
            existing = nodes_by_path.get(device.path)
            nodes_by_path[device.path] = merge_device_info(existing, device) if existing else device

    grouped: dict[str, list[InputDeviceInfo]] = {}
    for device in nodes_by_path.values():
        grouped.setdefault(_build_group_key(device), []).append(device)

    controllers: list[ControllerInfo] = []
    for devices in grouped.values():
        if not any(looks_like_8bitdo_controller(device) for device in devices):
            continue
        devices.sort(key=lambda item: item.path)
        preferred = next((device for device in devices if device.capabilities), devices[0])
        evdev = next((device for device in devices if device.path.startswith("/dev/input/event")), None)
        joystick = next((device for device in devices if device.path.startswith("/dev/input/js")), None)
        hidraw = next((device for device in devices if device.path.startswith("/dev/hidraw")), None)
        transport = next((device.transport for device in devices if device.transport != "unknown"), preferred.transport)
        detection_reasons = sorted({reason for device in devices for reason in device.detection_reasons})
        capabilities = evdev.capabilities if evdev and evdev.capabilities else preferred.capabilities
        controllers.append(
            ControllerInfo(
                name=preferred.name,
                transport=transport,
                vendor_id=preferred.vendor_id,
                product_id=preferred.product_id,
                serial=preferred.serial,
                evdev_path=evdev.path if evdev else None,
                joystick_path=joystick.path if joystick else None,
                hidraw_path=hidraw.path if hidraw else None,
                evdev_readable=evdev.readable if evdev else None,
                joystick_readable=joystick.readable if joystick else None,
                hidraw_readable=hidraw.readable if hidraw else None,
                capabilities=capabilities,
                detection_reasons=detection_reasons,
                tests=_classify_tests(capabilities),
                paths=sorted(device.path for device in devices),
            )
        )
    return sorted(controllers, key=lambda item: (item.name.casefold(), item.evdev_path or item.joystick_path or item.hidraw_path or ""))


def list_candidate_devices() -> list[InputDeviceInfo]:
    controller_paths = {path for controller in list_detected_controllers() for path in controller.paths}
    merged: dict[str, InputDeviceInfo] = {}
    for collection in (list_udev_devices(), list_evdev_devices(), list_joystick_devices(), list_hidraw_devices()):
        for device in collection:
            if device.path not in controller_paths:
                continue
            existing = merged.get(device.path)
            merged[device.path] = merge_device_info(existing, device) if existing else device
    return sorted(merged.values(), key=lambda item: item.path)


def get_device_by_path(path: str) -> InputDeviceInfo | None:
    candidate_paths = {device.path for device in list_candidate_devices()}
    merged: InputDeviceInfo | None = None
    for collection in (list_udev_devices(), list_evdev_devices(), list_joystick_devices(), list_hidraw_devices()):
        for device in collection:
            if device.path == path and (device.is_8bitdo or path in candidate_paths):
                merged = merge_device_info(merged, device) if merged else device
    return merged


def classify_capability_tests(capabilities: dict[str, list[str]]) -> dict[str, str]:
    return _classify_tests(capabilities)


def merge_device_info(existing: InputDeviceInfo | None, incoming: InputDeviceInfo) -> InputDeviceInfo:
    if existing is None:
        return incoming
    if not existing.capabilities and incoming.capabilities:
        existing.capabilities = incoming.capabilities
        existing.capability_names = incoming.capability_names
    for field_name in (
        "name",
        "subsystem",
        "vendor_id",
        "product_id",
        "bus_type",
        "serial",
        "syspath",
        "phys",
        "uniq",
        "driver",
        "readable",
        "parent_path",
        "transport",
    ):
        current_value = getattr(existing, field_name)
        incoming_value = getattr(incoming, field_name)
        if current_value in (None, "", "unknown") and incoming_value not in (None, "", "unknown"):
            setattr(existing, field_name, incoming_value)
    existing.properties.update({key: value for key, value in incoming.properties.items() if key not in existing.properties})
    return existing
