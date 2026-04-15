"""FastAPI app: routes, error shaping, size limits, HTML landing page."""

from __future__ import annotations

import io
import os
from typing import Optional

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from PIL import Image, UnidentifiedImageError

from . import __version__
from .logging import JsonRequestLogger
from .models import ErrorResponse, HealthResponse
from .validators import (
    ImageKind,
    InvalidColorError,
    UnsupportedImageError,
    clamp,
    parse_hex_color,
    sniff_image,
)
from .watermark import VALID_POSITIONS, apply_image_watermark, apply_text_watermark


def _max_upload_bytes() -> int:
    mb = int(os.environ.get("MAX_UPLOAD_MB", "10"))
    return mb * 1024 * 1024


app = FastAPI(
    title="watermark-api",
    version=__version__,
    description=(
        "Small FastAPI service that adds text or image watermarks to uploaded "
        "photos using Pillow. Two endpoints, format-preserving, < 120 MB image."
    ),
)

app.add_middleware(JsonRequestLogger)


def _error(status: int, error: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=ErrorResponse(error=error, detail=detail).model_dump(),
    )


LANDING_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>watermark-api</title>
<style>
  body { font-family: -apple-system, system-ui, sans-serif; max-width: 720px;
         margin: 2rem auto; padding: 0 1rem; color: #222; line-height: 1.5; }
  h1 { margin-bottom: 0.2rem; }
  code, pre { background: #f4f4f4; border-radius: 4px; }
  code { padding: 1px 4px; }
  pre { padding: 12px; overflow-x: auto; }
  a { color: #0b6; }
  .muted { color: #777; font-size: 0.9rem; }
</style>
</head>
<body>
  <h1>watermark-api</h1>
  <p class="muted">FastAPI + Pillow. Watermark images over HTTP.</p>
  <h2>Endpoints</h2>
  <ul>
    <li><code>POST /watermark/text</code> &mdash; multipart upload + text field</li>
    <li><code>POST /watermark/image</code> &mdash; multipart upload + overlay PNG</li>
    <li><code>GET  /health</code> &mdash; liveness probe</li>
    <li><code>GET  /docs</code> &mdash; OpenAPI / Swagger UI</li>
  </ul>
  <h2>Try it</h2>
<pre>curl -F "file=@photo.jpg" \\
     -F "text=(C) SEN 2026" \\
     -F "position=bottom-right" \\
     -F "opacity=0.6" \\
     http://localhost:8000/watermark/text -o out.jpg</pre>
  <p class="muted">Format is preserved: JPEG in &rarr; JPEG out, PNG &rarr; PNG, WebP &rarr; WebP. Max upload size is configurable via <code>MAX_UPLOAD_MB</code>.</p>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def landing() -> HTMLResponse:
    return HTMLResponse(LANDING_HTML)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__)


def _validate_position(position: str) -> Optional[JSONResponse]:
    if position not in VALID_POSITIONS:
        return _error(
            422,
            "invalid_position",
            f"position must be one of {sorted(VALID_POSITIONS)}",
        )
    return None


def _save_to_bytes(image: Image.Image, kind: ImageKind) -> bytes:
    buf = io.BytesIO()
    if kind.pil_format == "JPEG":
        if image.mode != "RGB":
            image = image.convert("RGB")
        image.save(buf, format="JPEG", quality=90)
    elif kind.pil_format == "PNG":
        image.save(buf, format="PNG")
    elif kind.pil_format == "WEBP":
        image.save(buf, format="WEBP", lossless=True)
    else:  # pragma: no cover — sniff_image only returns known kinds
        raise RuntimeError(f"unknown image kind: {kind.pil_format}")
    return buf.getvalue()


async def _read_image_upload(
    file: UploadFile, max_bytes: int
) -> tuple[Optional[JSONResponse], Optional[bytes], Optional[ImageKind]]:
    data = await file.read()
    if len(data) > max_bytes:
        return (
            _error(
                413,
                "payload_too_large",
                f"file exceeds MAX_UPLOAD_MB={max_bytes // (1024 * 1024)}",
            ),
            None,
            None,
        )
    try:
        kind = sniff_image(data)
    except UnsupportedImageError as exc:
        return _error(415, "unsupported_media_type", str(exc)), None, None
    return None, data, kind


@app.post(
    "/watermark/text",
    responses={
        200: {"content": {"image/*": {}}, "description": "Watermarked image"},
        413: {"model": ErrorResponse, "description": "Upload exceeds size limit"},
        415: {"model": ErrorResponse, "description": "Unsupported media type"},
        422: {"model": ErrorResponse, "description": "Invalid parameters"},
    },
)
async def watermark_text(
    file: UploadFile = File(..., description="Image to watermark (JPEG/PNG/WebP)"),
    text: str = Form(..., max_length=200, description="Watermark text"),
    position: str = Form("bottom-right"),
    opacity: float = Form(0.5, ge=0.0, le=1.0),
    color: str = Form("#ffffff"),
    font_size_pct: float = Form(3.0, ge=1.0, le=20.0),
    padding_pct: float = Form(2.0, ge=0.0, le=20.0),
) -> StreamingResponse:
    max_bytes = _max_upload_bytes()

    err = _validate_position(position)
    if err is not None:
        return err

    try:
        rgb = parse_hex_color(color)
    except InvalidColorError as exc:
        return _error(422, "invalid_color", str(exc))

    err, data, kind = await _read_image_upload(file, max_bytes)
    if err is not None:
        return err
    assert data is not None and kind is not None

    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        return _error(422, "unprocessable_image", f"Pillow failed to open image: {exc}")

    out = apply_text_watermark(
        image,
        text=text,
        position=position,
        opacity=clamp(opacity, 0.0, 1.0),
        color=rgb,
        font_size_pct=clamp(font_size_pct, 1.0, 20.0),
        padding_pct=clamp(padding_pct, 0.0, 20.0),
    )
    body = _save_to_bytes(out, kind)
    return StreamingResponse(io.BytesIO(body), media_type=kind.mime)


@app.post(
    "/watermark/image",
    responses={
        200: {"content": {"image/*": {}}, "description": "Watermarked image"},
        413: {"model": ErrorResponse, "description": "Upload exceeds size limit"},
        415: {"model": ErrorResponse, "description": "Unsupported media type"},
        422: {"model": ErrorResponse, "description": "Invalid parameters"},
    },
)
async def watermark_image(
    file: UploadFile = File(..., description="Image to watermark (JPEG/PNG/WebP)"),
    overlay: UploadFile = File(..., description="Overlay PNG with alpha"),
    position: str = Form("bottom-right"),
    opacity: float = Form(0.5, ge=0.0, le=1.0),
    overlay_pct: float = Form(20.0, ge=1.0, le=50.0),
    padding_pct: float = Form(2.0, ge=0.0, le=20.0),
) -> StreamingResponse:
    max_bytes = _max_upload_bytes()

    err = _validate_position(position)
    if err is not None:
        return err

    err, data, kind = await _read_image_upload(file, max_bytes)
    if err is not None:
        return err
    assert data is not None and kind is not None

    overlay_bytes = await overlay.read()
    if len(overlay_bytes) > max_bytes:
        return _error(
            413,
            "payload_too_large",
            f"overlay exceeds MAX_UPLOAD_MB={max_bytes // (1024 * 1024)}",
        )
    try:
        ov_kind = sniff_image(overlay_bytes)
    except UnsupportedImageError as exc:
        return _error(415, "unsupported_media_type", f"overlay: {exc}")
    if ov_kind.pil_format != "PNG":
        return _error(
            415,
            "unsupported_media_type",
            "overlay must be a PNG (with alpha channel)",
        )

    try:
        image = Image.open(io.BytesIO(data))
        image.load()
        overlay_img = Image.open(io.BytesIO(overlay_bytes))
        overlay_img.load()
    except (UnidentifiedImageError, OSError) as exc:
        return _error(422, "unprocessable_image", f"Pillow failed to open image: {exc}")

    out = apply_image_watermark(
        image,
        overlay_img,
        position=position,
        opacity=clamp(opacity, 0.0, 1.0),
        overlay_pct=clamp(overlay_pct, 1.0, 50.0),
        padding_pct=clamp(padding_pct, 0.0, 20.0),
    )
    body = _save_to_bytes(out, kind)
    return StreamingResponse(io.BytesIO(body), media_type=kind.mime)
