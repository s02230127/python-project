"""Веб-интерфейс для FileOptimizer с ручным управлением шаблонами."""

import json
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from jinja2 import Environment, FileSystemLoader, select_autoescape
from babel.support import Translations

from .config import (
    TEMPLATES_DIR,
    STATIC_DIR,
    LOCALES_DIR,
    DOCS_DIR,
    JOBS_BASE_DIR,
    MAX_UPLOAD_SIZE,
    LANGUAGES,
    DEFAULT_LANGUAGE,
)
from fileoptimizer.storage import StorageService
from fileoptimizer.image_optimizer import ImageOptimizer
from fileoptimizer.archive_service import ArchiveService
from fileoptimizer.exceptions import (
    FileOptimizerError,
    UnsupportedFormatError,
    OptimizationError,
    StorageError,
    ArchiveCreationError,
)

app = FastAPI(title="FileOptimizer", version="0.1.0")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

if DOCS_DIR.exists():
    app.mount("/documentation", StaticFiles(directory=DOCS_DIR, html=True), name="docs")
else:
    print("Warning: Documentation not built. Run 'sphinx-build -b html docs/source docs/_build/html'")

env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(['html', 'xml']),
    cache_size=0,
)

# ---------- Сервисы ----------
storage_service = StorageService(base_dir=JOBS_BASE_DIR)
image_optimizer = ImageOptimizer()
archive_service = ArchiveService()

# ---------- Вспомогательные функции для переводов ----------
def load_translations(lang: str) -> Translations:
    """Загружает переводы для языка через Babel."""
    try:
        return Translations.load(LOCALES_DIR, [lang])
    except Exception:
        return Translations()

def gettext(request: Request, key: str) -> str:
    """Возвращает перевод строки для текущего языка."""
    translations = getattr(request.state, "translations", None)
    if translations:
        return translations.gettext(key)
    return key

def render_template(request: Request, template_name: str, context: dict = None) -> HTMLResponse:
    """Рендерит шаблон с добавлением функции перевода и объекта request."""
    if context is None:
        context = {}
    context.setdefault("request", request)
    context["_"] = lambda key: gettext(request, key)
    template = env.get_template(template_name)
    return HTMLResponse(content=template.render(**context))

# ---------- Middleware для локализации ----------
@app.middleware("http")
async def set_locale(request: Request, call_next):
    """Загружает переводы для языка из куки/параметра и сохраняет в request.state."""
    lang = request.cookies.get("lang")
    if not lang:
        lang = request.query_params.get("lang", DEFAULT_LANGUAGE)
    if lang not in LANGUAGES:
        lang = DEFAULT_LANGUAGE

    request.state.lang = lang
    request.state.translations = load_translations(lang)

    response = await call_next(request)
    return response

# ---------- Обработчики ошибок ----------
@app.exception_handler(FileOptimizerError)
async def file_optimizer_exception_handler(request: Request, exc: FileOptimizerError):
    return render_template(request, "error.html", {"error": str(exc)}, status_code=400)

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return render_template(request, "error.html", {"error": exc.detail}, status_code=exc.status_code)

# ---------- Переключение языка ----------
@app.get("/set_lang")
async def set_lang(lang: str, redirect: str = "/"):
    if lang not in LANGUAGES:
        lang = DEFAULT_LANGUAGE
    response = RedirectResponse(url=redirect, status_code=303)
    response.set_cookie("lang", lang, max_age=3600*24*30)
    return response

# ---------- Главная страница ----------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return render_template(request, "index.html")

# ---------- Оптимизация изображений ----------
@app.get("/image", response_class=HTMLResponse)
async def image_form(request: Request):
    return render_template(request, "image_form.html")

