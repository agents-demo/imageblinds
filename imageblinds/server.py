"""FastAPI server: serves the JS GUI and the image-analysis endpoint.

On startup it prints the addresses the app can be reached at (from another
machine on the network — typically a phone), and warns when the HTTPS
certificate does not cover the current address (the IP can change between
Wi-Fi connections).
"""

from __future__ import annotations

import asyncio
import re
import socket
import subprocess
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from imageblinds import service, tts

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"
CERT_PATH = ROOT / "certs" / "local.crt"

ALLOWED_SUFFIXES = {".jpg", ".jpeg"}

MAX_QUESTION_CHARS = 500


def _is_wsl() -> bool:
    try:
        return "microsoft" in (Path("/proc/version").read_text().lower() if Path("/proc/version").exists() else "")
    except OSError:
        return False


def _windows_wifi_ips() -> list[str]:
    """Under WSL the phone reaches the Windows host, not the WSL IP."""
    if not _is_wsl():
        return []
    exe = Path("/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")
    if not exe.is_file():
        return []
    try:
        proc = subprocess.run(
            [
                str(exe),
                "-NoProfile",
                "-Command",
                "Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -match 'Wi-Fi' } "
                "| Select-Object -ExpandProperty IPAddress",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    ips = []
    for line in proc.stdout.replace("\r", "").splitlines():
        ip = line.strip()
        if ip and not ip.startswith(("127.", "169.254.")):
            ips.append(ip)
    return ips


def _local_ips() -> list[str]:
    """Best-effort list of this machine's IPv4 addresses (LAN-facing first)."""
    ips: list[str] = []
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        ip = probe.getsockname()[0]
        if ip and not ip.startswith(("127.", "169.254.")):
            ips.append(ip)
    except OSError:
        pass
    finally:
        probe.close()
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if ip not in ips and not ip.startswith(("127.", "169.254.")):
                ips.append(ip)
    except OSError:
        pass
    return ips


def _cert_ips() -> list[str]:
    """IP addresses covered by the HTTPS certificate's subjectAltName."""
    if not CERT_PATH.is_file():
        return []
    try:
        proc = subprocess.run(
            ["openssl", "x509", "-in", str(CERT_PATH), "-noout", "-ext", "subjectAltName"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return re.findall(r"IP Address:([\d.]+)", proc.stdout)


def connection_info() -> str:
    """The startup banner: where to connect from, and cert-coverage notes."""
    ips = _windows_wifi_ips() if _is_wsl() else _local_ips()
    lines = ["ImageBlinds is running. Connect from:"]
    if _is_wsl():
        lines.append("  (WSL: the addresses below are the Windows host's Wi-Fi addresses)")
    if not ips:
        lines.append("  No LAN address detected (offline?). Local use: http://localhost:8080")
    for ip in ips:
        lines.append(f"  Phone (HTTPS, install as app): https://{ip}:8000")
        lines.append(f"  Phone (plain HTTP, no install): http://{ip}:8080")
    cert_ips = _cert_ips()
    if cert_ips:
        covered = set(cert_ips) & set(ips)
        if not covered:
            lines.append(
                "  WARNING: the certificate covers " + ", ".join(cert_ips)
                + " but the current address(es) are not included."
                + " The IP changed - regenerate certs/local.crt (see README) and re-install it on the phone."
            )
        else:
            lines.append("  Certificate covers: " + ", ".join(cert_ips))
    else:
        lines.append("  No certificate found at certs/local.crt - HTTPS will not work (see README).")
    return "\n".join(lines)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    print(connection_info(), flush=True)
    yield


app = FastAPI(title="ImageBlinds", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://agents-demo.github.io",
        "http://localhost:8000",
        "http://localhost:8080",
        "http://127.0.0.1:8000",
        "http://127.0.0.1:8080",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")
app.mount("/examples", StaticFiles(directory=STATIC_DIR / "examples"), name="examples")
app.mount("/icons", StaticFiles(directory=STATIC_DIR / "icons"), name="icons")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/manifest.json")
async def manifest() -> FileResponse:
    return FileResponse(STATIC_DIR / "manifest.json", media_type="application/manifest+json")


@app.get("/sw.js")
async def service_worker() -> FileResponse:
    return FileResponse(STATIC_DIR / "sw.js", media_type="application/javascript")


@app.get("/ca.crt")
async def ca_cert() -> FileResponse:
    if not CERT_PATH.is_file():
        raise HTTPException(status_code=404, detail="Local certificate not generated yet (see README).")
    return FileResponse(
        CERT_PATH,
        media_type="application/x-x509-ca-cert",
        filename="imageblinds-ca.crt",
    )


async def _run_until_disconnect(request: Request, task: asyncio.Task) -> bool:
    """Await ``task`` but cancel it as soon as the client disconnects.

    Returns ``True`` when the client is still connected and ``task`` finished,
    ``False`` when the client went away and the task was cancelled.
    """
    while not task.done():
        if await request.is_disconnected():
            task.cancel()
            return False
        await asyncio.sleep(0.2)
    return True


@app.get("/api/tts")
async def tts_audio(request: Request, text: str = "") -> Response:
    """Synthesize narration audio with a neural voice (edge-tts)."""
    if not text.strip():
        raise HTTPException(status_code=400, detail="Missing text to narrate.")
    if len(text) > tts.MAX_CHARS:
        raise HTTPException(status_code=422, detail=f"Text too long (max {tts.MAX_CHARS} chars).")
    task = asyncio.create_task(tts.synthesize(text))
    if not await _run_until_disconnect(request, task):
        return JSONResponse(status_code=499, content={"error": "Client disconnected."})
    try:
        audio = task.result()
    except Exception as exc:  # noqa: BLE001 - any network/edge-tts failure should trigger fallback
        return JSONResponse(status_code=502, content={"error": str(exc)})
    if not audio:
        return JSONResponse(status_code=502, content={"error": "TTS returned no audio."})
    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )


async def _save_upload(file: UploadFile) -> tuple[tuple[int, str] | None, Path | None]:
    """Validate and persist an uploaded image; returns ((status, detail), path)."""
    name = file.filename or ""
    if Path(name).suffix.lower() not in ALLOWED_SUFFIXES:
        return (400, "Only .jpg images are supported."), None
    content = await file.read()
    if not content:
        return (422, "Uploaded file is empty."), None
    workspace = service.ensure_workspace()
    image_path = workspace / "uploads" / f"{uuid.uuid4().hex}.jpg"
    image_path.write_bytes(content)
    return None, image_path


@app.post("/api/analyze")
async def analyze(request: Request, file: Annotated[UploadFile, File()]) -> JSONResponse:
    failure, image_path = await _save_upload(file)
    if failure:
        raise HTTPException(status_code=failure[0], detail=failure[1])
    assert image_path is not None

    task = asyncio.create_task(service.describe_image(image_path))
    if not await _run_until_disconnect(request, task):
        return JSONResponse(status_code=499, content={"error": "Client disconnected."})
    try:
        description = task.result()
    except Exception as exc:  # noqa: BLE001 - surface any model/backend failure to the GUI
        return JSONResponse(status_code=500, content={"error": str(exc)})

    return JSONResponse(content={"description": description})


@app.post("/api/ask")
async def ask(
    request: Request,
    file: Annotated[UploadFile, File()],
    question: Annotated[str, Form()] = "",
) -> JSONResponse:
    """Answer a follow-up question about an uploaded image."""
    question = question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Missing question.")
    if len(question) > MAX_QUESTION_CHARS:
        raise HTTPException(status_code=422, detail=f"Question too long (max {MAX_QUESTION_CHARS} chars).")

    failure, image_path = await _save_upload(file)
    if failure:
        raise HTTPException(status_code=failure[0], detail=failure[1])
    assert image_path is not None

    task = asyncio.create_task(service.answer_question(image_path, question))
    if not await _run_until_disconnect(request, task):
        return JSONResponse(status_code=499, content={"error": "Client disconnected."})
    try:
        answer = task.result()
    except Exception as exc:  # noqa: BLE001 - surface any model/backend failure to the GUI
        return JSONResponse(status_code=500, content={"error": str(exc)})

    return JSONResponse(content={"answer": answer})
