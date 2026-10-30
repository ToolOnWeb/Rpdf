# PDF Control

Current development release: **1.1.0**.

PDF Control is a local browser app for everyday PDF work. It uses a standard HTML/CSS/JavaScript interface backed by FastAPI and does not depend on Streamlit.

## Phoenix LiveView application

The local Elixir/Phoenix application is in `web/`, using the existing PDF engine through a persistent, bounded worker. The current PDF operations and browser editor remain available; the editor uses a LiveView JavaScript hook. This does not automatically replace the published Python release.

Run from the repository root with Elixir/OTP and the existing Python virtual environment available:

```sh
PHX_SERVER=true PORT=4000 sh scripts/liveview.sh phx.server
```

See [verified operating instructions and remaining release gates](docs/LIVEVIEW_OPERATING_AR.md) for tests, packaging, settings and limitations.
## Features

- PDF information view with page count, encryption status, and metadata.
- Merge two or more PDF files into one document.
- Extract selected pages using formats such as `1,3,5-7` or `3;8`.
- Split a PDF into individual page files packaged as a ZIP archive.
- Rotate selected pages by `90`, `180`, or `270` degrees.
- Replace text when it is available in the PDF text layer.
- Add text to a selected page with optional TTF font support for Arabic and other non-Latin text.
- Visually cover existing content and add movable text layers without deleting the original PDF text.
- Generate a same-layout editable PDF by adding form fields over selectable text, with optional OCR for scanned PDFs.
- Generate an exact-look editable PDF by rendering the original pages as image backgrounds and placing transparent editable fields and clickable checkboxes above them.
- Insert a full PDF document into another PDF after a selected page.

## Requirements

- Python 3.10 or newer.
- A modern web browser.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

For development and tests:

```bash
pip install -e .[dev]
```

For OCR support with scanned/image-only PDFs:

```bash
.venv/bin/python -m pip install -e '.[ocr]'
sudo apt install tesseract-ocr tesseract-ocr-ara
```

If the virtual environment is already activated, this is equivalent to:

```bash
pip install -e '.[ocr]'
```

## Running The App

Use the packaged CLI:

```bash
pdf-control
```

Or run the development script:

```bash
scripts/dev.sh
```

You can also use Make:

```bash
make dev
```

You can set a specific port:

```bash
pdf-control --port 8000
```

You can also change the maximum upload size in megabytes:

```bash
pdf-control --max-upload-size 2048
```

## Usage

1. Open `http://127.0.0.1:8000` or the local URL shown in the terminal.
2. Choose a PDF operation from the Arabic navigation menu.
3. Select the required files and options.
4. Run the operation; the generated result downloads automatically.

### Non-destructive visual editing

Choose **محرر الطبقات** to work directly over a rendered page:

1. Use **إخفاء** and drag a rectangle over content that should no longer be visible.
2. Use **نص** and click the page to add replacement or supplemental text.
3. Select a layer to move it, resize it, change its color, edit its text, or delete it.
4. Navigate between pages; the editor retains each page's layers.
5. Use undo/redo, then save a new PDF when the result is ready.

Cover rectangles and new text are appended visually. They do not redact or remove the original
text layer, so this tool must not be used to permanently sanitize sensitive information.

## Page Selection Format

Page numbers are 1-based, so the first page is `1`.

- Single page: `1`
- All pages: `all` or `الكل`
- Multiple pages: `1,3,8`
- Page range: `5-7`
- Mixed format: `1,3,5-7`
- Arabic separators and semicolons are accepted, such as `1؛3` or `1،3`.

## Important Notes

- Uploaded files are processed in an isolated temporary directory and are not stored in a database.
- Temporary files are removed after the response finishes or an operation fails.
- PDF operations generate new files and do not modify the original uploads directly.
- Encrypted PDFs can be inspected for encryption status, but processing operations require a decrypted copy.
- Text replacement depends on the internal structure of the PDF. It may not work with scanned pages, image-only text, or PDFs with complex text encoding.
- Editable PDF generation can use the selectable text layer or OCR. OCR requires the optional Python dependencies and the Tesseract system package.
- Editable PDF fields are transparent by default so the generated file keeps the original page appearance. Enable "إظهار النص المكتشف داخل الحقول" only when you want the detected text to be visibly placed in the generated fields.
- Use the "طبق الأصل" tab when preserving the visual appearance matters most. It rasterizes each page as a background, so the output looks closer to the original but may be larger and less sharp at low render DPI values.
- In the "طبق الأصل" tab, keep "تحويل مربعات الاختيار إلى عناصر قابلة للنقر" enabled when the source has checkbox-style options.
- OCR quality depends on scan clarity. Typed text is usually much better than handwriting, and handwritten Arabic may produce inaccurate text.
- Added text uses standard PDF coordinates, where the origin starts at the bottom-left corner of the page.
- For better Arabic text rendering when adding text, upload a suitable TTF font or rely on fonts available on the system.

## Resource Limits

PDF Control applies conservative limits before expensive work. Override them through environment variables:

```bash
PDF_CONTROL_MAX_FILE_SIZE_MB=256
PDF_CONTROL_MAX_SESSION_SIZE_MB=512
PDF_CONTROL_MAX_PAGES=2000
PDF_CONTROL_MAX_RENDER_PAGES=250
```

The session limit applies to the combined files in one request. Rendering has a lower page limit
because page images and OCR consume substantially more memory than PDF composition.

## Project Structure

```text
.
├── pyproject.toml
├── Makefile
├── .env.example
├── requirements.txt
├── src/
│   └── pdf_control/
│       ├── cli.py
│       ├── config.py
│       ├── core.py
│       ├── logging.py
│       ├── utils.py
│       ├── api.py
│       └── static/
├── tests/
├── scripts/
├── .github/workflows/
└── docs/
```

- `src/pdf_control/api.py`: FastAPI routes and safe temporary-file handling.
- `src/pdf_control/static/`: Arabic HTML/CSS/JavaScript browser interface.
- `src/pdf_control/core.py`: stable compatibility facade for processing APIs.
- `src/pdf_control/merge.py`: composition, extraction, splitting, and rotation APIs.
- `src/pdf_control/editing.py`: text replacement and overlay APIs.
- `src/pdf_control/ocr.py`: rendering and OCR-facing APIs.
- `src/pdf_control/_engine.py`: editable forms, text-layer, OCR, and exact-look internals.
- `src/pdf_control/limits.py`: configurable resource guards.
- `src/pdf_control/cli.py`: command-line entrypoint.
- `src/pdf_control/config.py`: environment-based configuration.
- `src/pdf_control/utils.py`: shared helper functions.
- `src/pdf_control/logging.py`: logging setup.
- `scripts/dev.sh`: local development runner.
- `scripts/test.sh`: test runner.

## Browser UI Architecture

The Arabic design and migration guide for the standard HTML/CSS/JavaScript interface backed by FastAPI is available in
[`docs/FASTAPI_MIGRATION_AR.md`](docs/FASTAPI_MIGRATION_AR.md).

## Developer Commands

```bash
make install
make run
make test
make lint
make format
make check
```

The same commands are mirrored by scripts in `scripts/`.

## Testing

```bash
scripts/test.sh
```

Or:

```bash
pytest
```

## License

This project is licensed under the MIT License. See `LICENSE` for details.
