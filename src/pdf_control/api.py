"""FastAPI application exposing PDF Control to a standard browser UI."""

from __future__ import annotations

import json
import logging
import secrets
import shutil
import tempfile
import threading
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse

from pdf_control import config, core, limits, utils

logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).with_name("static")
UPLOAD_CHUNK_SIZE = 1024 * 1024
MAX_FONT_SIZE = 20 * 1024 * 1024
MAX_OUTPUT_NAME_LENGTH = 255
PREVIEW_SESSION_TTL_SECONDS = 60 * 60
MAX_PREVIEW_SESSIONS = 8

app = FastAPI(
    title=config.APP_NAME,
    description="واجهة محلية لمعالجة ملفات PDF",
    version="1.1.0",
)


@dataclass(frozen=True)
class _Download:
    output: Path
    directory: Path
    filename: str
    media_type: str
    message: str | None


@dataclass
class _PreviewSession:
    directory: Path
    source: Path
    expires_at: float
    last_access: float


_preview_sessions: dict[str, _PreviewSession] = {}
_preview_sessions_lock = threading.Lock()


@app.exception_handler(ValueError)
async def value_error_handler(_request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


def _temporary_directory() -> Path:
    return Path(tempfile.mkdtemp(prefix="pdf-control-"))


def _remove_directories(directories: list[Path]) -> None:
    for directory in directories:
        shutil.rmtree(directory, ignore_errors=True)


def _cleanup_preview_sessions(now: float | None = None) -> None:
    current_time = time.monotonic() if now is None else now
    stale_directories: list[Path] = []
    with _preview_sessions_lock:
        expired = [
            token
            for token, session in _preview_sessions.items()
            if session.expires_at <= current_time
        ]
        for token in expired:
            stale_directories.append(_preview_sessions.pop(token).directory)

        overflow = max(0, len(_preview_sessions) - MAX_PREVIEW_SESSIONS + 1)
        if overflow:
            oldest = sorted(
                _preview_sessions,
                key=lambda token: _preview_sessions[token].last_access,
            )[:overflow]
            for token in oldest:
                stale_directories.append(_preview_sessions.pop(token).directory)
    _remove_directories(stale_directories)


def _register_preview_session(directory: Path, source: Path) -> str:
    _cleanup_preview_sessions()
    token = secrets.token_urlsafe(24)
    now = time.monotonic()
    with _preview_sessions_lock:
        _preview_sessions[token] = _PreviewSession(
            directory=directory,
            source=source,
            expires_at=now + PREVIEW_SESSION_TTL_SECONDS,
            last_access=now,
        )
    return token


def _preview_session_source(token: str) -> Path:
    _cleanup_preview_sessions()
    now = time.monotonic()
    with _preview_sessions_lock:
        session = _preview_sessions.get(token)
        if session is None:
            raise HTTPException(status_code=404, detail="انتهت جلسة المعاينة. اختر الملف مجددًا.")
        session.last_access = now
        session.expires_at = now + PREVIEW_SESSION_TTL_SECONDS
        return session.source


def _discard_preview_session(token: str) -> None:
    with _preview_sessions_lock:
        session = _preview_sessions.pop(token, None)
    if session is not None:
        shutil.rmtree(session.directory, ignore_errors=True)


async def _save_pdf(
    upload: UploadFile,
    directory: Path,
    internal_name: str,
    current_bytes: int = 0,
) -> tuple[Path, int]:
    path = directory / internal_name
    written = 0
    prefix = bytearray()
    try:
        with path.open("wb") as stream:
            while chunk := await upload.read(UPLOAD_CHUNK_SIZE):
                written += len(chunk)
                limits.validate_upload_size(written, current_bytes)
                if len(prefix) < 1024:
                    prefix.extend(chunk[: 1024 - len(prefix)])
                stream.write(chunk)
    finally:
        await upload.close()

    if not bytes(prefix).lstrip().startswith(b"%PDF-"):
        path.unlink(missing_ok=True)
        raise ValueError(f"{upload.filename or 'الملف'} ليس ملف PDF صالحًا.")
    return path, current_bytes + written


async def _save_optional_font(
    upload: UploadFile | None,
    directory: Path,
    current_bytes: int = 0,
) -> str | None:
    if upload is None or not upload.filename:
        return None
    path = directory / "font.ttf"
    written = 0
    signature = b""
    try:
        with path.open("wb") as stream:
            while chunk := await upload.read(UPLOAD_CHUNK_SIZE):
                written += len(chunk)
                if written > MAX_FONT_SIZE:
                    raise ValueError("يتجاوز ملف الخط الحد المسموح (20 MB).")
                limits.validate_upload_size(written, current_bytes)
                if not signature:
                    signature = chunk[:4]
                stream.write(chunk)
    finally:
        await upload.close()
    if not signature.startswith((b"\x00\x01\x00\x00", b"OTTO", b"true", b"typ1")):
        path.unlink(missing_ok=True)
        raise ValueError("ملف الخط المرفوع ليس خط TTF أو OpenType صالحًا.")
    return str(path)


def _download(
    output: Path,
    directory: Path,
    _background_tasks: BackgroundTasks,
    filename: str,
    media_type: str = "application/pdf",
    message: str | None = None,
) -> _Download:
    del _background_tasks
    if len(filename) > MAX_OUTPUT_NAME_LENGTH:
        raise ValueError("اسم الملف الناتج أطول من الحد المسموح (255 حرفًا).")
    return _Download(output, directory, filename, media_type, message)


def _download_response(download: _Download) -> Response:
    output = download.output
    directory = download.directory
    message = download.message
    safe_filename = utils.safe_name(download.filename, output.name)
    headers = {"X-PDF-Control-Message": quote(message)} if message else None
    headers = headers or {}
    headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(safe_filename)}"
    headers["Content-Length"] = str(output.stat().st_size)
    return StreamingResponse(
        _file_chunks(output, directory),
        media_type=download.media_type,
        headers=headers,
    )


