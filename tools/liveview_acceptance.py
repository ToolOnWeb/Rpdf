"""Local HTTP acceptance; only generated documents, never production data."""

import io
import json
import os
import sys
import time
import zipfile
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader
from reportlab.pdfgen import canvas

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:4000"
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path(os.environ.get("PDF_CONTROL_ACCEPTANCE_OUTPUT", ROOT / ".runtime" / "acceptance"))
OUTPUT.mkdir(parents=True, exist_ok=True)
source = OUTPUT / "sample.pdf"
pdf = canvas.Canvas(str(source))
pdf.drawString(72, 720, "Alpha Invoice Total 1250")
pdf.acroForm.checkbox(name="approved", x=72, y=650, checked=True)
pdf.showPage()
pdf.drawString(72, 720, "Second page")
pdf.save()
sample = source.read_bytes()
font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 72)
image = Image.new("RGB", (1400, 500), "white")
ImageDraw.Draw(image).text((80, 170), "INVOICE TOTAL 1250", fill="black", font=font)
image.save(OUTPUT / "scan.pdf", "PDF", resolution=150)
results = []
with httpx.Client(base_url=BASE, timeout=60) as client:
    assert client.get("/").status_code == 200
    for asset in (
        "/liveview.js",
        "/workspace.js",
        "/app.css",
        "/vendor/phoenix/phoenix.mjs",
        "/vendor/liveview/phoenix_live_view.esm.js",
    ):
        response = client.get(asset)
        assert response.status_code == 200, (asset, response.status_code)

    def run(endpoint, data=None, files=None):
        started = time.perf_counter()
        response = client.post(
            "/api/" + endpoint,
            data=data or {},
            files=files or {"file": ("sample.pdf", sample, "application/pdf")},
        )
        assert response.status_code == 200, (endpoint, response.status_code, response.text[:300])
        results.append(
            {
                "operation": endpoint,
                "ms": round((time.perf_counter() - started) * 1000, 3),
                "bytes": len(response.content),
            }
        )
        return response

    assert run("info").json()["pages"] == 2
    merged = run(
        "merge",
        files=[
            ("files", ("a.pdf", sample, "application/pdf")),
            ("files", ("b.pdf", sample, "application/pdf")),
        ],
    )
    assert len(PdfReader(io.BytesIO(merged.content)).pages) == 4
    assert "content-disposition" in merged.headers
    assert len(PdfReader(io.BytesIO(run("extract", {"pages": "2"}).content)).pages) == 1
    assert len(zipfile.ZipFile(io.BytesIO(run("split").content)).namelist()) == 2
    assert (
        PdfReader(io.BytesIO(run("rotate", {"pages": "1", "angle": "90"}).content))
        .pages[0]
        .rotation
        == 90
    )
    inserted = run(
        "insert",
        {"after_page": "1"},
        files={
            "base_file": ("a.pdf", sample, "application/pdf"),
            "insert_file": ("b.pdf", sample, "application/pdf"),
        },
    )
    assert len(PdfReader(io.BytesIO(inserted.content)).pages) == 4
    replaced = run("replace-text", {"find_text": "Alpha", "replace_text": "Beta"})
    assert "Beta" in PdfReader(io.BytesIO(replaced.content)).pages[0].extract_text()
    added = run(
        "add-text", {"text": "Added", "page": "1", "x": "72", "y": "500", "font_size": "12"}
    )
    assert "Added" in PdfReader(io.BytesIO(added.content)).pages[0].extract_text()
    assert run("layer-preview", {"page": "1", "dpi": "96"}).content.startswith(b"\x89PNG")
    preview = run("preview-session", {"page": "1", "dpi": "96"})
    token = preview.headers["x-preview-session"]
    assert run("preview-page", {"session": token, "page": "2"}).content.startswith(b"\x89PNG")
    with httpx.Client(base_url=BASE) as foreign:
        foreign.get("/")
        assert foreign.post("/api/preview-page", data={"session": token}).status_code == 404
    assert client.delete("/api/preview-session/" + token).status_code == 204
    layers = run("layer-edit", {"edits": json.dumps([]), "deleted_pages": json.dumps([2])})
    assert len(PdfReader(io.BytesIO(layers.content)).pages) == 1
    assert PdfReader(io.BytesIO(run("editable").content)).get_fields()
    exact = run("exact-editable", {"render_dpi": "96", "ocr_dpi": "200"})
    assert any(
        f.get("/FT") == "/Btn" for f in PdfReader(io.BytesIO(exact.content)).get_fields().values()
    )
    ocr = run(
        "editable",
        {"use_ocr": "true", "ocr_language": "eng", "ocr_dpi": "200", "ocr_min_confidence": "20"},
        files={"file": ("scan.pdf", (OUTPUT / "scan.pdf").read_bytes(), "application/pdf")},
    )
    fields = PdfReader(io.BytesIO(ocr.content)).get_fields()
    assert "INVOICE" in " ".join(str(f.get("/TU", "")) for f in fields.values()).upper()
result = {
    "base_url": BASE,
    "scope": "generated English PDF/scan; actual HTTP via Phoenix and persistent worker",
    "operations": results,
    "api_checks": "passed",
}
(OUTPUT / "http-acceptance.json").write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
