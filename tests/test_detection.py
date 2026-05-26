from ultim8do.constants import EIGHTBITDO_VENDOR_ID
from ultim8do.devices import (
    ControllerInfo,
    InputDeviceInfo,
    classify_capability_tests,
    detection_reasons_for_device,
    is_supported_vendor_id,
    looks_like_8bitdo_controller,
    normalize_hex_identifier,
)


def test_normalize_hex_identifier_accepts_prefixed_string() -> None:
    assert normalize_hex_identifier("0x2dc8") == EIGHTBITDO_VENDOR_ID


def test_normalize_hex_identifier_accepts_plain_string() -> None:
    assert normalize_hex_identifier("2dc8") == EIGHTBITDO_VENDOR_ID


def test_supported_vendor_id_matches_8bitdo() -> None:
    assert is_supported_vendor_id(EIGHTBITDO_VENDOR_ID)
    assert not is_supported_vendor_id(0x045E)


def test_detection_reasons_include_name_and_vendor() -> None:
    info = InputDeviceInfo(
        path="/dev/input/event99",
        name="8BitDo Ultimate Controller",
        vendor_id=EIGHTBITDO_VENDOR_ID,
        product_id=0x1234,
    )

    assert detection_reasons_for_device(info) == ["name", "vendor_id"]
    assert looks_like_8bitdo_controller(info) is True


def test_detection_reasons_include_gamepad_capabilities_when_other_signal_exists() -> None:
    info = InputDeviceInfo(
        path="/dev/input/event99",
        name="Generic Gamepad",
        vendor_id=EIGHTBITDO_VENDOR_ID,
        capabilities={
            "EV_KEY": ["BTN_SOUTH", "BTN_EAST"],
            "EV_ABS": ["ABS_X", "ABS_Y", "ABS_Z", "ABS_RZ"],
            "EV_FF": ["FF_RUMBLE"],
        },
    )

    assert detection_reasons_for_device(info) == ["vendor_id", "gamepad_capabilities"]


def test_input_device_info_dict_includes_8bitdo_flag() -> None:
    info = InputDeviceInfo(
        path="/dev/input/event99",
        name="8BitDo Ultimate Controller",
        vendor_id=EIGHTBITDO_VENDOR_ID,
        product_id=0x1234,
    )

    payload = info.to_dict()

    assert payload["is_8bitdo"] is True
    assert payload["vendor_id"] == EIGHTBITDO_VENDOR_ID
    assert payload["detection_reasons"] == ["name", "vendor_id"]


def test_classify_capability_tests_covers_expected_fields() -> None:
    tests = classify_capability_tests(
        {
            "EV_KEY": ["BTN_SOUTH", "BTN_EAST", "BTN_TRIGGER_HAPPY1"],
            "EV_ABS": ["ABS_X", "ABS_Y", "ABS_Z"],
            "EV_FF": ["FF_RUMBLE"],
        }
    )

    assert tests == {
        "buttons": "detected",
        "axes": "detected",
        "triggers": "partial",
        "rumble": "detected",
        "gyro": "missing",
        "back_buttons": "detected",
    }


def test_controller_info_to_dict_exposes_paths_transport_and_permissions() -> None:
    controller = ControllerInfo(
        name="8BitDo Ultimate 3mode Xbox",
        transport="USB",
        vendor_id=EIGHTBITDO_VENDOR_ID,
        product_id=0x2030,
        evdev_path="/dev/input/event17",
        joystick_path="/dev/input/js0",
        hidraw_path="/dev/hidraw4",
        evdev_readable=True,
        joystick_readable=True,
        hidraw_readable=False,
        tests={"buttons": "detected"},
    )

    payload = controller.to_dict()

    assert payload["transport"] == "USB"
    assert payload["evdev_path"] == "/dev/input/event17"
    assert payload["joystick_path"] == "/dev/input/js0"
    assert payload["hidraw_readable"] is False