async def _file_chunks(path: Path, directory: Path):
    """Yield a generated file without copying the entire result into memory."""
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(UPLOAD_CHUNK_SIZE):
                yield chunk
    finally:
        shutil.rmtree(directory, ignore_errors=True)


async def _run_download(operation: Callable[[], _Download], directory: Path) -> Response:
    try:
        download = operation()
        return _download_response(download)
    except HTTPException:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    except (ValueError, OSError) as exc:
        shutil.rmtree(directory, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        shutil.rmtree(directory, ignore_errors=True)
        logger.exception("PDF operation failed")
        raise HTTPException(status_code=500, detail="تعذّرت معالجة الملف.") from exc


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "application": config.APP_NAME}


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def browser_home() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


@app.get("/app.css", include_in_schema=False)
async def browser_css() -> Response:
    return Response((STATIC_DIR / "app.css").read_bytes(), media_type="text/css")


@app.get("/app.js", include_in_schema=False)
async def browser_javascript() -> Response:
    return Response((STATIC_DIR / "app.js").read_bytes(), media_type="text/javascript")


@app.post("/api/info")
async def pdf_info(file: Annotated[UploadFile, File(...)]) -> dict:
    directory = _temporary_directory()
    try:
        source, _ = await _save_pdf(file, directory, "input.pdf")
        info = core.get_pdf_info(source)
        info.pop("path", None)
        return info
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("PDF information inspection failed")
        raise HTTPException(status_code=400, detail="تعذّرت قراءة ملف PDF.") from exc
    finally:
        shutil.rmtree(directory, ignore_errors=True)


@app.post("/api/merge")
async def merge(
    background_tasks: BackgroundTasks,
    files: Annotated[list[UploadFile], File(...)],
    output_name: Annotated[str, Form()] = "merged.pdf",
) -> Response:
    if len(files) < 2:
        raise HTTPException(status_code=400, detail="اختر ملفين على الأقل.")
    directory = _temporary_directory()
    try:
        paths, total = [], 0
        for index, upload in enumerate(files):
            path, total = await _save_pdf(upload, directory, f"input-{index}.pdf", total)
            paths.append(path)
        output = directory / "output.pdf"
        return await _run_download(
            lambda: (
                core.merge_pdfs(paths, output),
                _download(output, directory, background_tasks, output_name),
            )[1],
            directory,
        )
    except Exception:
        if directory.exists():
            shutil.rmtree(directory, ignore_errors=True)
        raise


@app.post("/api/extract")
async def extract(
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File(...)],
    pages: Annotated[str, Form()] = "الكل",
    output_name: Annotated[str, Form()] = "extracted.pdf",
) -> Response:
    directory = _temporary_directory()
    try:
        source, _ = await _save_pdf(file, directory, "input.pdf")
        output = directory / "output.pdf"
        return await _run_download(
            lambda: (
                core.extract_pages(source, output, utils.normalize_page_spec(pages)),
                _download(output, directory, background_tasks, output_name),
            )[1],
            directory,
        )
    except Exception:
        if directory.exists():
            shutil.rmtree(directory, ignore_errors=True)
        raise


