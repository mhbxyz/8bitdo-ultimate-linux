from pathlib import Path

from ultim8do.sdl import load_mappings, parse_mapping_line, validate_mapping_file


def test_parse_mapping_line_extracts_platform() -> None:
    mapping = parse_mapping_line(
        "03000000c82d00000100000000000000,8BitDo Ultimate Controller,a:b0,b:b1,platform:Linux,"
    )

    assert mapping is not None
    assert mapping.platform == "Linux"
    assert mapping.name == "8BitDo Ultimate Controller"


def test_load_mappings_reads_fixture() -> None:
    fixture = Path("tests/fixtures/sample_gamecontrollerdb.txt")
    mappings = load_mappings(fixture)

    assert len(mappings) == 1
    assert mappings[0].guid == "03000000c82d00000100000000000000"


def test_validate_mapping_file_reports_missing_platform(tmp_path: Path) -> None:
    mapping_file = tmp_path / "gamecontrollerdb.txt"
    mapping_file.write_text(
        "03000000c82d00000100000000000000,8BitDo Ultimate Controller,a:b0,b:b1,\n",
        encoding="utf-8",
    )

    warnings = validate_mapping_file(mapping_file)

    assert warnings == ["Line 1: missing platform field"]