@app.post("/image", response_class=HTMLResponse)
async def process_image(
    request: Request,
    file: UploadFile = File(...),
    output_format: str = Form("webp"),
    quality: int = Form(75),
    max_width: Optional[int] = Form(None),
    max_height: Optional[int] = Form(None),
    contrast: float = Form(1.0),
    sharpness: float = Form(1.0),
    brightness: float = Form(1.0),
):
    try:
        content = await file.read()
        if len(content) > MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail="File too large")

        job_dir = storage_service.create_job_dir()
        input_dir = storage_service.get_input_dir(job_dir)

        temp_path = input_dir / file.filename
        with open(temp_path, "wb") as f:
            f.write(content)

        result = image_optimizer.optimize(
            input_path=temp_path,
            output_dir=storage_service.get_output_dir(job_dir),
            output_format=output_format,
            quality=quality,
            max_width=max_width if max_width and max_width > 0 else None,
            max_height=max_height if max_height and max_height > 0 else None,
            contrast_factor=contrast,
            sharpness_factor=sharpness,
            brightness_factor=brightness,
        )

        metadata = {
            "original_size": result.size_info.original_size,
            "processed_size": result.size_info.processed_size,
            "saved_percent": result.size_info.saved_percent,
            "width": result.width,
            "height": result.height,
            "output_format": result.output_format,
        }
        meta_path = job_dir / "output" / "meta.json"
        with open(meta_path, "w") as f:
            json.dump(metadata, f)

        return RedirectResponse(
            url=f"/result/{job_dir.name}?type=image",
            status_code=303
        )
    except (UnsupportedFormatError, OptimizationError, ValueError) as e:
        return render_template(request, "image_form.html", {"error": str(e)}, status_code=400)
    except StorageError as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------- Архиватор ----------
@app.get("/archive", response_class=HTMLResponse)
async def archive_form(request: Request):
    return render_template(request, "archive_form.html")

@app.post("/archive", response_class=HTMLResponse)
async def process_archive(
    request: Request,
    files: List[UploadFile] = File(...),
    archive_format: str = Form("zip"),
    archive_name: str = Form("archive"),
):
    try:
        if not files or len(files) == 0:
            raise ValueError("No files uploaded")

        job_dir = storage_service.create_job_dir()
        input_dir = storage_service.get_input_dir(job_dir)

        input_paths = []
        for uploaded_file in files:
            if uploaded_file.filename == "":
                continue
            content = await uploaded_file.read()
            if len(content) > MAX_UPLOAD_SIZE:
                raise HTTPException(status_code=413, detail=f"File {uploaded_file.filename} too large")
            file_path = input_dir / uploaded_file.filename
            with open(file_path, "wb") as f:
                f.write(content)
            input_paths.append(file_path)

        if not input_paths:
            raise ValueError("No valid files to archive")

        result = archive_service.create_archive(
            input_paths=input_paths,
            output_dir=storage_service.get_output_dir(job_dir),
            archive_name=archive_name,
            archive_format=archive_format,
        )

        metadata = {
            "original_size": result.size_info.original_size,
            "processed_size": result.size_info.processed_size,
            "saved_percent": result.size_info.saved_percent,
            "files_count": result.files_count,
            "archive_format": result.archive_format,
        }
        meta_path = job_dir / "output" / "meta.json"
        with open(meta_path, "w") as f:
            json.dump(metadata, f)

        return RedirectResponse(
            url=f"/result/{job_dir.name}?type=archive",
            status_code=303
        )
    except (UnsupportedFormatError, ArchiveCreationError, ValueError) as e:
        return render_template(request, "archive_form.html", {"error": str(e)}, status_code=400)
    except StorageError as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------- Страница результата ----------
@app.get("/result/{job_id}", response_class=HTMLResponse)
async def show_result(request: Request, job_id: str, type: str):
    job_dir = JOBS_BASE_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="Job not found")

    output_dir = storage_service.get_output_dir(job_dir)
    result_files = [f for f in output_dir.glob("*") if f.name != "meta.json"]
    if not result_files:
        raise HTTPException(status_code=404, detail="Result file not found")
    result_file = result_files[0]

    meta_path = output_dir / "meta.json"
    metadata = {}
    if meta_path.exists():
        with open(meta_path) as f:
            metadata = json.load(f)

    context = {
        "job_id": job_id,
        "result_file": result_file.name,
        "file_size": result_file.stat().st_size,
        "result_type": type,
        "metadata": metadata,
    }
    return render_template(request, "result.html", context)

# ---------- Скачивание и очистка ----------
@app.get("/download/{job_id}/{filename}")
async def download_result(
    request: Request,
    job_id: str,
    filename: str,
    background_tasks: BackgroundTasks,
):
    job_dir = JOBS_BASE_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="Job not found")

    file_path = job_dir / "output" / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    def cleanup():
        try:
            storage_service.cleanup_job_dir(job_dir)
        except Exception as e:
            print(f"Cleanup error: {e}")

    background_tasks.add_task(cleanup)

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream"
    )

# ---------- Точка входа ----------
def main():
    import uvicorn
    uvicorn.run("web.web:app", host="0.0.0.0", port=8000, reload=True)

if __name__ == "__main__":
    main()