@app.post("/api/split")
async def split(
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File(...)],
    output_name: Annotated[str, Form()] = "split_pages.zip",
) -> Response:
    directory = _temporary_directory()
    try:
        source, _ = await _save_pdf(file, directory, "input.pdf")
        pages_dir = directory / "pages"
        output = directory / "output.zip"

        def operation() -> Response:
            core.split_pdf(source, pages_dir)
            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
                for path in sorted(pages_dir.glob("*.pdf")):
                    archive.write(path, arcname=path.name)
            return _download(output, directory, background_tasks, output_name, "application/zip")

        return await _run_download(operation, directory)
    except Exception:
        if directory.exists():
            shutil.rmtree(directory, ignore_errors=True)
        raise


@app.post("/api/rotate")
async def rotate(
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File(...)],
    pages: Annotated[str, Form()] = "الكل",
    angle: Annotated[int, Form()] = 90,
    output_name: Annotated[str, Form()] = "rotated.pdf",
) -> Response:
    directory = _temporary_directory()
    try:
        source, _ = await _save_pdf(file, directory, "input.pdf")
        output = directory / "output.pdf"
        return await _run_download(
            lambda: (
                core.rotate_pages(source, output, utils.normalize_page_spec(pages), angle),
                _download(output, directory, background_tasks, output_name),
            )[1],
            directory,
        )
    except Exception:
        if directory.exists():
            shutil.rmtree(directory, ignore_errors=True)
        raise


@app.post("/api/insert")
async def insert(
    background_tasks: BackgroundTasks,
    base_file: Annotated[UploadFile, File(...)],
    insert_file: Annotated[UploadFile, File(...)],
    after_page: Annotated[int, Form()] = 1,
    output_name: Annotated[str, Form()] = "inserted.pdf",
) -> Response:
    directory = _temporary_directory()
    try:
        base, total = await _save_pdf(base_file, directory, "base.pdf")
        addition, _ = await _save_pdf(insert_file, directory, "insert.pdf", total)
        output = directory / "output.pdf"
        return await _run_download(
            lambda: (
                core.insert_pdf_after_page(base, addition, output, after_page),
                _download(output, directory, background_tasks, output_name),
            )[1],
            directory,
        )
    except Exception:
        if directory.exists():
            shutil.rmtree(directory, ignore_errors=True)
        raise


@app.post("/api/replace-text")
async def replace_text(
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File(...)],
    find_text: Annotated[str, Form()],
    replace_text: Annotated[str, Form()] = "",
    pages: Annotated[str, Form()] = "",
    output_name: Annotated[str, Form()] = "edited.pdf",
) -> Response:
    directory = _temporary_directory()
    try:
        source, _ = await _save_pdf(file, directory, "input.pdf")
        output = directory / "output.pdf"

        def operation() -> Response:
            count = core.replace_text_in_pdf(
                source,
                output,
                find_text,
                replace_text,
                utils.normalize_page_spec(pages) or None,
            )
            return _download(
                output,
                directory,
                background_tasks,
                output_name,
                message=f"تم استبدال {count} موضع/مواضع.",
            )

        return await _run_download(operation, directory)
    except Exception:
        if directory.exists():
            shutil.rmtree(directory, ignore_errors=True)
        raise


@app.post("/api/add-text")
async def add_text(
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File(...)],
    text: Annotated[str, Form()],
    page: Annotated[int, Form()] = 1,
    x: Annotated[float, Form()] = 120,
    y: Annotated[float, Form()] = 100,
    font_size: Annotated[int, Form()] = 16,
    output_name: Annotated[str, Form()] = "with_text.pdf",
    font: Annotated[UploadFile | None, File()] = None,
) -> Response:
    directory = _temporary_directory()
    try:
        source, total = await _save_pdf(file, directory, "input.pdf")
        font_path = await _save_optional_font(font, directory, total)
        output = directory / "output.pdf"
        return await _run_download(
            lambda: (
                core.add_text_overlay(source, output, page, text, x, y, font_size, font_path),
                _download(output, directory, background_tasks, output_name),
            )[1],
            directory,
        )
    except Exception:
        if directory.exists():
            shutil.rmtree(directory, ignore_errors=True)
        raise


def _preview_image_response(
    image: bytes,
    page_count: int,
    width: float,
    height: float,
    session_token: str | None = None,
) -> Response:
    headers = {
        "X-Page-Count": str(page_count),
        "X-Page-Width": str(width),
        "X-Page-Height": str(height),
        "Cache-Control": "no-store",
    }
    if session_token:
        headers["X-Preview-Session"] = session_token
    return Response(image, media_type="image/png", headers=headers)


