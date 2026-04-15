"""Test fixtures.

We generate small test images in memory per session: a red 400x300 JPEG, a
green 200x150 PNG with an alpha channel, and a blue 300x200 WebP. No binary
files are committed; everything here is Pillow-on-the-fly.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image


def _jpeg_bytes(width: int = 400, height: int = 300) -> bytes:
    img = Image.new("RGB", (width, height), (200, 30, 30))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _png_bytes(width: int = 200, height: int = 150) -> bytes:
    img = Image.new("RGBA", (width, height), (30, 200, 30, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _webp_bytes(width: int = 300, height: int = 200) -> bytes:
    img = Image.new("RGB", (width, height), (30, 30, 200))
    buf = io.BytesIO()
    img.save(buf, format="WEBP", lossless=True)
    return buf.getvalue()


def _overlay_png_bytes(width: int = 60, height: int = 60) -> bytes:
    """A small PNG with a translucent yellow square in the middle."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for x in range(10, width - 10):
        for y in range(10, height - 10):
            img.putpixel((x, y), (255, 220, 0, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture()
def jpeg_image() -> bytes:
    return _jpeg_bytes()


@pytest.fixture()
def png_image() -> bytes:
    return _png_bytes()


@pytest.fixture()
def webp_image() -> bytes:
    return _webp_bytes()


@pytest.fixture()
def overlay_png() -> bytes:
    return _overlay_png_bytes()
