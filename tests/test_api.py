"""API-level tests using FastAPI's synchronous TestClient."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from watermark_api.main import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _open(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    img.load()
    return img


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_landing_page_is_html(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "watermark-api" in r.text
    assert "/watermark/text" in r.text


def test_openapi_schema(client: TestClient) -> None:
    r = client.get("/openapi.json")
    assert r.status_code == 200
    schema = r.json()
    assert "/watermark/text" in schema["paths"]
    assert "/watermark/image" in schema["paths"]
    assert "/health" in schema["paths"]


def test_text_watermark_jpeg_roundtrip(client: TestClient, jpeg_image: bytes) -> None:
    r = client.post(
        "/watermark/text",
        files={"file": ("in.jpg", jpeg_image, "image/jpeg")},
        data={"text": "hello", "position": "bottom-right"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    out = _open(r.content)
    assert out.format == "JPEG"
    assert out.size == (400, 300)


def test_text_watermark_png_preserves_format(
    client: TestClient, png_image: bytes
) -> None:
    r = client.post(
        "/watermark/text",
        files={"file": ("in.png", png_image, "image/png")},
        data={"text": "hi"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    out = _open(r.content)
    assert out.format == "PNG"


def test_text_watermark_webp_preserves_format(
    client: TestClient, webp_image: bytes
) -> None:
    r = client.post(
        "/watermark/text",
        files={"file": ("in.webp", webp_image, "image/webp")},
        data={"text": "hi"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/webp"
    out = _open(r.content)
    assert out.format == "WEBP"


@pytest.mark.parametrize(
    "position", ["top-left", "top-right", "bottom-left", "bottom-right", "center"]
)
def test_text_watermark_all_positions(
    client: TestClient, jpeg_image: bytes, position: str
) -> None:
    r = client.post(
        "/watermark/text",
        files={"file": ("in.jpg", jpeg_image, "image/jpeg")},
        data={"text": "x", "position": position},
    )
    assert r.status_code == 200


def test_text_watermark_invalid_position_returns_422(
    client: TestClient, jpeg_image: bytes
) -> None:
    r = client.post(
        "/watermark/text",
        files={"file": ("in.jpg", jpeg_image, "image/jpeg")},
        data={"text": "x", "position": "sideways"},
    )
    assert r.status_code == 422
    assert r.json()["error"] == "invalid_position"


def test_text_watermark_invalid_color_returns_422(
    client: TestClient, jpeg_image: bytes
) -> None:
    r = client.post(
        "/watermark/text",
        files={"file": ("in.jpg", jpeg_image, "image/jpeg")},
        data={"text": "x", "color": "not-a-color"},
    )
    assert r.status_code == 422
    assert r.json()["error"] == "invalid_color"


def test_text_watermark_valid_hex_color(
    client: TestClient, jpeg_image: bytes
) -> None:
    r = client.post(
        "/watermark/text",
        files={"file": ("in.jpg", jpeg_image, "image/jpeg")},
        data={"text": "x", "color": "#8040C0"},
    )
    assert r.status_code == 200


def test_text_watermark_opacity_zero(client: TestClient, jpeg_image: bytes) -> None:
    r = client.post(
        "/watermark/text",
        files={"file": ("in.jpg", jpeg_image, "image/jpeg")},
        data={"text": "x", "opacity": "0.0"},
    )
    assert r.status_code == 200


def test_text_watermark_opacity_one(client: TestClient, jpeg_image: bytes) -> None:
    r = client.post(
        "/watermark/text",
        files={"file": ("in.jpg", jpeg_image, "image/jpeg")},
        data={"text": "x", "opacity": "1.0"},
    )
    assert r.status_code == 200


def test_text_watermark_opacity_out_of_range(
    client: TestClient, jpeg_image: bytes
) -> None:
    r = client.post(
        "/watermark/text",
        files={"file": ("in.jpg", jpeg_image, "image/jpeg")},
        data={"text": "x", "opacity": "2.5"},
    )
    # FastAPI Form ge/le validation returns 422.
    assert r.status_code == 422


def test_text_watermark_non_image_returns_415(client: TestClient) -> None:
    r = client.post(
        "/watermark/text",
        files={"file": ("a.txt", b"nope, just some text bytes here", "image/jpeg")},
        data={"text": "x"},
    )
    assert r.status_code == 415
    assert r.json()["error"] == "unsupported_media_type"


def test_text_watermark_missing_text_returns_422(
    client: TestClient, jpeg_image: bytes
) -> None:
    r = client.post(
        "/watermark/text",
        files={"file": ("in.jpg", jpeg_image, "image/jpeg")},
    )
    assert r.status_code == 422


def test_text_watermark_oversize_returns_413(
    client: TestClient,
    jpeg_image: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MAX_UPLOAD_MB", "0")
    r = client.post(
        "/watermark/text",
        files={"file": ("in.jpg", jpeg_image, "image/jpeg")},
        data={"text": "x"},
    )
    assert r.status_code == 413
    assert r.json()["error"] == "payload_too_large"


def test_text_watermark_font_size_clamped(
    client: TestClient, jpeg_image: bytes
) -> None:
    # Outside [1, 20] -> FastAPI Form validator rejects with 422.
    r = client.post(
        "/watermark/text",
        files={"file": ("in.jpg", jpeg_image, "image/jpeg")},
        data={"text": "x", "font_size_pct": "50"},
    )
    assert r.status_code == 422


def test_text_watermark_padding_accepted(
    client: TestClient, jpeg_image: bytes
) -> None:
    r = client.post(
        "/watermark/text",
        files={"file": ("in.jpg", jpeg_image, "image/jpeg")},
        data={"text": "x", "padding_pct": "5"},
    )
    assert r.status_code == 200


def test_image_watermark_basic(
    client: TestClient, jpeg_image: bytes, overlay_png: bytes
) -> None:
    r = client.post(
        "/watermark/image",
        files={
            "file": ("in.jpg", jpeg_image, "image/jpeg"),
            "overlay": ("logo.png", overlay_png, "image/png"),
        },
        data={"position": "top-left", "overlay_pct": "20"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    out = _open(r.content)
    assert out.format == "JPEG"


def test_image_watermark_overlay_must_be_png(
    client: TestClient, jpeg_image: bytes
) -> None:
    r = client.post(
        "/watermark/image",
        files={
            "file": ("in.jpg", jpeg_image, "image/jpeg"),
            "overlay": ("logo.jpg", jpeg_image, "image/jpeg"),
        },
    )
    assert r.status_code == 415


def test_image_watermark_missing_overlay_returns_422(
    client: TestClient, jpeg_image: bytes
) -> None:
    r = client.post(
        "/watermark/image",
        files={"file": ("in.jpg", jpeg_image, "image/jpeg")},
    )
    assert r.status_code == 422
