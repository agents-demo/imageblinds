"""FastAPI server: serves the JS GUI and the image-analysis endpoint."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from imageblinds import service

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"

ALLOWED_SUFFIXES = {".jpg", ".jpeg"}

app = FastAPI(title="ImageBlinds")

app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")
app.mount("/examples", StaticFiles(directory=STATIC_DIR / "examples"), name="examples")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/analyze")
async def analyze(file: Annotated[UploadFile, File()]) -> JSONResponse:
    name = file.filename or ""
    if Path(name).suffix.lower() not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail="Only .jpg images are supported.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")

    workspace = service.ensure_workspace()
    image_path = workspace / "uploads" / f"{uuid.uuid4().hex}.jpg"
    image_path.write_bytes(content)

    try:
        description = await service.describe_image(image_path)
    except Exception as exc:  # noqa: BLE001 - surface any model/backend failure to the GUI
        return JSONResponse(status_code=500, content={"error": str(exc)})

    return JSONResponse(content={"description": description})
