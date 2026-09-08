# syntax=docker/dockerfile:1.6

# --- builder stage -----------------------------------------------------------
FROM python:3.12-alpine AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Native libs Pillow needs to build from source on Alpine.
# freetype-dev is required so Pillow's ImageFont.truetype() can load TTFs
# at runtime — without it you get "decoder pilopen not available" or the
# FreeType C library will be missing entirely.
RUN apk add --no-cache \
        build-base \
        libjpeg-turbo-dev \
        zlib-dev \
        tiff-dev \
        libwebp-dev \
        freetype-dev

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN pip install --no-cache-dir --prefix=/install ".[dev]" \
    && find /install -name "__pycache__" -type d -exec rm -rf {} + \
    && find /install -name "*.dist-info" -type d -exec rm -rf {} + \
    && find /install -name "tests" -type d -exec rm -rf {} +

# --- final stage -------------------------------------------------------------
FROM python:3.12-alpine AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/usr/local/bin:$PATH \
    PYTEST_ADDOPTS="--rootdir=/app /app/tests"

# Runtime native libs (no -dev headers, no compilers) + font-dejavu so text
# watermarks have a real TrueType to render with. Bundling the font here is a
# deploy-time decision: the image gets ~2 MB bigger but users don't need to
# mount a font volume or pass --font-path.
RUN apk add --no-cache \
        libjpeg-turbo \
        zlib \
        tiff \
        libwebp \
        freetype \
        font-dejavu \
        fonts-liberation \
        fontconfig

COPY --from=builder /install /usr/local

WORKDIR /app
COPY src ./src
COPY tests ./tests
COPY pyproject.toml README.md LICENSE ./

RUN adduser -D -s /bin/sh runner \
    && chown -R runner:runner /app
USER runner

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; \
    sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"

CMD ["python", "-m", "watermark_api"]
