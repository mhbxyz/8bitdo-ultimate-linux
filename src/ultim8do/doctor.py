"""Environment checks for ultim8do."""

from __future__ import annotations

import importlib.util
import os
import sys
from dataclasses import dataclass

from .constants import SDL_DB_PATH
from .devices import list_candidate_devices
from .sdl import validate_mapping_file
from .udev import get_rule_status


@dataclass(slots=True)
class DoctorCheck:
    name: str
    ok: bool
    details: str

    def to_dict(self) -> dict[str, str | bool]:
        return {"name": self.name, "ok": self.ok, "details": self.details}


@dataclass(slots=True)
class DoctorResult:
    checks: list[DoctorCheck]

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    def to_dict(self) -> dict[str, object]:
        return {"ok": self.ok, "checks": [check.to_dict() for check in self.checks]}


def _check_python() -> DoctorCheck:
    return DoctorCheck(
        name="python",
        ok=sys.version_info >= (3, 12),
        details=f"Running {sys.version.split()[0]}",
    )


def _check_dependency(module_name: str) -> DoctorCheck:
    return DoctorCheck(
        name=f"dependency:{module_name}",
        ok=importlib.util.find_spec(module_name) is not None,
        details=f"Import check for {module_name}",
    )


def _check_input_access() -> DoctorCheck:
    path = "/dev/input"
    readable = os.path.isdir(path) and os.access(path, os.R_OK | os.X_OK)
    return DoctorCheck(name="input-access", ok=readable, details=f"Directory {path}")


def _check_udev_rule() -> DoctorCheck:
    status = get_rule_status()
    details = f"Bundled={status.bundled_exists}, installed={status.system_exists}"
    return DoctorCheck(name="udev-rule", ok=status.bundled_exists, details=details)


def _check_devices() -> DoctorCheck:
    try:
        devices = list_candidate_devices()
    except Exception as exc:  # pragma: no cover - defensive path for host-specific failures
        return DoctorCheck(name="device-detection", ok=False, details=str(exc))
    details = f"Detected {len(devices)} candidate device(s)"
    return DoctorCheck(name="device-detection", ok=True, details=details)


def _check_sdl_db() -> DoctorCheck:
    warnings = validate_mapping_file(SDL_DB_PATH)
    ok = SDL_DB_PATH.exists()
    details = "; ".join(warnings) if warnings else "SDL mapping database looks consistent"
    return DoctorCheck(name="sdl-db", ok=ok, details=details)


def run_doctor() -> DoctorResult:
    checks = [
        _check_python(),
        _check_dependency("evdev"),
        _check_dependency("pyudev"),
        _check_dependency("rich"),
        _check_dependency("typer"),
        _check_input_access(),
        _check_udev_rule(),
        _check_devices(),
        _check_sdl_db(),
    ]
    return DoctorResult(checks=checks)