async def _render_preview(source: Path, page: int, dpi: int) -> Response:
    image, page_count, width, height = core.render_editor_page(source, page, dpi)
    return _preview_image_response(image, page_count, width, height)


@app.post("/api/layer-preview")
async def layer_preview(
    file: Annotated[UploadFile, File(...)],
    page: Annotated[int, Form()] = 1,
    dpi: Annotated[int, Form()] = 120,
) -> Response:
    directory = _temporary_directory()
    try:
        source, _ = await _save_pdf(file, directory, "input.pdf")
        return await _render_preview(source, page, dpi)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("PDF editor preview failed")
        raise HTTPException(status_code=400, detail="تعذّرت معاينة صفحة PDF.") from exc
    finally:
        shutil.rmtree(directory, ignore_errors=True)


@app.post("/api/preview-session")
async def create_preview_session(
    file: Annotated[UploadFile, File(...)],
    dpi: Annotated[int, Form()] = 96,
) -> Response:
    directory = _temporary_directory()
    try:
        source, _ = await _save_pdf(file, directory, "input.pdf")
        image, page_count, width, height = core.render_editor_page(source, 1, dpi)
        token = _register_preview_session(directory, source)
        return _preview_image_response(image, page_count, width, height, token)
    except ValueError as exc:
        shutil.rmtree(directory, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        shutil.rmtree(directory, ignore_errors=True)
        logger.exception("PDF preview session creation failed")
        raise HTTPException(status_code=400, detail="تعذّرت معاينة صفحة PDF.") from exc


@app.post("/api/preview-page")
async def preview_session_page(
    session: Annotated[str, Form()],
    page: Annotated[int, Form()] = 1,
    dpi: Annotated[int, Form()] = 96,
) -> Response:
    try:
        source = _preview_session_source(session)
        return await _render_preview(source, page, dpi)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("PDF preview session page failed")
        raise HTTPException(status_code=400, detail="تعذّرت معاينة صفحة PDF.") from exc


@app.delete("/api/preview-session/{token}", status_code=204)
async def close_preview_session(token: str) -> Response:
    _discard_preview_session(token)
    return Response(status_code=204)


@app.post("/api/layer-edit")
async def layer_edit(
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File(...)],
    edits: Annotated[str, Form()],
    deleted_pages: Annotated[str, Form()] = "[]",
    output_name: Annotated[str, Form()] = "layered.pdf",
    font: Annotated[UploadFile | None, File()] = None,
) -> Response:
    directory = _temporary_directory()
    try:
        source, total = await _save_pdf(file, directory, "input.pdf")
        font_path = await _save_optional_font(font, directory, total)
        output = directory / "output.pdf"

        def operation() -> Response:
            count = core.apply_visual_layers(source, output, edits, font_path, deleted_pages)
            deleted_count = len(set(json.loads(deleted_pages)))
            message = f"تم حفظ {count} طبقة"
            if deleted_count:
                message += f" وحذف {deleted_count} صفحة"
            message += "."
            return _download(
                output,
                directory,
                background_tasks,
                output_name,
                message=message,
            )

        return await _run_download(operation, directory)
    except Exception:
        if directory.exists():
            shutil.rmtree(directory, ignore_errors=True)
        raise


def _editable_download(
    *,
    source: Path,
    output: Path,
    exact: bool,
    pages: str,
    max_fields: int,
    use_ocr: bool,
    ocr_language: str,
    ocr_dpi: int,
    ocr_min_confidence: float,
    show_field_values: bool,
    render_dpi: int,
    detect_checkboxes: bool,
    max_checkboxes: int,
) -> int:
    arguments = dict(
        input_pdf=source,
        output_pdf=output,
        pages=utils.normalize_page_spec(pages) or None,
        max_fields=max_fields,
        use_ocr=use_ocr,
        ocr_language=ocr_language,
        ocr_dpi=ocr_dpi,
        ocr_min_confidence=ocr_min_confidence,
        show_field_values=show_field_values,
    )
    if exact:
        arguments.update(
            render_dpi=render_dpi,
            detect_checkboxes=detect_checkboxes,
            max_checkboxes=max_checkboxes,
        )
        return core.create_exact_editable_pdf(**arguments)
    return core.create_editable_pdf(**arguments)


