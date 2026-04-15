"""Tiny JSON request logger as an ASGI middleware.

Writes one line per request to stdout: method, path, status, duration_ms,
bytes_in, bytes_out. No external logging deps.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class JsonRequestLogger:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status_code = 500
        response_bytes = 0
        request_bytes = 0

        async def receive_wrapper() -> Message:
            nonlocal request_bytes
            message = await receive()
            if message["type"] == "http.request":
                body = message.get("body", b"") or b""
                request_bytes += len(body)
            return message

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code, response_bytes
            if message["type"] == "http.response.start":
                status_code = int(message.get("status", 500))
            elif message["type"] == "http.response.body":
                body = message.get("body", b"") or b""
                response_bytes += len(body)
            await send(message)

        try:
            await self.app(scope, receive_wrapper, send_wrapper)
        finally:
            duration_ms = (time.perf_counter() - start) * 1000.0
            record: dict[str, Any] = {
                "method": scope.get("method"),
                "path": scope.get("path"),
                "status": status_code,
                "duration_ms": round(duration_ms, 2),
                "bytes_in": request_bytes,
                "bytes_out": response_bytes,
            }
            sys.stdout.write(json.dumps(record, separators=(",", ":")) + "\n")
            sys.stdout.flush()
