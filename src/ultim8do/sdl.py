"""SDL mapping helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .constants import SDL_DB_PATH


@dataclass(slots=True)
class SDLMapping:
    guid: str
    name: str
    fields: list[str]
    platform: str | None = None

    def to_dict(self) -> dict[str, str | list[str] | None]:
        return {
            "guid": self.guid,
            "name": self.name,
            "fields": self.fields,
            "platform": self.platform,
        }


def parse_mapping_line(line: str) -> SDLMapping | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    parts = [part.strip() for part in stripped.split(",")]
    if len(parts) < 3:
        raise ValueError(f"Invalid SDL mapping line: {line}")
    guid, name, *fields = parts
    platform = None
    for field in fields:
        if field.startswith("platform:"):
            platform = field.split(":", 1)[1]
    return SDLMapping(guid=guid, name=name, fields=fields, platform=platform)


def load_mappings(path: Path = SDL_DB_PATH) -> list[SDLMapping]:
    mappings: list[SDLMapping] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        mapping = parse_mapping_line(line)
        if mapping is not None:
            mappings.append(mapping)
    return mappings


def validate_mapping_file(path: Path = SDL_DB_PATH) -> list[str]:
    warnings: list[str] = []
    seen_guids: set[str] = set()
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        mapping = parse_mapping_line(line)
        if mapping is None:
            continue
        if mapping.guid in seen_guids:
            warnings.append(f"Line {index}: duplicate GUID {mapping.guid}")
        else:
            seen_guids.add(mapping.guid)
        if not mapping.platform:
            warnings.append(f"Line {index}: missing platform field")
    if not seen_guids:
        warnings.append("No SDL mappings defined yet")
    return warnings
