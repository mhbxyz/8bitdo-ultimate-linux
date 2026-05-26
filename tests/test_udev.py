from __future__ import annotations

from ultim8do import udev


def test_get_rule_status_detects_missing_system_rule(tmp_path, monkeypatch) -> None:
    bundled = tmp_path / "99-8bitdo-ultimate.rules"
    system = tmp_path / "system.rules"
    bundled.write_text("rule", encoding="utf-8")
    monkeypatch.setattr(udev, "UDEV_RULE_PATH", bundled)
    monkeypatch.setattr(udev, "SYSTEM_UDEV_RULE_PATH", system)

    status = udev.get_rule_status()

    assert status.bundled_exists is True
    assert status.system_exists is False
    assert status.installed_matches_bundled is None


def test_get_rule_status_detects_matching_installed_rule(tmp_path, monkeypatch) -> None:
    bundled = tmp_path / "99-8bitdo-ultimate.rules"
    system = tmp_path / "system.rules"
    bundled.write_text("same", encoding="utf-8")
    system.write_text("same", encoding="utf-8")
    monkeypatch.setattr(udev, "UDEV_RULE_PATH", bundled)
    monkeypatch.setattr(udev, "SYSTEM_UDEV_RULE_PATH", system)

    status = udev.get_rule_status()

    assert status.system_exists is True
    assert status.installed_matches_bundled is True


def test_get_rule_status_detects_different_installed_rule(tmp_path, monkeypatch) -> None:
    bundled = tmp_path / "99-8bitdo-ultimate.rules"
    system = tmp_path / "system.rules"
    bundled.write_text("bundled", encoding="utf-8")
    system.write_text("system", encoding="utf-8")
    monkeypatch.setattr(udev, "UDEV_RULE_PATH", bundled)
    monkeypatch.setattr(udev, "SYSTEM_UDEV_RULE_PATH", system)

    status = udev.get_rule_status()

    assert status.installed_matches_bundled is False


def test_install_bundled_rule_rejects_non_root(monkeypatch) -> None:
    monkeypatch.setattr(udev.os, "geteuid", lambda: 1000)

    try:
        udev.install_bundled_rule()
    except PermissionError as exc:
        assert "install-udev" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("PermissionError not raised")


def test_install_bundled_rule_copies_rule_and_reloads(tmp_path, monkeypatch) -> None:
    bundled = tmp_path / "99-8bitdo-ultimate.rules"
    system = tmp_path / "etc" / "udev" / "rules.d" / "99-8bitdo-ultimate.rules"
    bundled.write_text("rule-content", encoding="utf-8")
    calls: list[list[str]] = []

    monkeypatch.setattr(udev, "UDEV_RULE_PATH", bundled)
    monkeypatch.setattr(udev, "SYSTEM_UDEV_RULE_PATH", system)
    monkeypatch.setattr(udev.os, "geteuid", lambda: 0)

    def fake_run(command: list[str], check: bool) -> None:
        calls.append(command + [f"check={check}"])

    monkeypatch.setattr(udev.subprocess, "run", fake_run)

    message = udev.install_bundled_rule()

    assert system.read_text(encoding="utf-8") == "rule-content"
    assert any(command[:3] == ["udevadm", "control", "--reload-rules"] for command in calls)
    assert any(command[:2] == ["udevadm", "trigger"] for command in calls)
    assert str(system) in message


def test_uninstall_rule_rejects_non_root(monkeypatch) -> None:
    monkeypatch.setattr(udev.os, "geteuid", lambda: 1000)

    try:
        udev.uninstall_rule()
    except PermissionError as exc:
        assert "uninstall-udev" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("PermissionError not raised")


def test_uninstall_rule_removes_installed_rule_and_reloads(tmp_path, monkeypatch) -> None:
    system = tmp_path / "etc" / "udev" / "rules.d" / "99-8bitdo-ultimate.rules"
    system.parent.mkdir(parents=True, exist_ok=True)
    system.write_text("rule-content", encoding="utf-8")
    calls: list[list[str]] = []

    monkeypatch.setattr(udev, "SYSTEM_UDEV_RULE_PATH", system)
    monkeypatch.setattr(udev.os, "geteuid", lambda: 0)

    def fake_run(command: list[str], check: bool) -> None:
        calls.append(command + [f"check={check}"])

    monkeypatch.setattr(udev.subprocess, "run", fake_run)

    message = udev.uninstall_rule()

    assert system.exists() is False
    assert any(command[:3] == ["udevadm", "control", "--reload-rules"] for command in calls)
    assert any(command[:2] == ["udevadm", "trigger"] for command in calls)
    assert str(system) in message


def test_uninstall_rule_tolerates_absent_file(tmp_path, monkeypatch) -> None:
    system = tmp_path / "etc" / "udev" / "rules.d" / "99-8bitdo-ultimate.rules"
    calls: list[list[str]] = []

    monkeypatch.setattr(udev, "SYSTEM_UDEV_RULE_PATH", system)
    monkeypatch.setattr(udev.os, "geteuid", lambda: 0)

    def fake_run(command: list[str], check: bool) -> None:
        calls.append(command + [f"check={check}"])

    monkeypatch.setattr(udev.subprocess, "run", fake_run)

    message = udev.uninstall_rule()

    assert any(command[:3] == ["udevadm", "control", "--reload-rules"] for command in calls)
    assert any(command[:2] == ["udevadm", "trigger"] for command in calls)
    assert "already absent" in message
