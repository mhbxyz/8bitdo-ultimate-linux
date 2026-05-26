from pathlib import Path

from typer.testing import CliRunner

from ultim8do import cli
from ultim8do.doctor import DoctorDependency, DoctorResult, DoctorSystemInfo
from ultim8do.devices import ControllerInfo
from ultim8do.udev import UdevRuleStatus

runner = CliRunner()


def test_doctor_json_contains_expected_sections(monkeypatch) -> None:
    doctor_result = DoctorResult(
        system=DoctorSystemInfo(
            os_name="CachyOS",
            kernel="7.0.9-1-cachyos",
            session="wayland/KDE",
            user_in_input_group=True,
        ),
        controllers=[
            ControllerInfo(
                name="8BitDo Ultimate 3mode Xbox",
                transport="USB",
                vendor_id=0x2DC8,
                product_id=0x2030,
                evdev_path="/dev/input/event17",
                joystick_path="/dev/input/js0",
                hidraw_path=None,
                evdev_readable=True,
                joystick_readable=True,
                hidraw_readable=None,
                tests={
                    "buttons": "detected",
                    "axes": "detected",
                    "triggers": "partial",
                    "rumble": "unknown",
                    "gyro": "missing",
                    "back_buttons": "missing",
                },
            )
        ],
        dependencies=[DoctorDependency(name="evdev", ok=True)],
        recommendations=["Install udev rules: sudo ultim8do install-udev"],
        udev_rule_installed=False,
    )
    monkeypatch.setattr(cli, "run_doctor", lambda: doctor_result)

    result = runner.invoke(cli.app, ["doctor", "--json"])

    assert result.exit_code == 0
    assert '"system"' in result.stdout
    assert '"controllers"' in result.stdout
    assert '"permissions"' in result.stdout
    assert '"recommendations"' in result.stdout


def test_export_report_json_uses_build_report(monkeypatch) -> None:
    monkeypatch.setattr(cli, "build_report", lambda: {"doctor": {"ok": True}, "controllers": []})

    result = runner.invoke(cli.app, ["export-report", "--json"])

    assert result.exit_code == 0
    assert '"doctor"' in result.stdout


def test_install_udev_prints_instructions_when_not_root(monkeypatch) -> None:
    def raise_permission_error() -> str:
        raise PermissionError("not root")

    monkeypatch.setattr(cli, "install_bundled_rule", raise_permission_error)
    monkeypatch.setattr(cli, "install_instructions", lambda: "run installer")

    result = runner.invoke(cli.app, ["install-udev"])

    assert result.exit_code == 1
    assert "run installer" in result.stdout


def test_install_udev_success_prints_install_message(monkeypatch) -> None:
    monkeypatch.setattr(cli, "install_bundled_rule", lambda: "Installed /etc/udev/rules.d/99-8bitdo-ultimate.rules")

    result = runner.invoke(cli.app, ["install-udev"])

    assert result.exit_code == 0
    assert "Installed /etc/udev/rules.d/99-8bitdo-ultimate.rules" in result.stdout


def test_uninstall_udev_requires_sudo_when_not_root(monkeypatch) -> None:
    def raise_permission_error() -> str:
        raise PermissionError("not root")

    monkeypatch.setattr(cli, "uninstall_rule", raise_permission_error)

    result = runner.invoke(cli.app, ["uninstall-udev"])

    assert result.exit_code == 1
    assert "sudo ultim8do uninstall-udev" in result.stdout


def test_uninstall_udev_success_prints_message(monkeypatch) -> None:
    monkeypatch.setattr(cli, "uninstall_rule", lambda: "Removed /etc/udev/rules.d/99-8bitdo-ultimate.rules")

    result = runner.invoke(cli.app, ["uninstall-udev"])

    assert result.exit_code == 0
    assert "Removed /etc/udev/rules.d/99-8bitdo-ultimate.rules" in result.stdout


def test_check_udev_json_contains_expected_fields(monkeypatch) -> None:
    monkeypatch.setattr(
        cli,
        "get_rule_status",
        lambda: UdevRuleStatus(
            bundled_path=Path("/repo/udev/99-8bitdo-ultimate.rules"),
            system_path=Path("/etc/udev/rules.d/99-8bitdo-ultimate.rules"),
            bundled_exists=True,
            system_exists=False,
            bundled_content="rule",
            system_content=None,
            installed_matches_bundled=None,
        ),
    )

    result = runner.invoke(cli.app, ["check-udev", "--json"])

    assert result.exit_code == 0
    assert '"bundled_path"' in result.stdout
    assert '"system_exists"' in result.stdout
    assert '"installed_matches_bundled"' in result.stdout


def test_check_udev_human_mentions_bundled_system_and_matches(monkeypatch) -> None:
    monkeypatch.setattr(
        cli,
        "get_rule_status",
        lambda: UdevRuleStatus(
            bundled_path=Path("/repo/udev/99-8bitdo-ultimate.rules"),
            system_path=Path("/etc/udev/rules.d/99-8bitdo-ultimate.rules"),
            bundled_exists=True,
            system_exists=True,
            bundled_content="rule",
            system_content="rule",
            installed_matches_bundled=True,
        ),
    )

    result = runner.invoke(cli.app, ["check-udev"])

    assert result.exit_code == 0
    assert "Bundled rule:" in result.stdout
    assert "System rule:" in result.stdout
    assert "Matches bundled: yes" in result.stdout
