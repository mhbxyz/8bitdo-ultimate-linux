"""CLI entrypoint for ultim8do."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .devices import get_device_by_path, list_detected_controllers
from .doctor import run_doctor
from .evdev_reader import iter_events
from .report import build_report
from .sdl import validate_mapping_file
from .udev import get_rule_status, install_bundled_rule, install_instructions

app = typer.Typer(help="Inspect and validate 8BitDo Ultimate controllers on Linux.")
sdl_app = typer.Typer(help="SDL mapping helpers.")
udev_app = typer.Typer(help="udev helpers.")
app.add_typer(sdl_app, name="sdl")
app.add_typer(udev_app, name="udev")

console = Console()


def _print_json(payload: object) -> None:
    console.print_json(json.dumps(payload, indent=2))


def _format_hex(value: int | None) -> str:
    return f"{value:04x}" if value is not None else "missing"


def _yes_no(value: bool | None) -> str:
    if value is None:
        return "unknown"
    return "yes" if value else "no"


def _render_doctor(result: object) -> None:
    doctor = result.to_dict()
    system = doctor["system"]
    console.print("8BitDo Ultimate Linux Diagnostic")
    console.print()
    console.print("System:")
    console.print(f"  OS: {system['os']}")
    console.print(f"  Kernel: {system['kernel']}")
    console.print(f"  Session: {system['session']}")
    console.print(f"  User in input group: {_yes_no(system['user_in_input_group'])}")
    console.print()
    console.print("Detected controllers:")
    controllers = doctor["controllers"]
    if not controllers:
        console.print("  none")
    for index, controller in enumerate(controllers, start=1):
        console.print(f"  [{index}] {controller['name']}")
        console.print(f"      transport: {controller['transport']}")
        console.print(f"      vendor_id: {_format_hex(controller['vendor_id'])}")
        console.print(f"      product_id: {_format_hex(controller['product_id'])}")
        console.print(f"      evdev: {controller['evdev_path'] or 'missing'}")
        console.print(f"      joystick: {controller['joystick_path'] or 'missing'}")
        console.print(f"      hidraw: {controller['hidraw_path'] or 'missing'}")
    console.print()
    console.print("Permissions:")
    permissions = doctor["permissions"]
    if not permissions:
        console.print("  none")
    for path, readable in permissions.items():
        console.print(f"  {path}: readable {_yes_no(readable)}")
    console.print()
    console.print("Tests:")
    if not controllers:
        console.print("  none")
    for controller in controllers:
        if len(controllers) > 1:
            console.print(f"  {controller['name']}:")
        tests = controller["tests"]
        prefix = "    " if len(controllers) > 1 else "  "
        console.print(f"{prefix}buttons: {tests['buttons']}")
        console.print(f"{prefix}axes: {tests['axes']}")
        console.print(f"{prefix}triggers: {tests['triggers']}")
        console.print(f"{prefix}rumble: {tests['rumble']}")
        console.print(f"{prefix}gyro: {tests['gyro']}")
        console.print(f"{prefix}back buttons: {tests['back_buttons']}")
    if doctor["recommendations"]:
        console.print()
        console.print("Recommendation:")
        for recommendation in doctor["recommendations"]:
            if recommendation.startswith("Install udev rules:"):
                console.print("  Install udev rules:")
                console.print("    sudo ultim8do install-udev")
            else:
                console.print(f"  {recommendation}")


@app.command("doctor")
def doctor_command(as_json: bool = typer.Option(False, "--json", help="Render checks as JSON.")) -> None:
    result = run_doctor()
    if as_json:
        _print_json(result.to_dict())
        return

    _render_doctor(result)
    raise typer.Exit(code=0 if result.ok else 1)


@app.command("list")
def list_command(
    as_json: bool = typer.Option(False, "--json", help="Render devices as JSON."),
    verbose: bool = typer.Option(False, "--verbose", help="Show raw properties when available."),
) -> None:
    controllers = list_detected_controllers()
    if as_json:
        _print_json([controller.to_dict() for controller in controllers])
        return
    table = Table(title="Detected controllers")
    table.add_column("Name")
    table.add_column("Transport")
    table.add_column("Vendor")
    table.add_column("Product")
    table.add_column("evdev")
    table.add_column("joystick")
    table.add_column("hidraw")
    for controller in controllers:
        vendor = f"0x{controller.vendor_id:04x}" if controller.vendor_id is not None else "-"
        product = f"0x{controller.product_id:04x}" if controller.product_id is not None else "-"
        table.add_row(
            controller.name,
            controller.transport,
            vendor,
            product,
            controller.evdev_path or "-",
            controller.joystick_path or "-",
            controller.hidraw_path or "-",
        )
        if verbose:
            table.add_row("", json.dumps(controller.detection_reasons), "", "", "", "", "")
    console.print(table)


@app.command("inspect")
def inspect_command(path: str, as_json: bool = typer.Option(False, "--json", help="Render device as JSON.")) -> None:
    device = get_device_by_path(path)
    if device is None:
        raise typer.BadParameter(f"No candidate device found for {path}")
    if as_json:
        _print_json(device.to_dict())
        return
    table = Table(title=f"Device {path}")
    table.add_column("Field")
    table.add_column("Value")
    for key, value in device.to_dict().items():
        table.add_row(str(key), json.dumps(value) if isinstance(value, dict) else str(value))
    console.print(table)


@app.command("monitor")
def monitor_command(
    path: str,
    limit: int | None = typer.Option(None, "--limit", min=1, help="Stop after N events."),
    as_json: bool = typer.Option(False, "--json", help="Render events as JSON lines."),
) -> None:
    try:
        for event in iter_events(path, limit=limit):
            if as_json:
                console.print(json.dumps(event))
            else:
                console.print(
                    f"[{event['timestamp']:.06f}] type={event['type']} code={event['code']} value={event['value']} {event['description']}"
                )
    except PermissionError as exc:
        console.print(f"[red]Permission denied[/red] while opening {path}: {exc}")
        raise typer.Exit(code=1)
    except FileNotFoundError as exc:
        console.print(f"[red]Device not found[/red] for {path}: {exc}")
        raise typer.Exit(code=1)
    except KeyboardInterrupt:
        raise typer.Exit(code=130)


@app.command("report")
def report_command(as_json: bool = typer.Option(False, "--json", help="Render report as JSON.")) -> None:
    report = build_report()
    if as_json:
        _print_json(report)
        return
    console.print_json(json.dumps(report, indent=2))


@app.command("export-report")
def export_report_command(as_json: bool = typer.Option(False, "--json", help="Render report as JSON.")) -> None:
    report_command(as_json=as_json)


@app.command("install-udev")
def install_udev_command() -> None:
    try:
        console.print(install_bundled_rule())
    except PermissionError:
        console.print(install_instructions())
        raise typer.Exit(code=1)


@sdl_app.command("validate")
def sdl_validate_command(
    path: Path = typer.Option(Path("mappings/sdl2/gamecontrollerdb.txt"), "--path", help="Mapping file to validate."),
    as_json: bool = typer.Option(False, "--json", help="Render warnings as JSON."),
) -> None:
    warnings = validate_mapping_file(path)
    if as_json:
        _print_json({"path": str(path), "warnings": warnings})
        return
    if warnings:
        for warning in warnings:
            console.print(f"[yellow]warning:[/yellow] {warning}")
        raise typer.Exit(code=1)
    console.print("SDL mapping file looks good")


@udev_app.command("path")
def udev_path_command() -> None:
    status = get_rule_status()
    console.print(str(status.bundled_path))


@udev_app.command("install-instructions")
def udev_install_instructions_command() -> None:
    console.print(install_instructions())


if __name__ == "__main__":
    app()
