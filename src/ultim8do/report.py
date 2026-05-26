"""Build human and JSON reports."""

from __future__ import annotations

from .devices import list_candidate_devices
from .doctor import run_doctor
from .sdl import load_mappings, validate_mapping_file
from .udev import get_rule_status


def build_report() -> dict[str, object]:
    doctor = run_doctor()
    try:
        devices = [device.to_dict() for device in list_candidate_devices()]
    except Exception as exc:  # pragma: no cover - defensive path for host-specific failures
        devices = [{"error": str(exc)}]
    udev = get_rule_status().to_dict()
    sdl_warnings = validate_mapping_file()
    mappings = [mapping.to_dict() for mapping in load_mappings()]
    return {
        "doctor": doctor.to_dict(),
        "devices": devices,
        "udev": udev,
        "sdl": {
            "warnings": sdl_warnings,
            "mappings": mappings,
        },
    }
