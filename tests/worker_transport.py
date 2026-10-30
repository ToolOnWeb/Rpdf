"""Runs the complete API contract tests through the disk-based worker boundary."""

import shutil
import uuid
from pathlib import Path

import httpx

from pdf_control.worker import process


class WorkerTransport(httpx.AsyncBaseTransport):
    def __init__(self, root: Path):
        self.root = root

    async def handle_async_request(self, request):
        identifier = uuid.uuid4().hex
        directory = self.root / identifier
        directory.mkdir()
        try:
            (directory / "request.body").write_bytes(await request.aread())
            result = await process(
                {
                    "id": identifier,
                    "workspace": "test-workspace-1234567890",
                    "method": request.method,
                    "path": request.url.path,
                    "headers": list(request.headers.items()),
                },
                self.root,
            )
            path = directory / "response.body"
            return httpx.Response(
                result["status"],
                headers=result["headers"],
                content=path.read_bytes() if path.exists() else b"",
            )
        finally:
            shutil.rmtree(directory)
