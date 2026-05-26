"""Future virtual controller support."""

from __future__ import annotations


class VirtualPadUnavailable(RuntimeError):
    """Raised when virtual pad features are not implemented."""


def ensure_virtual_pad_available() -> None:
    raise VirtualPadUnavailable(
        "Virtual pad emulation is intentionally not implemented yet. "
        "This project currently focuses on inspection and diagnostics."
    )
