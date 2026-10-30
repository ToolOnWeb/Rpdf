"""Synthetic parity measurements, not a representative Arabic accuracy claim."""

import hashlib
import json
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader

from pdf_control import core

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".runtime/acceptance"
font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
reference_text = "مرحبا بالعالم"
font = ImageFont.truetype(font_path, 72)
image = Image.new("RGB", (1600, 500), "white")
ImageDraw.Draw(image).text(
    (1450, 180), reference_text, fill="black", font=font, direction="rtl", anchor="ra"
)
scan = OUT / "arabic-scan.pdf"
image.save(scan, "PDF", resolution=150)
reference = OUT / "arabic-reference.pdf"
count = core.create_editable_pdf(
    scan, reference, use_ocr=True, ocr_language="ara", ocr_dpi=200, ocr_min_confidence=20
)
assert count > 0
with httpx.Client(base_url="http://127.0.0.1:4000", timeout=60) as client:
    client.get("/")
    response = client.post(
        "/api/editable",
        data={
            "use_ocr": "true",
            "ocr_language": "ara",
            "ocr_dpi": "200",
            "ocr_min_confidence": "20",
        },
        files={"file": ("arabic.pdf", scan.read_bytes(), "application/pdf")},
    )
    assert response.status_code == 200, response.text[:200]
    migrated = OUT / "arabic-migrated.pdf"
    migrated.write_bytes(response.content)


def labels(path):
    return [str(value.get("/TU", "")) for value in PdfReader(path).get_fields().values()]


direct = labels(reference)
through_phoenix = labels(migrated)
assert direct == through_phoenix


def distance(a, b):
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        following = [i]
        for j, y in enumerate(b, 1):
            following.append(min(row[j] + 1, following[-1] + 1, row[j - 1] + (x != y)))
        row = following
    return row[-1]


recognized = " ".join(through_phoenix)
cer = distance(reference_text, recognized) / len(reference_text)
direct_images = core.render_pdf_pages_as_png(reference, dpi=120)
migrated_images = core.render_pdf_pages_as_png(migrated, dpi=120)
assert direct_images == migrated_images
result = {
    "scope": "one synthetic Arabic sample; does not establish real-document accuracy",
    "reference": reference_text,
    "recognized": recognized,
    "cer": cer,
    "ocr_fields_identical": True,
    "rendered_pages_identical": True,
    "render_sha256": hashlib.sha256(direct_images[0]).hexdigest(),
}
(OUT / "arabic-parity.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
print(json.dumps(result, ensure_ascii=False))
