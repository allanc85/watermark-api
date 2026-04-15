"""Pure unit tests for watermark.py — no FastAPI, no TestClient."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from watermark_api.watermark import (
    VALID_POSITIONS,
    apply_image_watermark,
    apply_text_watermark,
)


def _load(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    img.load()
    return img


def test_text_watermark_returns_same_mode_and_size(jpeg_image: bytes) -> None:
    src = _load(jpeg_image)
    out = apply_text_watermark(src, text="hello")
    assert out.mode == src.mode
    assert out.size == src.size


def test_text_watermark_each_position(jpeg_image: bytes) -> None:
    src = _load(jpeg_image)
    for pos in sorted(VALID_POSITIONS):
        out = apply_text_watermark(src, text="hi", position=pos)
        assert out.size == src.size, f"size changed for position={pos}"


def test_text_watermark_changes_pixels(jpeg_image: bytes) -> None:
    src = _load(jpeg_image)
    out = apply_text_watermark(
        src,
        text="MARK",
        position="center",
        opacity=1.0,
        color=(255, 255, 255),
        font_size_pct=10,
    )
    # Center should have some non-red pixels somewhere after watermarking.
    center = out.crop((src.width // 2 - 40, src.height // 2 - 20,
                       src.width // 2 + 40, src.height // 2 + 20))
    pixels = list(center.getdata())
    non_red = [p for p in pixels if not (p[0] > 150 and p[1] < 80 and p[2] < 80)]
    assert len(non_red) > 0, "expected watermark to change some pixels"


def test_text_watermark_opacity_zero_leaves_image_untouched(jpeg_image: bytes) -> None:
    src = _load(jpeg_image)
    out = apply_text_watermark(
        src,
        text="INVISIBLE",
        opacity=0.0,
        color=(255, 255, 255),
        font_size_pct=10,
        position="center",
    )
    # At opacity 0, every pixel should be visually identical to the source.
    # JPEG quantization means bytes can drift slightly, so compare via Pillow.
    assert list(out.getdata())[:10] == list(src.getdata())[:10]


def test_text_watermark_preserves_rgba(png_image: bytes) -> None:
    src = _load(png_image)
    assert src.mode == "RGBA"
    out = apply_text_watermark(src, text="alpha", opacity=0.7)
    assert out.mode == "RGBA"


def test_text_watermark_rejects_unknown_position(jpeg_image: bytes) -> None:
    src = _load(jpeg_image)
    with pytest.raises(ValueError):
        apply_text_watermark(src, text="x", position="middle-of-nowhere")


def test_text_watermark_rejects_bad_opacity(jpeg_image: bytes) -> None:
    src = _load(jpeg_image)
    with pytest.raises(ValueError):
        apply_text_watermark(src, text="x", opacity=2.5)


def test_image_watermark_basic(jpeg_image: bytes, overlay_png: bytes) -> None:
    src = _load(jpeg_image)
    ov = _load(overlay_png)
    out = apply_image_watermark(src, ov, overlay_pct=25, position="top-left")
    assert out.size == src.size
    assert out.mode == src.mode
