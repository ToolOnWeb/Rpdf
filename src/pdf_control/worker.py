"""Persistent ASGI bridge: JSON metadata over stdio, request/response bytes on disk.

Phoenix owns HTTP/UI. The existing API remains the processing contract, without
a second listening server. Never place document bytes in the JSON protocol.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import sys
import time
from pathlib import Path

from pdf_control.api import _discard_preview_session, _preview_sessions, app

WORKSPACE = re.compile(r"^[A-Za-z0-9_-]{20,80}$")
OWNERS: dict[str, str] = {}
CHUNK = 1024 * 1024


async def process(request: dict, root: Path) -> dict:
    identifier = request["id"]
    workspace = request["workspace"]
    if not WORKSPACE.fullmatch(workspace):
        raise ValueError("Invalid workspace")
    directory = root / identifier
    if not re.fullmatch(r"[a-f0-9]{32}", identifier):
        raise ValueError("Invalid request ID")
    if directory.is_symlink() or directory.resolve().parent != root.resolve():
        raise ValueError("Invalid request directory")
    body = directory / "request.body"
    output = directory / "response.body"
    method = request["method"]
    path = request["path"]
    if not path.startswith("/api/") or method not in {"GET", "POST", "DELETE"}:
        return {"id": identifier, "status": 404, "headers": [], "error": "Unknown operation"}
    token = None
    if path.startswith("/api/preview-session/"):
        token = path.rsplit("/", 1)[-1]
    elif path == "/api/preview-page":
        # The API validates the token and PDF options. Ownership is enforced below
        # by intercepting its source lookup in the worker request context.
        pass

    # A retained instance may own this token. Local absence is an idempotent
    # delete; the guarded proxy mirrors it to retained instances with this same
    # signed workspace cookie. A known foreign owner must still be rejected.
    if token and method == "DELETE" and token not in OWNERS:
        output.write_bytes(b"")
        return {"id": identifier, "status": 204, "headers": []}

    if token and OWNERS.get(token) != workspace:
        output.write_bytes(b'{"detail":"Preview session not found"}')
        return {"id": identifier, "status": 404, "headers": [["content-type", "application/json"]]}
    headers = []
    status = 500
    finished = asyncio.Event()
    with body.open("rb") as incoming, output.open("wb") as outgoing:
        exhausted = False

        async def receive():
            nonlocal exhausted
            if exhausted:
                await finished.wait()
                return {"type": "http.disconnect"}
            chunk = incoming.read(CHUNK)
            exhausted = len(chunk) < CHUNK
            return {"type": "http.request", "body": chunk, "more_body": not exhausted}

        async def send(message):
            nonlocal headers, status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = [
                    [key.decode("latin-1"), value.decode("latin-1")]
                    for key, value in message["headers"]
                ]
            elif message["type"] == "http.response.body":
                outgoing.write(message.get("body", b""))

        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "root_path": "",
            "query_string": b"",
            "server": ("127.0.0.1", 0),
            "client": ("127.0.0.1", 0),
            "headers": [
                (k.encode("latin-1"), v.encode("latin-1")) for k, v in request.get("headers", [])
            ],
        }
        from pdf_control import api

        original = api._preview_session_source

        def owned_source(value):
            if OWNERS.get(value) != workspace:
                from fastapi import HTTPException

                raise HTTPException(status_code=404, detail="انتهت جلسة المعاينة.")
            return original(value)

        # One request per process: this scoped replacement cannot race a second
        # ASGI request. Restored even on processing failure.
        api._preview_session_source = owned_source
        try:
            await app(scope, receive, send)
        finally:
            api._preview_session_source = original

    for key, value in headers:
        if key.lower() == "x-preview-session" and status < 400:
            OWNERS[value] = workspace
    if token and status < 400:
        OWNERS.pop(token, None)
    for expired in set(OWNERS) - set(_preview_sessions):
        OWNERS.pop(expired, None)
    return {"id": identifier, "status": status, "headers": headers}


def main():
    root = Path(os.environ["PDF_CONTROL_WORKER_SPOOL"]).resolve()
    root.mkdir(parents=True, exist_ok=True)
    protocol = sys.stdout
    with contextlib.redirect_stdout(sys.stderr):
        protocol.write(json.dumps({"ready": True, "protocol": 1}) + "\n")
        protocol.flush()
        try:
            for line in sys.stdin:
                request = json.loads(line)
                if request.get("shutdown"):
                    break
                try:
                    result = asyncio.run(process(request, root))
                except Exception:
                    # No paths, document content or exception detail in protocol.
                    result = {
                        "id": request.get("id"),
                        "status": 500,
                        "headers": [],
                        "error": "PDF worker failed",
                    }
                result["valid_sessions"] = sum(
                    s.expires_at > time.monotonic() for s in _preview_sessions.values()
                )
                protocol.write(json.dumps(result, ensure_ascii=True) + "\n")
                protocol.flush()
        finally:
            for token in list(_preview_sessions):
                _discard_preview_session(token)


if __name__ == "__main__":
    main()
