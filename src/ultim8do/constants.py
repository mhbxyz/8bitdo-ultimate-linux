"""Project constants."""

from __future__ import annotations

from pathlib import Path

EIGHTBITDO_VENDOR_ID = 0x2DC8
KNOWN_EIGHTBITDO_NAMES = (
    "8BitDo",
    "Ultimate Bluetooth Controller",
    "Ultimate 2.4G Controller",
    "Ultimate C Controller",
)

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent.parent
SDL_DB_PATH = PROJECT_ROOT / "mappings" / "sdl2" / "gamecontrollerdb.txt"
UDEV_RULE_PATH = PROJECT_ROOT / "udev" / "99-8bitdo-ultimate.rules"
SYSTEMD_UNIT_PATH = PROJECT_ROOT / "systemd" / "ultim8do.service"
SYSTEM_UDEV_RULE_PATH = Path("/etc/udev/rules.d/99-8bitdo-ultimate.rules")
