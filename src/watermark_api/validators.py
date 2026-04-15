"""Input validation: magic-byte content-type check, hex color parsing, clamping.

These helpers are deliberately free of FastAPI / HTTP concerns so the watermark
module and tests can reuse them without pulling Starlette.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


class UnsupportedImageError(ValueError):
    """Raised when a payload does not look like JPEG, PNG, or WebP."""


class InvalidColorError(ValueError):
    """Raised when a hex color string is malformed."""


@dataclass(frozen=True)
class ImageKind:
    name: str         # "JPEG", "PNG", "WEBP"
    mime: str         # "image/jpeg", ...
    pil_format: str   # Value for Image.save(format=...)


JPEG = ImageKind("JPEG", "image/jpeg", "JPEG")
PNG = ImageKind("PNG", "image/png", "PNG")
WEBP = ImageKind("WEBP", "image/webp", "WEBP")


def sniff_image(data: bytes) -> ImageKind:
    """Return the detected image kind or raise UnsupportedImageError.

    Checks magic bytes only. The client-reported MIME is never trusted.
    """
    if len(data) < 12:
        raise UnsupportedImageError("payload too short to be an image")

    # JPEG: FF D8 FF
    if data[:3] == b"\xff\xd8\xff":
        return JPEG
    # PNG: 89 50 4E 47 0D 0A 1A 0A
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return PNG
    # WebP: RIFF <size> WEBP
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return WEBP

    raise UnsupportedImageError(
        "payload does not match JPEG, PNG, or WebP magic bytes"
    )


def parse_hex_color(value: str) -> Tuple[int, int, int]:
    """Parse a ``#RRGGBB`` string into an RGB tuple.

    Raises InvalidColorError on malformed input. We accept the 7-character
    form with the leading ``#`` only — no 3-digit shorthand, no alpha channel
    (alpha is a separate ``opacity`` parameter on the API).
    """
    if not isinstance(value, str):
        raise InvalidColorError("color must be a string")
    if len(value) != 7 or value[0] != "#":
        raise InvalidColorError("color must be in #RRGGBB form")
    try:
        r = int(value[1:3], 16)
        g = int(value[3:5], 16)
        b = int(value[5:7], 16)
    except ValueError as exc:
        raise InvalidColorError(f"color has non-hex characters: {exc}") from exc
    return (r, g, b)


def clamp(value: float, lo: float, hi: float) -> float:
    """Clamp a numeric value into ``[lo, hi]``."""
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value
