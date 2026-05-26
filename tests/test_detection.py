from ultim8do.constants import EIGHTBITDO_VENDOR_ID
from ultim8do.devices import InputDeviceInfo, is_supported_vendor_id, normalize_hex_identifier


def test_normalize_hex_identifier_accepts_prefixed_string() -> None:
    assert normalize_hex_identifier("0x2dc8") == EIGHTBITDO_VENDOR_ID


def test_normalize_hex_identifier_accepts_plain_string() -> None:
    assert normalize_hex_identifier("2dc8") == EIGHTBITDO_VENDOR_ID


def test_supported_vendor_id_matches_8bitdo() -> None:
    assert is_supported_vendor_id(EIGHTBITDO_VENDOR_ID)
    assert not is_supported_vendor_id(0x045E)


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
