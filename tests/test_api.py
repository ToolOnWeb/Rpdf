from __future__ import annotations

import io

import httpx
import pytest
from fastapi import BackgroundTasks
from pypdf import PdfReader, PdfWriter

from pdf_control.api import _download, _download_response, app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


def _pdf_bytes(page_count: int = 1) -> bytes:
    output = io.BytesIO()
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=200, height=300)
    writer.write(output)
    return output.getvalue()


@pytest.mark.anyio
async def test_browser_home_is_served(client) -> None:
    response = await client.get("/")

    assert response.status_code == 200
    assert "PDF Control" in response.text
    assert "Streamlit" not in response.text
    assert "theme-toggle" in response.text
    assert "pdf-control-theme" in response.text
    assert 'id="merge-add-files"' in response.text
    assert 'id="merge-files-list"' in response.text


@pytest.mark.anyio
async def test_health_endpoint(client) -> None:
    response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.anyio
async def test_info_returns_pdf_metadata_without_server_path(client) -> None:
    response = await client.post(
        "/api/info",
        files={"file": ("document.pdf", _pdf_bytes(2), "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json()["pages"] == 2
    assert "path" not in response.json()


@pytest.mark.anyio
async def test_merge_returns_valid_pdf(client) -> None:
    response = await client.post(
        "/api/merge",
        files=[
            ("files", ("first.pdf", _pdf_bytes(), "application/pdf")),
            ("files", ("second.pdf", _pdf_bytes(2), "application/pdf")),
        ],
        data={"output_name": "combined.pdf"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert len(PdfReader(io.BytesIO(response.content)).pages) == 3
    assert "combined.pdf" in response.headers["content-disposition"]


@pytest.mark.anyio
async def test_rotate_accepts_arabic_page_separator(client) -> None:
    response = await client.post(
        "/api/rotate",
        files={"file": ("document.pdf", _pdf_bytes(2), "application/pdf")},
        data={"pages": "1،2", "angle": "90"},
    )

    assert response.status_code == 200
    reader = PdfReader(io.BytesIO(response.content))
    assert [page.rotation for page in reader.pages] == [90, 90]


@pytest.mark.anyio
async def test_non_pdf_upload_is_rejected(client) -> None:
    response = await client.post(
        "/api/info",
        files={"file": ("fake.pdf", b"not a pdf", "application/pdf")},
    )

    assert response.status_code == 400
    assert "ليس ملف PDF" in response.json()["detail"]


@pytest.mark.anyio
async def test_merge_requires_two_files(client) -> None:
    response = await client.post(
        "/api/merge",
        files=[("files", ("only.pdf", _pdf_bytes(), "application/pdf"))],
    )

    assert response.status_code == 400


@pytest.mark.anyio
async def test_editable_rejects_excessive_dpi_at_api_boundary(client) -> None:
    response = await client.post(
        "/api/editable",
        files={"file": ("document.pdf", _pdf_bytes(), "application/pdf")},
        data={"ocr_dpi": "401"},
    )

    assert response.status_code == 400
    assert "OCR" in response.json()["detail"]


@pytest.mark.anyio
async def test_download_supports_arabic_status_header(tmp_path) -> None:
    directory = tmp_path / "operation"
    directory.mkdir()
    output = directory / "output.pdf"
    output.write_bytes(_pdf_bytes())

    response = _download_response(
        _download(
            output,
            directory,
            BackgroundTasks(),
            "result.pdf",
            message="تم إنشاء النتيجة.",
        )
    )

    assert response.status_code == 200
    assert "%D8%AA%D9%85" in response.headers["x-pdf-control-message"]
    assert directory.exists()
    content = b"".join([chunk async for chunk in response.body_iterator])
    assert content.startswith(b"%PDF-")
    assert not directory.exists()


@pytest.mark.anyio
async def test_layer_preview_returns_page_geometry(client) -> None:
    response = await client.post(
        "/api/layer-preview",
        files={"file": ("document.pdf", _pdf_bytes(2), "application/pdf")},
        data={"page": "2", "dpi": "96"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["x-page-count"] == "2"
    assert float(response.headers["x-page-width"]) == 200
    assert response.content.startswith(b"\x89PNG")


@pytest.mark.anyio
async def test_preview_session_reuses_uploaded_pdf(client) -> None:
    first_page = await client.post(
        "/api/preview-session",
        files={"file": ("document.pdf", _pdf_bytes(2), "application/pdf")},
        data={"dpi": "96"},
    )

    assert first_page.status_code == 200
    token = first_page.headers["x-preview-session"]
    second_page = await client.post(
        "/api/preview-page",
        data={"session": token, "page": "2", "dpi": "96"},
    )
    assert second_page.status_code == 200
    assert second_page.headers["x-page-count"] == "2"
    assert second_page.content.startswith(b"\x89PNG")

    closed = await client.delete(f"/api/preview-session/{token}")
    assert closed.status_code == 204
    expired = await client.post(
        "/api/preview-page",
        data={"session": token, "page": "1", "dpi": "96"},
    )
    assert expired.status_code == 404


@pytest.mark.anyio
async def test_layer_edit_returns_pdf_without_removing_base_page(client) -> None:
    edits = '[{"type":"mask","page":1,"x":10,"y":10,"width":40,"height":20}]'
    response = await client.post(
        "/api/layer-edit",
        files={"file": ("document.pdf", _pdf_bytes(), "application/pdf")},
        data={"edits": edits, "output_name": "layered.pdf"},
    )

    assert response.status_code == 200
    assert len(PdfReader(io.BytesIO(response.content)).pages) == 1
    assert "layered.pdf" in response.headers["content-disposition"]


@pytest.mark.anyio
async def test_layer_edit_deletes_selected_page(client) -> None:
    response = await client.post(
        "/api/layer-edit",
        files={"file": ("document.pdf", _pdf_bytes(3), "application/pdf")},
        data={"edits": "[]", "deleted_pages": "[2]", "output_name": "shorter.pdf"},
    )

    assert response.status_code == 200
    assert len(PdfReader(io.BytesIO(response.content)).pages) == 2
    assert "%D8%AD%D8%B0%D9%81" in response.headers["x-pdf-control-message"]


@pytest.mark.anyio
async def test_layer_edit_rejects_deleting_all_pages(client) -> None:
    response = await client.post(
        "/api/layer-edit",
        files={"file": ("document.pdf", _pdf_bytes(2), "application/pdf")},
        data={"edits": "[]", "deleted_pages": "[1,2]"},
    )

    assert response.status_code == 400
    assert "جميع صفحات" in response.json()["detail"]
