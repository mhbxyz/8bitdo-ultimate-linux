"""Interactive input testing helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import os
import select
import time
from typing import Any

from evdev import InputDevice, ecodes
from rich.live import Live
from rich.table import Table

from .devices import ControllerInfo, list_detected_controllers


@dataclass(frozen=True, slots=True)
class ExpectedInput:
    label: str
    kind: str
    expected_codes: tuple[str, ...]
    fallback_button_codes: tuple[str, ...] = ()
    required: bool = True


@dataclass(slots=True)
class ObservedInputState:
    label: str
    kind: str
    expected_codes: tuple[str, ...]
    fallback_button_codes: tuple[str, ...] = ()
    status: str = "missing"
    code: str | None = None
    value: int | None = None
    minimum: int | None = None
    maximum: int | None = None
    notes: list[str] = field(default_factory=list)
    activated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class InteractiveTestResult:
    path: str
    device_name: str
    states: list[ObservedInputState]
    unexpected_events: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "device_name": self.device_name,
            "states": [state.to_dict() for state in self.states],
            "unexpected_events": self.unexpected_events,
        }


EXPECTED_GAMEPAD_INPUTS: tuple[ExpectedInput, ...] = (
    ExpectedInput("A", "button", ("BTN_SOUTH", "BTN_A")),
    ExpectedInput("B", "button", ("BTN_EAST", "BTN_B")),
    ExpectedInput("X", "button", ("BTN_NORTH", "BTN_X")),
    ExpectedInput("Y", "button", ("BTN_WEST", "BTN_Y")),
    ExpectedInput("LB", "button", ("BTN_TL",)),
    ExpectedInput("RB", "button", ("BTN_TR",)),
    ExpectedInput("LT", "trigger", ("ABS_Z",), fallback_button_codes=("BTN_TL2",)),
    ExpectedInput("RT", "trigger", ("ABS_RZ",), fallback_button_codes=("BTN_TR2",)),
    ExpectedInput("LX", "axis", ("ABS_X",)),
    ExpectedInput("LY", "axis", ("ABS_Y",)),
    ExpectedInput("RX", "axis", ("ABS_RX",)),
    ExpectedInput("RY", "axis", ("ABS_RY",)),
    ExpectedInput("DPad", "hat", ("ABS_HAT0X", "ABS_HAT0Y")),
    ExpectedInput("Home", "button", ("BTN_MODE",)),
    ExpectedInput(
        "Back buttons",
        "feature",
        ("BTN_TRIGGER_HAPPY1", "BTN_TRIGGER_HAPPY2", "BTN_TRIGGER_HAPPY3", "BTN_TRIGGER_HAPPY4"),
        required=False,
    ),
    ExpectedInput(
        "Gyro",
        "feature",
        ("ABS_GYRO_X", "ABS_GYRO_Y", "ABS_GYRO_Z", "ABS_RZ_GYRO"),
        required=False,
    ),
)


def _aliases(event_type: int, code: int) -> tuple[str, ...]:
    type_map = ecodes.bytype.get(event_type, {})
    mapped = type_map.get(code, str(code)) if isinstance(type_map, dict) else str(code)
    if isinstance(mapped, tuple):
        return tuple(str(item) for item in mapped)
    return (str(mapped),)


def _append_note(notes: list[str], note: str) -> None:
    if note not in notes:
        notes.append(note)


def resolve_test_device(path: str | None) -> tuple[str, ControllerInfo | None]:
    controllers = list_detected_controllers()
    if path is not None:
        controller = next((item for item in controllers if item.evdev_path == path), None)
        return path, controller
    controller = next((item for item in controllers if item.evdev_path and item.evdev_readable is not False), None)
    if controller is None or controller.evdev_path is None:
        raise RuntimeError("No readable 8BitDo evdev device found. Run `ultim8do list` or pass `--path /dev/input/eventX`.")
    return controller.evdev_path, controller


def build_initial_states(device: InputDevice, controller: ControllerInfo | None = None) -> dict[str, ObservedInputState]:
    capabilities = device.capabilities(absinfo=True)
    key_names: set[str] = set()
    for code in capabilities.get(ecodes.EV_KEY, []):
        if isinstance(code, tuple):
            code = code[0]
        key_names.update(_aliases(ecodes.EV_KEY, int(code)))

    abs_info_by_name: dict[str, Any] = {}
    for entry in capabilities.get(ecodes.EV_ABS, []):
        code = entry[0] if isinstance(entry, tuple) else entry
        info = entry[1] if isinstance(entry, tuple) and len(entry) > 1 else None
        for alias in _aliases(ecodes.EV_ABS, int(code)):
            abs_info_by_name[alias] = info

    states: dict[str, ObservedInputState] = {}
    for spec in EXPECTED_GAMEPAD_INPUTS:
        state = ObservedInputState(
            label=spec.label,
            kind=spec.kind,
            expected_codes=spec.expected_codes,
            fallback_button_codes=spec.fallback_button_codes,
        )
        if spec.kind == "button":
            code = next((item for item in spec.expected_codes if item in key_names), None)
            if code:
                state.status = "present"
                state.code = code
            else:
                state.status = "missing"
        elif spec.kind == "trigger":
            axis_code = next((item for item in spec.expected_codes if item in abs_info_by_name), None)
            button_code = next((item for item in spec.fallback_button_codes if item in key_names), None)
            if axis_code:
                info = abs_info_by_name[axis_code]
                state.status = "axis"
                state.code = axis_code
                if info is not None:
                    state.value = info.value
                    state.minimum = info.min
                    state.maximum = info.max
            elif button_code:
                state.status = "button"
                state.code = button_code
                _append_note(state.notes, "trigger exposed as button")
            else:
                state.status = "missing"
        elif spec.kind == "axis":
            axis_code = next((item for item in spec.expected_codes if item in abs_info_by_name), None)
            if axis_code:
                info = abs_info_by_name[axis_code]
                state.status = "axis"
                state.code = axis_code
                if info is not None:
                    state.value = info.value
                    state.minimum = info.min
                    state.maximum = info.max
                    if axis_code in {"ABS_Y", "ABS_RY"} and info.value in {info.min, info.max}:
                        _append_note(state.notes, "possible inverted axis")
            else:
                state.status = "missing"
        elif spec.kind == "hat":
            present = [item for item in spec.expected_codes if item in abs_info_by_name]
            if len(present) == len(spec.expected_codes):
                state.status = "hat"
                state.code = "ABS_HAT0X/Y"
            elif present:
                state.status = "partial"
                state.code = "/".join(present)
            else:
                state.status = "missing"
        else:
            code = next((item for item in spec.expected_codes if item in key_names or item in abs_info_by_name), None)
            if code:
                state.status = "present"
                state.code = code
            else:
                state.status = "missing"
                if controller and controller.hidraw_path:
                    _append_note(state.notes, "missing from evdev; hidraw available")
        states[spec.label] = state
    return states


def update_states_from_event(
    states: dict[str, ObservedInputState], event: Any, unexpected_events: list[str]
) -> None:
    aliases = _aliases(event.type, event.code)
    matched = False
    for state in states.values():
        if state.kind in {"button", "feature"}:
            if any(alias in state.expected_codes for alias in aliases):
                matched = True
                if event.value:
                    state.activated = True
                    state.status = "ok"
                    state.value = int(event.value)
                    if state.code is None:
                        state.code = next(alias for alias in aliases if alias in state.expected_codes)
        elif state.kind == "trigger":
            if any(alias in state.expected_codes for alias in aliases):
                matched = True
                state.status = "axis"
                state.code = next(alias for alias in aliases if alias in state.expected_codes)
                state.value = int(event.value)
            elif any(alias in state.fallback_button_codes for alias in aliases):
                matched = True
                state.status = "button"
                state.code = next(alias for alias in aliases if alias in state.fallback_button_codes)
                if event.value:
                    state.activated = True
                    state.value = int(event.value)
                    _append_note(state.notes, "trigger exposed as button")
        elif state.kind == "axis":
            if any(alias in state.expected_codes for alias in aliases):
                matched = True
                state.status = "axis"
                state.code = next(alias for alias in aliases if alias in state.expected_codes)
                state.value = int(event.value)
        elif state.kind == "hat":
            if any(alias in state.expected_codes for alias in aliases):
                matched = True
                state.status = "hat"
                state.value = int(event.value)
    if not matched and event.type in {ecodes.EV_KEY, ecodes.EV_ABS}:
        rendered = f"{ecodes.EV.get(event.type, event.type)} {aliases[0]} value={event.value}"
        if rendered not in unexpected_events:
            unexpected_events.append(rendered)


def render_test_table(device_name: str, states: dict[str, ObservedInputState], unexpected_events: list[str]) -> Table:
    table = Table(title="Press buttons on your controller...")
    table.caption = device_name
    table.add_column("Input")
    table.add_column("Status")
    table.add_column("Details")
    table.add_column("Notes")
    for state in states.values():
        status, details = _render_state(state)
        table.add_row(state.label, status, details, "; ".join(state.notes))
    if unexpected_events:
        table.add_row("Unexpected", "observed", unexpected_events[-1], "possible mis-mapped control")
    return table


def _render_state(state: ObservedInputState) -> tuple[str, str]:
    if state.kind in {"button", "feature"}:
        if state.status == "ok":
            return "OK", state.code or ""
        if state.status == "present":
            return "present", state.code or ""
        return state.status, state.code or ""
    if state.kind == "trigger":
        if state.status == "axis":
            return "axis", _render_axis_details(state)
        if state.status == "button":
            return "button", state.code or ""
        return state.status, state.code or ""
    if state.kind == "axis":
        return state.code or state.status, _render_axis_range(state)
    if state.kind == "hat":
        return state.code or state.status, f"value {state.value}" if state.value is not None else ""
    return state.status, state.code or ""


def _render_axis_details(state: ObservedInputState) -> str:
    parts = [state.code or ""]
    range_text = _render_axis_range(state)
    if range_text:
        parts.append(range_text)
    if state.value is not None:
        parts.append(f"value {state.value}")
    return " ".join(part for part in parts if part)


def _render_axis_range(state: ObservedInputState) -> str:
    if state.minimum is None or state.maximum is None:
        return ""
    return f"range {state.minimum}..{state.maximum}"


def run_interactive_test(
    path: str,
    controller: ControllerInfo | None,
    duration: float | None = None,
    render_live: bool = True,
) -> InteractiveTestResult:
    device = InputDevice(path)
    states = build_initial_states(device, controller)
    unexpected_events: list[str] = []
    start = time.monotonic()
    device_name = device.name or path
    try:
        os.set_blocking(device.fd, False)
        if render_live:
            with Live(render_test_table(device_name, states, unexpected_events), refresh_per_second=10) as live:
                while True:
                    if duration is not None and time.monotonic() - start >= duration:
                        break
                    ready, _, _ = select.select([device.fd], [], [], 0.1)
                    if ready:
                        for event in device.read():
                            update_states_from_event(states, event, unexpected_events)
                        live.update(render_test_table(device_name, states, unexpected_events))
        else:
            while True:
                if duration is not None and time.monotonic() - start >= duration:
                    break
                ready, _, _ = select.select([device.fd], [], [], 0.1)
                if ready:
                    for event in device.read():
                        update_states_from_event(states, event, unexpected_events)
                elif duration is None:
                    continue
    finally:
        device.close()
    return InteractiveTestResult(
        path=path,
        device_name=device_name,
        states=list(states.values()),
        unexpected_events=unexpected_events,
    )
