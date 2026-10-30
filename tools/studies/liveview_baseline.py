"""Synthetic local measurements; not a production load test."""

import json
import platform
import statistics
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from pdf_control import core


def fixtures(folder):
    for name in ("a", "b"):
        pdf = canvas.Canvas(str(folder / f"{name}.pdf"))
        for page in range(20):
            pdf.drawString(72, 720, f"PDF Control synthetic {name} page {page + 1}")
            pdf.showPage()
        pdf.save()
    image = Image.new("RGB", (1400, 500), "white")
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 72)
    ImageDraw.Draw(image).text((80, 170), "INVOICE TOTAL 1250", fill="black", font=font)
    image.save(folder / "scan.pdf", "PDF", resolution=150)


def operation(name, folder):
    a, b, output = folder / "a.pdf", folder / "b.pdf", folder / "result.pdf"
    if name == "info20":
        assert core.get_pdf_info(a)["pages"] == 20
    elif name == "merge40":
        core.merge_pdfs([a, b], output)
        assert len(PdfReader(output).pages) == 40
    elif name == "extract10":
        core.extract_pages(a, output, "1-10")
        assert len(PdfReader(output).pages) == 10
    elif name == "rotate20":
        core.rotate_pages(a, output, "all", 90)
        assert all(p.rotation == 90 for p in PdfReader(output).pages)
    elif name == "render20_120dpi":
        images = core.render_pdf_pages_as_png(a, dpi=120)
        assert len(images) == 20 and images[0].startswith(b"\x89PNG")
    elif name == "ocr1_eng":
        core.create_editable_pdf(
            folder / "scan.pdf",
            output,
            use_ocr=True,
            ocr_language="eng",
            ocr_dpi=200,
            ocr_min_confidence=20,
        )
        fields = PdfReader(output).get_fields()
        assert (
            fields and "INVOICE" in " ".join(str(f.get("/TU", "")) for f in fields.values()).upper()
        )
    else:
        raise ValueError(name)


def stats(samples):
    return {
        "n": len(samples),
        "median_ms": round(statistics.median(samples), 3),
        "min_ms": round(min(samples), 3),
        "max_ms": round(max(samples), 3),
        "samples_ms": [round(v, 3) for v in samples],
    }


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--persistent":
        folder = Path(sys.argv[2])
        print("ready", flush=True)
        for line in sys.stdin:
            if line.strip() == "quit":
                break
            operation(line.strip(), folder)
            print("ok", flush=True)
    elif len(sys.argv) > 2 and sys.argv[1] == "--worker":
        operation("merge40", Path(sys.argv[2]))
        print("ok")
    else:
        folder = Path(".runtime/study-fixtures").resolve()
        folder.mkdir(parents=True, exist_ok=True)
        fixtures(folder)
        result = {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "fixture_directory": str(folder),
            "scope": "synthetic local; no browser/network/load; correctness assertions included",
            "warm_engine": {},
        }
        for name in ("info20", "merge40", "extract10", "rotate20", "render20_120dpi", "ocr1_eng"):
            operation(name, folder)
            samples = []
            for _ in range(7):
                start = time.perf_counter()
                operation(name, folder)
                samples.append((time.perf_counter() - start) * 1000)
            result["warm_engine"][name] = stats(samples)
        print(json.dumps(result, indent=2))