def _validate_editable_options(
    *,
    max_fields: int,
    ocr_dpi: int,
    ocr_min_confidence: float,
    render_dpi: int,
    max_checkboxes: int,
    exact: bool,
) -> None:
    if not 1 <= max_fields <= 3000:
        raise ValueError("يجب أن يكون عدد الحقول بين 1 و3000.")
    if not 72 <= ocr_dpi <= 400:
        raise ValueError("يجب أن تكون دقة OCR بين 72 و400 DPI.")
    if not 0 <= ocr_min_confidence <= 100:
        raise ValueError("يجب أن تكون ثقة OCR بين 0 و100.")
    if exact and not 72 <= render_dpi <= 400:
        raise ValueError("يجب أن تكون دقة الخلفية بين 72 و400 DPI.")
    if exact and not 0 <= max_checkboxes <= 1000:
        raise ValueError("يجب أن يكون عدد مربعات الاختيار بين 0 و1000.")


async def _editable_response(
    *,
    background_tasks: BackgroundTasks,
    file: UploadFile,
    exact: bool,
    pages: str,
    max_fields: int,
    use_ocr: bool,
    ocr_language: str,
    ocr_dpi: int,
    ocr_min_confidence: float,
    show_field_values: bool,
    render_dpi: int,
    detect_checkboxes: bool,
    max_checkboxes: int,
    output_name: str,
) -> Response:
    _validate_editable_options(
        max_fields=max_fields,
        ocr_dpi=ocr_dpi,
        ocr_min_confidence=ocr_min_confidence,
        render_dpi=render_dpi,
        max_checkboxes=max_checkboxes,
        exact=exact,
    )
    directory = _temporary_directory()
    try:
        source, _ = await _save_pdf(file, directory, "input.pdf")
        output = directory / "output.pdf"

        def operation() -> Response:
            count = _editable_download(
                source=source,
                output=output,
                exact=exact,
                pages=pages,
                max_fields=max_fields,
                use_ocr=use_ocr,
                ocr_language=ocr_language,
                ocr_dpi=ocr_dpi,
                ocr_min_confidence=ocr_min_confidence,
                show_field_values=show_field_values,
                render_dpi=render_dpi,
                detect_checkboxes=detect_checkboxes,
                max_checkboxes=max_checkboxes,
            )
            return _download(
                output,
                directory,
                background_tasks,
                output_name,
                message=f"تم إنشاء {count} حقل/حقول قابلة للتعديل.",
            )

        return await _run_download(operation, directory)
    except Exception:
        if directory.exists():
            shutil.rmtree(directory, ignore_errors=True)
        raise


@app.post("/api/editable")
async def editable(
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File(...)],
    pages: Annotated[str, Form()] = "",
    max_fields: Annotated[int, Form()] = 300,
    use_ocr: Annotated[bool, Form()] = False,
    ocr_language: Annotated[str, Form()] = "eng",
    ocr_dpi: Annotated[int, Form()] = 200,
    ocr_min_confidence: Annotated[float, Form()] = 30,
    show_field_values: Annotated[bool, Form()] = False,
    output_name: Annotated[str, Form()] = "editable.pdf",
) -> Response:
    return await _editable_response(
        background_tasks=background_tasks,
        file=file,
        exact=False,
        pages=pages,
        max_fields=max_fields,
        use_ocr=use_ocr,
        ocr_language=ocr_language,
        ocr_dpi=ocr_dpi,
        ocr_min_confidence=ocr_min_confidence,
        show_field_values=show_field_values,
        render_dpi=200,
        detect_checkboxes=False,
        max_checkboxes=0,
        output_name=output_name,
    )


@app.post("/api/exact-editable")
async def exact_editable(
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File(...)],
    pages: Annotated[str, Form()] = "",
    max_fields: Annotated[int, Form()] = 500,
    use_ocr: Annotated[bool, Form()] = False,
    ocr_language: Annotated[str, Form()] = "eng",
    ocr_dpi: Annotated[int, Form()] = 250,
    ocr_min_confidence: Annotated[float, Form()] = 25,
    show_field_values: Annotated[bool, Form()] = False,
    render_dpi: Annotated[int, Form()] = 200,
    detect_checkboxes: Annotated[bool, Form()] = True,
    max_checkboxes: Annotated[int, Form()] = 300,
    output_name: Annotated[str, Form()] = "exact_editable.pdf",
) -> Response:
    return await _editable_response(
        background_tasks=background_tasks,
        file=file,
        exact=True,
        pages=pages,
        max_fields=max_fields,
        use_ocr=use_ocr,
        ocr_language=ocr_language,
        ocr_dpi=ocr_dpi,
        ocr_min_confidence=ocr_min_confidence,
        show_field_values=show_field_values,
        render_dpi=render_dpi,
        detect_checkboxes=detect_checkboxes,
        max_checkboxes=max_checkboxes,
        output_name=output_name,
    )
