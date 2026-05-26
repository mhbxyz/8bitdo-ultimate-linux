"""udev inspection helpers."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess

from .constants import SYSTEM_UDEV_RULE_PATH, UDEV_RULE_PATH


@dataclass(slots=True)
class UdevRuleStatus:
    bundled_path: Path
    system_path: Path
    bundled_exists: bool
    system_exists: bool

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "bundled_path": str(self.bundled_path),
            "system_path": str(self.system_path),
            "bundled_exists": self.bundled_exists,
            "system_exists": self.system_exists,
        }


def get_rule_status() -> UdevRuleStatus:
    return UdevRuleStatus(
        bundled_path=UDEV_RULE_PATH,
        system_path=SYSTEM_UDEV_RULE_PATH,
        bundled_exists=UDEV_RULE_PATH.exists(),
        system_exists=SYSTEM_UDEV_RULE_PATH.exists(),
    )


def install_instructions() -> str:
    return (
        "Install the bundled udev rule with:\n"
        "  sudo ultim8do install-udev\n\n"
        "Equivalent script:\n"
        "  sudo ./scripts/install-udev-rules.sh\n\n"
        "Then reload rules and reconnect the controller if needed."
    )


def install_bundled_rule() -> str:
    if os.geteuid() != 0:
        raise PermissionError("install-udev must be run as root")
    SYSTEM_UDEV_RULE_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(UDEV_RULE_PATH, SYSTEM_UDEV_RULE_PATH)
    os.chmod(SYSTEM_UDEV_RULE_PATH, 0o644)
    subprocess.run(["udevadm", "control", "--reload-rules"], check=True)
    subprocess.run(
        ["udevadm", "trigger", "--subsystem-match=input", "--subsystem-match=hidraw"],
        check=False,
    )
    return f"Installed {SYSTEM_UDEV_RULE_PATH}"
