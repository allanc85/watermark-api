"""Pure Pillow watermarking ops.

This module takes PIL ``Image`` objects and returns PIL ``Image`` objects. No
HTTP, no file IO, no FastAPI imports. The API layer handles bytes <-> Image
conversion so this module stays easy to test in isolation.

Two operations are exposed:

* :func:`apply_text_watermark` — draw a text string on top of the image using
  alpha compositing so opacity works on flat colors.
* :func:`apply_image_watermark` — composite an RGBA overlay PNG onto the image
  with a requested opacity and position.

Both return a new image in the same mode as the input (RGB for JPEG inputs,
RGBA for PNG with alpha). The caller is responsible for writing it back out
in the correct format.
"""

from __future__ import annotations

import os
from typing import Tuple

from PIL import Image, ImageDraw, ImageFont

Position = str  # "top-left", "top-right", "bottom-left", "bottom-right", "center"

VALID_POSITIONS = {
    "top-left",
    "top-right",
    "bottom-left",
    "bottom-right",
    "center",
    "upper-mid-center",
    "lower-mid-center",
}

# Ordered list of candidate TTF paths. The Dockerfile installs font-dejavu
# which puts DejaVuSans.ttf at the first path. When running on a dev laptop
# we also try a few common system locations before giving up and falling
# back to Pillow's embedded bitmap font (which ignores font size, but at
# least lets unit tests run without any TTF installed).
_FONT_CANDIDATES = (
    "/usr/share/fonts/ttf-liberation/LiberationSerif-Regular.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
)


def _load_font(pixel_size: int) -> ImageFont.ImageFont:
    """Load a TrueType font at the requested pixel size.

    Falls back to Pillow's embedded bitmap font if no TTF is available so
    watermark.py can still be imported and its non-text paths exercised on
    hosts with no fonts installed.
    """
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, pixel_size)
            except OSError:
                continue
    return ImageFont.load_default()


def _position_xy(
    canvas_size: Tuple[int, int],
    object_size: Tuple[int, int],
    position: Position,
    padding: int,
) -> Tuple[int, int]:
    """Compute the top-left (x, y) for an object given a position and padding.

    Everything is integer pixels. The caller is responsible for clamping
    ``padding`` to something sensible.
    """
    cw, ch = canvas_size
    ow, oh = object_size

    if position == "top-left":
        return (padding, padding)
    if position == "top-right":
        return (cw - ow - padding, padding)
    if position == "bottom-left":
        return (padding, ch - oh - padding)
    if position == "bottom-right":
        return (cw - ow - padding, ch - oh - padding)
    if position == "center":
        return ((cw - ow) // 2, (ch - oh) // 2)
    if position == "upper-mid-center":
        return ((cw - ow) // 2, (ch - oh) // 4)
    if position == "lower-mid-center":
        return ((cw - ow) // 2, (ch - oh) // 4 * 3)

    raise ValueError(f"unknown position: {position!r}")


def apply_text_watermark(
    image: Image.Image,
    *,
    text: str,
    position: Position = "bottom-right",
    opacity: float = 0.5,
    color: Tuple[int, int, int] = (255, 255, 255),
    font_size_pct: float = 3.0,
    padding_pct: float = 2.0,
) -> Image.Image:
    """Return a new image with ``text`` composited onto it.

    The work happens on an RGBA copy so opacity works by pre-multiplying it
    into the text's alpha channel, then the final image is converted back to
    the input mode. That matters because JPEG inputs must come out as RGB —
    JPEG has no alpha channel, so any RGBA result would have to be flattened
    against a background color anyway.
    """
    if position not in VALID_POSITIONS:
        raise ValueError(f"unknown position: {position!r}")
    if not (0.0 <= opacity <= 1.0):
        raise ValueError("opacity must be in [0, 1]")

    orig_mode = image.mode
    base = image.convert("RGBA")
    width, height = base.size

    pixel_size = max(8, int(height * font_size_pct / 100.0))
    padding = max(0, int(min(width, height) * padding_pct / 100.0))
    font = _load_font(pixel_size)

    # Draw onto a transparent layer so we can composite with alpha.
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    # Measure the text so we can position it. textbbox is available on
    # modern Pillow (>=9); it returns the pixel bbox the text will occupy.
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    x, y = _position_xy(base.size, (text_w, text_h), position, padding)

    alpha = int(round(opacity * 255))
    fill = (color[0], color[1], color[2], alpha)
    # Offset by (-bbox[0], -bbox[1]) so the glyph actually lands where we
    # asked. textbbox of some fonts has non-zero left/top bearings.
    draw.text((x - bbox[0], y - bbox[1]), text, font=font, fill=fill)

    composed = Image.alpha_composite(base, layer)

    if orig_mode == "RGBA":
        return composed
    # JPEG / most RGB flows: flatten back down. Pillow's .convert("RGB")
    # silently drops alpha against black, which would give weird edges on
    # anti-aliased text. Instead we paste onto a white background of the
    # requested mode so the composite looks clean.
    flat = Image.new(orig_mode, composed.size, (255, 255, 255))
    flat.paste(composed, mask=composed.split()[3])
    return flat


def apply_image_watermark(
    image: Image.Image,
    overlay: Image.Image,
    *,
    position: Position = "bottom-right",
    opacity: float = 0.5,
    overlay_pct: float = 20.0,
    padding_pct: float = 2.0,
) -> Image.Image:
    """Return a new image with ``overlay`` composited onto it.

    ``overlay`` is resized to ``overlay_pct`` of the base image's width while
    preserving its aspect ratio, then composited at ``position`` with
    ``opacity`` multiplied into its alpha channel.
    """
    if position not in VALID_POSITIONS:
        raise ValueError(f"unknown position: {position!r}")
    if not (0.0 <= opacity <= 1.0):
        raise ValueError("opacity must be in [0, 1]")

    orig_mode = image.mode
    base = image.convert("RGBA")
    ov = overlay.convert("RGBA")

    target_w = max(1, int(base.width * overlay_pct / 100.0))
    scale = target_w / ov.width
    target_h = max(1, int(ov.height * scale))
    ov = ov.resize((target_w, target_h), Image.Resampling.LANCZOS)

    # Multiply the overlay's existing alpha by the requested opacity.
    if opacity < 1.0:
        r, g, b, a = ov.split()
        a = a.point(lambda v: int(v * opacity))
        ov = Image.merge("RGBA", (r, g, b, a))

    padding = max(0, int(min(base.width, base.height) * padding_pct / 100.0))
    x, y = _position_xy(base.size, ov.size, position, padding)

    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    layer.paste(ov, (x, y), ov)
    composed = Image.alpha_composite(base, layer)

    if orig_mode == "RGBA":
        return composed
    flat = Image.new(orig_mode, composed.size, (255, 255, 255))
    flat.paste(composed, mask=composed.split()[3])
    return flat
