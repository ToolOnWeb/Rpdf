import io
import json
import os
import subprocess
import sys
import uuid

import httpx
from pypdf import PdfReader, PdfWriter


def test_persistent_worker_protocol_and_session_isolation(tmp_path):
    worker = subprocess.Popen(
        [sys.executable, "-u", "-m", "pdf_control.worker"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        env={**os.environ, "PDF_CONTROL_WORKER_SPOOL": str(tmp_path)},
    )
    try:
        assert json.loads(worker.stdout.readline()) == {"ready": True, "protocol": 1}

        def request(method, path, workspace, data=None, files=None):
            http = httpx.Request(method, "http://test" + path, data=data, files=files)
            identifier = uuid.uuid4().hex
            directory = tmp_path / identifier
            directory.mkdir()
            (directory / "request.body").write_bytes(http.read())
            message = {
                "id": identifier,
                "workspace": workspace,
                "method": method,
                "path": path,
                "headers": list(http.headers.items()),
            }
            worker.stdin.write(json.dumps(message) + "\n")
            worker.stdin.flush()
            result = json.loads(worker.stdout.readline())
            assert result["id"] == identifier
            result["body"] = (directory / "response.body").read_bytes()
            return result

        stream = io.BytesIO()
        pdf = PdfWriter()
        pdf.add_blank_page(width=200, height=300)
        pdf.write(stream)
        data = stream.getvalue()
        owner = "owner-workspace-1234567890"
        other = "other-workspace-1234567890"
        merged = request(
            "POST",
            "/api/merge",
            owner,
            files=[
                ("files", ("a.pdf", data, "application/pdf")),
                ("files", ("b.pdf", data, "application/pdf")),
            ],
        )
        assert merged["status"] == 200
        assert len(PdfReader(io.BytesIO(merged["body"])).pages) == 2
        first = request(
            "POST",
            "/api/preview-session",
            owner,
            files={"file": ("a.pdf", data, "application/pdf")},
        )
        assert first["status"] == 200
        token = dict(first["headers"])["x-preview-session"]
        foreign = request("POST", "/api/preview-page", other, data={"session": token, "page": "1"})
        assert foreign["status"] == 404
        valid = request("POST", "/api/preview-page", owner, data={"session": token, "page": "1"})
        assert valid["status"] == 200
        denied = request("DELETE", "/api/preview-session/" + token, other)
        assert denied["status"] == 404
        closed = request("DELETE", "/api/preview-session/" + token, owner)
        assert closed["status"] == 204
        assert request("DELETE", "/api/preview-session/" + token, owner)["status"] == 204
        assert request("DELETE", "/api/preview-session/absent-token", other)["status"] == 204
        assert (
            request("POST", "/api/preview-page", owner, data={"session": token, "page": "1"})[
                "status"
            ]
            == 404
        )
    finally:
        worker.stdin.write('{"shutdown":true}\n')
        worker.stdin.flush()
        worker.wait(timeout=10)
    assert worker.returncode == 0
