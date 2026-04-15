"""Entry point so `python -m watermark_api` starts the server."""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(
        "watermark_api.main:app",
        host=host,
        port=port,
        log_config=None,  # our middleware handles request logging
        access_log=False,
    )


if __name__ == "__main__":
    main()
