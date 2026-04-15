"""Unit tests for the validators module — magic bytes, hex parsing, clamping."""

from __future__ import annotations

import pytest

from watermark_api.validators import (
    InvalidColorError,
    UnsupportedImageError,
    clamp,
    parse_hex_color,
    sniff_image,
)


def test_sniff_jpeg(jpeg_image: bytes) -> None:
    kind = sniff_image(jpeg_image)
    assert kind.pil_format == "JPEG"
    assert kind.mime == "image/jpeg"


def test_sniff_png(png_image: bytes) -> None:
    kind = sniff_image(png_image)
    assert kind.pil_format == "PNG"


def test_sniff_webp(webp_image: bytes) -> None:
    kind = sniff_image(webp_image)
    assert kind.pil_format == "WEBP"


def test_sniff_rejects_text() -> None:
    with pytest.raises(UnsupportedImageError):
        sniff_image(b"this is definitely not an image, it's just text padding")


def test_sniff_rejects_short() -> None:
    with pytest.raises(UnsupportedImageError):
        sniff_image(b"short")


def test_parse_hex_valid() -> None:
    assert parse_hex_color("#ffffff") == (255, 255, 255)
    assert parse_hex_color("#000000") == (0, 0, 0)
    assert parse_hex_color("#8040C0") == (128, 64, 192)


def test_parse_hex_missing_hash() -> None:
    with pytest.raises(InvalidColorError):
        parse_hex_color("ffffff")


def test_parse_hex_wrong_length() -> None:
    with pytest.raises(InvalidColorError):
        parse_hex_color("#fff")


def test_parse_hex_non_hex_chars() -> None:
    with pytest.raises(InvalidColorError):
        parse_hex_color("#zzzzzz")


def test_clamp_basic() -> None:
    assert clamp(5, 0, 10) == 5
    assert clamp(-1, 0, 10) == 0
    assert clamp(99, 0, 10) == 10
    assert clamp(0.5, 0.0, 1.0) == 0.5
