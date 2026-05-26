"""Read evdev events."""

from __future__ import annotations

from collections.abc import Iterator

from evdev import InputDevice, categorize, ecodes, list_devices


def list_event_device_paths() -> list[str]:
    return sorted(list_devices())


def iter_events(path: str, limit: int | None = None) -> Iterator[dict[str, str | int | float]]:
    device = InputDevice(path)
    count = 0
    try:
        for event in device.read_loop():
            rendered = categorize(event) if event.type in ecodes.bytype else event
            yield {
                "path": path,
                "timestamp": event.timestamp(),
                "type": event.type,
                "code": event.code,
                "value": event.value,
                "description": str(rendered),
            }
            count += 1
            if limit is not None and count >= limit:
                break
    finally:
        device.close()
