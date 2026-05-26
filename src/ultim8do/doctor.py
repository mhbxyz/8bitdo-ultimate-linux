"""Environment checks for ultim8do."""

from __future__ import annotations

import grp
import importlib.util
import os
import platform
from dataclasses import asdict, dataclass, field

from .devices import ControllerInfo, list_detected_controllers
from .sdl import validate_mapping_file
from .udev import get_rule_status


@dataclass(slots=True)
class DoctorSystemInfo:
    os_name: str
    kernel: str
    session: str
    user_in_input_group: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "os": self.os_name,
            "kernel": self.kernel,
            "session": self.session,
            "user_in_input_group": self.user_in_input_group,
        }


@dataclass(slots=True)
class DoctorDependency:
    name: str
    ok: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class DoctorResult:
    system: DoctorSystemInfo
    controllers: list[ControllerInfo]
    dependencies: list[DoctorDependency] = field(default_factory=list)
    sdl_warnings: list[str] = field(default_factory=list)
    udev_rule_installed: bool = False
    recommendations: list[str] = field(default_factory=list)

    @property
    def permissions(self) -> dict[str, bool]:
        permissions: dict[str, bool] = {}
        for controller in self.controllers:
            if controller.evdev_path and controller.evdev_readable is not None:
                permissions[controller.evdev_path] = controller.evdev_readable
            if controller.joystick_path and controller.joystick_readable is not None:
                permissions[controller.joystick_path] = controller.joystick_readable
            if controller.hidraw_path and controller.hidraw_readable is not None:
                permissions[controller.hidraw_path] = controller.hidraw_readable
        return permissions

    @property
    def ok(self) -> bool:
        return all(dependency.ok for dependency in self.dependencies)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "system": self.system.to_dict(),
            "controllers": [controller.to_dict() for controller in self.controllers],
            "permissions": self.permissions,
            "dependencies": [dependency.to_dict() for dependency in self.dependencies],
            "sdl_warnings": self.sdl_warnings,
            "udev_rule_installed": self.udev_rule_installed,
            "recommendations": self.recommendations,
        }


def _read_os_name() -> str:
    try:
        with open("/etc/os-release", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
                if line.startswith("NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return platform.system()


def _read_session() -> str:
    session_type = os.environ.get("XDG_SESSION_TYPE", "unknown")
    desktop = os.environ.get("XDG_CURRENT_DESKTOP") or os.environ.get("DESKTOP_SESSION") or "unknown"
    return f"{session_type.capitalize()}/{desktop}"


def _user_in_input_group() -> bool:
    try:
        input_group = grp.getgrnam("input")
    except KeyError:
        return False
    return input_group.gr_gid in os.getgroups()


def _check_dependency(module_name: str) -> DoctorDependency:
    return DoctorDependency(name=module_name, ok=importlib.util.find_spec(module_name) is not None)


def run_doctor() -> DoctorResult:
    dependencies = [_check_dependency(name) for name in ("evdev", "pyudev", "rich", "typer")]
    try:
        controllers = list_detected_controllers()
    except Exception as exc:  # pragma: no cover - host-specific defensive path
        controllers = [
            ControllerInfo(
                name=f"detection-error: {exc}",
                transport="unknown",
                tests={
                    "buttons": "missing",
                    "axes": "missing",
                    "triggers": "missing",
                    "rumble": "unknown",
                    "gyro": "missing",
                    "back_buttons": "missing",
                },
            )
        ]
    sdl_warnings = validate_mapping_file()
    udev_status = get_rule_status()
    recommendations: list[str] = []
    unreadable_nodes = any(
        readable is False
        for controller in controllers
        for readable in (controller.evdev_readable, controller.joystick_readable, controller.hidraw_readable)
    )
    if controllers and (not udev_status.system_exists or unreadable_nodes):
        recommendations.append("Install udev rules: sudo ultim8do install-udev")
    if sdl_warnings:
        recommendations.append("Review SDL mapping warnings with: uv run ultim8do sdl validate")
    return DoctorResult(
        system=DoctorSystemInfo(
            os_name=_read_os_name(),
            kernel=platform.release(),
            session=_read_session(),
            user_in_input_group=_user_in_input_group(),
        ),
        controllers=controllers,
        dependencies=dependencies,
        sdl_warnings=sdl_warnings,
        udev_rule_installed=udev_status.system_exists,
        recommendations=recommendations,
    )
