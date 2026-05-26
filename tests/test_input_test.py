from __future__ import annotations

from types import SimpleNamespace

from ultim8do.devices import ControllerInfo
from ultim8do.input_test import build_initial_states, update_states_from_event


class FakeDevice:
    def __init__(self, capabilities: dict[int, list[object]], name: str = "Fake Pad") -> None:
        self._capabilities = capabilities
        self.name = name

    def capabilities(self, absinfo: bool = False) -> dict[int, list[object]]:
        assert absinfo is True
        return self._capabilities


def _absinfo(value: int, minimum: int, maximum: int) -> SimpleNamespace:
    return SimpleNamespace(value=value, min=minimum, max=maximum)


def test_build_initial_states_detects_complete_xbox_like_mapping() -> None:
    device = FakeDevice(
        {
            1: [304, 305, 307, 308, 310, 311, 316],
            3: [
                (0, _absinfo(0, -32768, 32767)),
                (1, _absinfo(0, -32768, 32767)),
                (2, _absinfo(0, 0, 255)),
                (3, _absinfo(0, -32768, 32767)),
                (4, _absinfo(0, -32768, 32767)),
                (5, _absinfo(0, 0, 255)),
                (16, _absinfo(0, -1, 1)),
                (17, _absinfo(0, -1, 1)),
            ],
        }
    )

    states = build_initial_states(device)

    assert states["A"].status == "present"
    assert states["LT"].status == "axis"
    assert states["LT"].code == "ABS_Z"
    assert states["LX"].code == "ABS_X"
    assert states["DPad"].status == "hat"
    assert states["Home"].status == "present"


def test_build_initial_states_detects_trigger_exposed_as_button() -> None:
    device = FakeDevice({1: [312], 3: []})

    states = build_initial_states(device)

    assert states["LT"].status == "button"
    assert states["LT"].code == "BTN_TL2"
    assert "trigger exposed as button" in states["LT"].notes


def test_build_initial_states_marks_home_missing() -> None:
    device = FakeDevice({1: [304], 3: []})

    states = build_initial_states(device)

    assert states["Home"].status == "missing"


def test_build_initial_states_marks_hidraw_note_for_missing_feature() -> None:
    controller = ControllerInfo(name="Pad", transport="USB", hidraw_path="/dev/hidraw4")
    device = FakeDevice({1: [304], 3: []})

    states = build_initial_states(device, controller)

    assert "missing from evdev; hidraw available" in states["Back buttons"].notes


def test_update_states_from_button_event_marks_button_ok() -> None:
    device = FakeDevice({1: [304], 3: []})
    states = build_initial_states(device)
    unexpected: list[str] = []
    event = SimpleNamespace(type=1, code=304, value=1)

    update_states_from_event(states, event, unexpected)

    assert states["A"].status == "ok"
    assert states["A"].activated is True


def test_update_states_from_axis_event_updates_value() -> None:
    device = FakeDevice({1: [], 3: [(0, _absinfo(0, -32768, 32767))]})
    states = build_initial_states(device)
    unexpected: list[str] = []
    event = SimpleNamespace(type=3, code=0, value=123)

    update_states_from_event(states, event, unexpected)

    assert states["LX"].value == 123


def test_update_states_from_unexpected_event_records_possible_mismap() -> None:
    device = FakeDevice({1: [304], 3: []})
    states = build_initial_states(device)
    unexpected: list[str] = []
    event = SimpleNamespace(type=1, code=314, value=1)

    update_states_from_event(states, event, unexpected)

    assert unexpected == ["EV_KEY BTN_SELECT value=1"]
