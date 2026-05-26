"""Interactive input testing helpers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
import os
import select
import time
from typing import Any

from evdev import InputDevice, ecodes
from rich.live import Live
from rich.table import Table

from .devices import ControllerInfo, get_device_by_path, list_detected_controllers

RECENT_EVENT_LIMIT = 12


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
    initial_value: int | None = None
    last_value: int | None = None
    min_seen: int | None = None
    max_seen: int | None = None
    moved: bool = False
    raw_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class InteractiveTestResult:
    path: str
    device_name: str
    states: list[ObservedInputState]
    unexpected_events: list[str] = field(default_factory=list)
    recent_events: list[str] = field(default_factory=list)
    mode_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "device_name": self.device_name,
            "states": [state.to_dict() for state in self.states],
            "unexpected_events": self.unexpected_events,
            "recent_events": self.recent_events,
            "mode_notes": self.mode_notes,
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
    ExpectedInput("L3", "button", ("BTN_THUMBL",)),
    ExpectedInput("R3", "button", ("BTN_THUMBR",)),
    ExpectedInput("Start", "button", ("BTN_START",)),
    ExpectedInput("Select", "button", ("BTN_SELECT",)),
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

GUIDED_SEQUENCE: tuple[str, ...] = (
    "A",
    "B",
    "X",
    "Y",
    "LB",
    "RB",
    "LT",
    "RT",
    "LX",
    "LY",
    "RX",
    "RY",
    "L3",
    "R3",
    "Start",
    "Select",
    "Home",
    "DPad",
    "Back buttons",
    "Gyro",
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


def _mode_notes(controller: ControllerInfo | None, input_device: InputDevice) -> list[str]:
    notes: list[str] = []
    merged = get_device_by_path(input_device.path)
    if merged and merged.driver == "xpad":
        notes.append(
            "Device is handled by xpad as an Xbox-compatible pad. Vendor-specific 8BitDo controls may not be exposed through evdev in this mode."
        )
    elif input_device.name == "Generic X-Box pad":
        notes.append(
            "Device reports as Generic X-Box pad. This usually means Xbox/XInput compatibility mode, not that the hardware is actually an Xbox controller."
        )
    if controller and controller.hidraw_path:
        notes.append(f"hidraw is available at {controller.hidraw_path}; vendor-specific controls may require HID-level investigation.")
    return notes


def resolve_test_device(path: str | None) -> tuple[str, ControllerInfo | None]:
    controllers = list_detected_controllers()
    if path is not None:
        controller = next((item for item in controllers if item.evdev_path == path), None)
        return path, controller
    controller = next((item for item in controllers if item.evdev_path and item.evdev_readable is not False), None)
    if controller is None or controller.evdev_path is None:
        raise RuntimeError("No readable 8BitDo evdev device found. Run `ultim8do list` or pass `--path /dev/input/eventX`.")
    return controller.evdev_path, controller


def _axis_threshold(state: ObservedInputState) -> int:
    if state.minimum is None or state.maximum is None:
        return 1
    span = abs(state.maximum - state.minimum)
    if state.kind == "trigger":
        return max(1, span // 20)
    return max(512, span // 10)


def _track_motion(state: ObservedInputState, value: int) -> None:
    state.last_value = value
    state.value = value
    state.min_seen = value if state.min_seen is None else min(state.min_seen, value)
    state.max_seen = value if state.max_seen is None else max(state.max_seen, value)
    baseline = state.initial_value if state.initial_value is not None else value
    if state.kind == "hat":
        if value != 0:
            state.moved = True
        return
    if abs(value - baseline) >= _axis_threshold(state):
        state.moved = True


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
                    state.initial_value = info.value
                    state.last_value = info.value
                    state.value = info.value
                    state.minimum = info.min
                    state.maximum = info.max
                    state.min_seen = info.value
                    state.max_seen = info.value
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
                    state.initial_value = info.value
                    state.last_value = info.value
                    state.value = info.value
                    state.minimum = info.min
                    state.maximum = info.max
                    state.min_seen = info.value
                    state.max_seen = info.value
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
                else:
                    _append_note(state.notes, "not exposed through evdev in this mode")
        states[spec.label] = state
    return states


def _record_recent_event(recent_events: list[str], event: Any) -> None:
    aliases = _aliases(event.type, event.code)
    rendered = f"{ecodes.EV.get(event.type, event.type)} {aliases[0]} value={event.value}"
    recent_events.append(rendered)
    if len(recent_events) > RECENT_EVENT_LIMIT:
        del recent_events[0]


def update_states_from_event(
    states: dict[str, ObservedInputState],
    event: Any,
    unexpected_events: list[str],
    recent_events: list[str] | None = None,
) -> None:
    aliases = _aliases(event.type, event.code)
    if recent_events is not None and event.type in {ecodes.EV_KEY, ecodes.EV_ABS}:
        _record_recent_event(recent_events, event)
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
                _track_motion(state, int(event.value))
                if state.moved:
                    state.activated = True
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
                _track_motion(state, int(event.value))
                if state.moved:
                    state.activated = True
        elif state.kind == "hat":
            if any(alias in state.expected_codes for alias in aliases):
                matched = True
                state.status = "hat"
                _track_motion(state, int(event.value))
                if state.moved:
                    state.activated = True
    if not matched and event.type in {ecodes.EV_KEY, ecodes.EV_ABS}:
        rendered = f"{ecodes.EV.get(event.type, event.type)} {aliases[0]} value={event.value}"
        if rendered not in unexpected_events:
            unexpected_events.append(rendered)


def _render_state(state: ObservedInputState) -> tuple[str, str]:
    if state.kind in {"button", "feature"}:
        if state.status == "ok":
            return "OK", state.code or ""
        if state.status == "present":
            return "present", state.code or ""
        return state.status, state.code or ""
    if state.kind == "trigger":
        if state.status == "axis":
            return "OK" if state.moved else "axis", _render_axis_details(state)
        if state.status == "button":
            return "OK" if state.activated else "button", state.code or ""
        return state.status, state.code or ""
    if state.kind == "axis":
        return ("OK" if state.moved else (state.code or state.status), _render_axis_details(state))
    if state.kind == "hat":
        details = state.code or state.status
        if state.value is not None:
            details = f"{details} value {state.value}"
        return ("OK" if state.moved else "hat", details)
    return state.status, state.code or ""


def _render_axis_details(state: ObservedInputState) -> str:
    parts = [state.code or ""]
    if state.minimum is not None and state.maximum is not None:
        parts.append(f"range {state.minimum}..{state.maximum}")
    if state.last_value is not None:
        waiting = " waiting" if not state.moved else ""
        parts.append(f"value {state.last_value}{waiting}")
    return " ".join(part for part in parts if part)


def render_test_table(
    device_name: str,
    states: dict[str, ObservedInputState],
    unexpected_events: list[str],
    recent_events: list[str],
    mode_notes: Iterable[str],
    raw: bool,
    guided_label: str | None = None,
) -> Table:
    title = "Press buttons on your controller..."
    if guided_label:
        title = f"Press {guided_label} now..."
    table = Table(title=title)
    table.caption = device_name
    table.add_column("Input")
    table.add_column("Status")
    table.add_column("Details")
    table.add_column("Notes")
    for state in states.values():
        status, details = _render_state(state)
        table.add_row(state.label, status, details, "; ".join(state.notes))
    for note in mode_notes:
        table.add_row("Mode", "note", note, "")
    if raw and recent_events:
        table.add_row("Recent events", "observed", recent_events[-1], "use --guided for one control at a time")
    if unexpected_events:
        table.add_row("Unexpected", "observed", unexpected_events[-1], "possible mis-mapped control")
    return table


def _wait_for_events(device: InputDevice, timeout: float) -> list[Any]:
    ready, _, _ = select.select([device.fd], [], [], timeout)
    if not ready:
        return []
    return list(device.read())


def _run_guided_test(
    device: InputDevice,
    states: dict[str, ObservedInputState],
    unexpected_events: list[str],
    recent_events: list[str],
    mode_notes: list[str],
    raw: bool,
    prompt_timeout: float,
    render_live: bool,
) -> None:
    state_sequence = [states[label] for label in GUIDED_SEQUENCE if label in states]
    live_context = Live(refresh_per_second=10) if render_live else None
    if live_context:
        live_context.start()
    try:
        for state in state_sequence:
            state.raw_status = "waiting"
            if live_context:
                live_context.update(
                    render_test_table(device.name or device.path, states, unexpected_events, recent_events, mode_notes, raw, guided_label=state.label)
                )
            deadline = time.monotonic() + prompt_timeout
            matched = False
            mismatched = False
            while time.monotonic() < deadline:
                events = _wait_for_events(device, min(0.1, max(0.0, deadline - time.monotonic())))
                if not events:
                    continue
                for event in events:
                    before_status = state.status
                    before_activated = state.activated
                    update_states_from_event(states, event, unexpected_events, recent_events if raw else None)
                    if state.status != before_status or state.activated != before_activated:
                        matched = True
                        break
                    if event.type in {ecodes.EV_KEY, ecodes.EV_ABS} and (raw or unexpected_events):
                        mismatched = True
                if live_context:
                    live_context.update(
                        render_test_table(device.name or device.path, states, unexpected_events, recent_events, mode_notes, raw, guided_label=state.label)
                    )
                if matched:
                    break
            if matched:
                state.raw_status = "ok"
            elif mismatched:
                state.raw_status = "mis-mapped"
                _append_note(state.notes, "control produced a different event than expected")
            else:
                state.raw_status = "missing"
                _append_note(state.notes, "not exposed through evdev in this mode")
    finally:
        if live_context:
            live_context.stop()


def run_interactive_test(
    path: str,
    controller: ControllerInfo | None,
    duration: float | None = None,
    render_live: bool = True,
    raw: bool = False,
    guided: bool = False,
    prompt_timeout: float = 3.0,
) -> InteractiveTestResult:
    device = InputDevice(path)
    states = build_initial_states(device, controller)
    unexpected_events: list[str] = []
    recent_events: list[str] = []
    mode_notes = _mode_notes(controller, device)
    start = time.monotonic()
    device_name = device.name or path
    try:
        os.set_blocking(device.fd, False)
        if guided:
            _run_guided_test(device, states, unexpected_events, recent_events, mode_notes, raw, prompt_timeout, render_live)
        elif render_live:
            with Live(render_test_table(device_name, states, unexpected_events, recent_events, mode_notes, raw), refresh_per_second=10) as live:
                while True:
                    if duration is not None and time.monotonic() - start >= duration:
                        break
                    for event in _wait_for_events(device, 0.1):
                        update_states_from_event(states, event, unexpected_events, recent_events if raw else None)
                    live.update(render_test_table(device_name, states, unexpected_events, recent_events, mode_notes, raw))
        else:
            while True:
                if duration is not None and time.monotonic() - start >= duration:
                    break
                events = _wait_for_events(device, 0.1)
                if events:
                    for event in events:
                        update_states_from_event(states, event, unexpected_events, recent_events if raw else None)
                elif duration is None:
                    continue
    finally:
        device.close()
    return InteractiveTestResult(
        path=path,
        device_name=device_name,
        states=list(states.values()),
        unexpected_events=unexpected_events,
        recent_events=recent_events,
        mode_notes=mode_notes,
    )
