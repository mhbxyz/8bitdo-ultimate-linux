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
    bundled_content: str | None = None
    system_content: str | None = None
    installed_matches_bundled: bool | None = None

    def to_dict(self) -> dict[str, str | bool | None]:
        return {
            "bundled_path": str(self.bundled_path),
            "system_path": str(self.system_path),
            "bundled_exists": self.bundled_exists,
            "system_exists": self.system_exists,
            "bundled_content": self.bundled_content,
            "system_content": self.system_content,
            "installed_matches_bundled": self.installed_matches_bundled,
        }


def _read_text_if_exists(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def _require_root(command_name: str) -> None:
    if os.geteuid() != 0:
        raise PermissionError(f"{command_name} must be run as root")


def _reload_rules() -> None:
    subprocess.run(["udevadm", "control", "--reload-rules"], check=True)
    subprocess.run(["udevadm", "trigger"], check=True)


def get_rule_status() -> UdevRuleStatus:
    bundled_content = _read_text_if_exists(UDEV_RULE_PATH)
    system_content = _read_text_if_exists(SYSTEM_UDEV_RULE_PATH)
    matches = None
    if bundled_content is not None and system_content is not None:
        matches = bundled_content == system_content
    return UdevRuleStatus(
        bundled_path=UDEV_RULE_PATH,
        system_path=SYSTEM_UDEV_RULE_PATH,
        bundled_exists=bundled_content is not None,
        system_exists=system_content is not None,
        bundled_content=bundled_content,
        system_content=system_content,
        installed_matches_bundled=matches,
    )


def install_instructions() -> str:
    return (
        "Install the bundled udev rule with:\n"
        "  sudo ultim8do install-udev\n\n"
        "Equivalent script:\n"
        "  sudo ./scripts/install-udev-rules.sh\n\n"
        "The bundled rule uses TAG+=\"uaccess\" for the active local user.\n"
        "Reconnect the controller if permissions do not refresh immediately."
    )


def install_bundled_rule() -> str:
    _require_root("install-udev")
    SYSTEM_UDEV_RULE_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(UDEV_RULE_PATH, SYSTEM_UDEV_RULE_PATH)
    os.chmod(SYSTEM_UDEV_RULE_PATH, 0o644)
    _reload_rules()
    return f"Installed {SYSTEM_UDEV_RULE_PATH}"


def uninstall_rule() -> str:
    _require_root("uninstall-udev")
    if SYSTEM_UDEV_RULE_PATH.exists():
        SYSTEM_UDEV_RULE_PATH.unlink()
        _reload_rules()
        return f"Removed {SYSTEM_UDEV_RULE_PATH}"
    _reload_rules()
    return f"Rule already absent: {SYSTEM_UDEV_RULE_PATH}"
