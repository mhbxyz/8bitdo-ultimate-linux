"""CLI entrypoint for ultim8do."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .devices import get_device_by_path, list_candidate_devices
from .doctor import run_doctor
from .evdev_reader import iter_events
from .report import build_report
from .sdl import validate_mapping_file
from .udev import get_rule_status, install_instructions

app = typer.Typer(help="Inspect and validate 8BitDo Ultimate controllers on Linux.")
sdl_app = typer.Typer(help="SDL mapping helpers.")
udev_app = typer.Typer(help="udev helpers.")
app.add_typer(sdl_app, name="sdl")
app.add_typer(udev_app, name="udev")

console = Console()


def _print_json(payload: object) -> None:
    console.print_json(json.dumps(payload, indent=2))


@app.command("doctor")
def doctor_command(as_json: bool = typer.Option(False, "--json", help="Render checks as JSON.")) -> None:
    result = run_doctor()
    if as_json:
        _print_json(result.to_dict())
        return

    table = Table(title="ultim8do doctor")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Details")
    for check in result.checks:
        table.add_row(check.name, "ok" if check.ok else "warn", check.details)
    console.print(table)
    raise typer.Exit(code=0 if result.ok else 1)


@app.command("list")
def list_command(
    as_json: bool = typer.Option(False, "--json", help="Render devices as JSON."),
    verbose: bool = typer.Option(False, "--verbose", help="Show raw properties when available."),
) -> None:
    devices = list_candidate_devices()
    if as_json:
        _print_json([device.to_dict() for device in devices])
        return
    table = Table(title="Candidate devices")
    table.add_column("Path")
    table.add_column("Name")
    table.add_column("Vendor")
    table.add_column("Product")
    for device in devices:
        vendor = f"0x{device.vendor_id:04x}" if device.vendor_id is not None else "-"
        product = f"0x{device.product_id:04x}" if device.product_id is not None else "-"
        table.add_row(device.path, device.name, vendor, product)
        if verbose and device.properties:
            table.add_row("", json.dumps(device.properties, sort_keys=True), "", "")
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
