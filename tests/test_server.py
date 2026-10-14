"""Endpoint tests for the upload API (service stubbed — no model calls)."""

from __future__ import annotations

import subprocess

from fastapi.testclient import TestClient

from imageblinds import server, service, tts
from imageblinds.server import app


async def _fake_describe(image_path):
    assert str(image_path).endswith(".jpg")
    return "This image shows a chair."


def _client(monkeypatch):
    monkeypatch.setattr(service, "describe_image", _fake_describe)
    return TestClient(app)


def test_analyze_returns_description(monkeypatch):
    client = _client(monkeypatch)
    response = client.post(
        "/api/analyze",
        files={"file": ("chair.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")},
    )
    assert response.status_code == 200
    assert response.json() == {"description": "This image shows a chair."}


def test_analyze_rejects_non_jpg(monkeypatch):
    client = _client(monkeypatch)
    response = client.post(
        "/api/analyze",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 400


def test_analyze_rejects_empty_upload(monkeypatch):
    client = _client(monkeypatch)
    response = client.post(
        "/api/analyze",
        files={"file": ("chair.jpg", b"", "image/jpeg")},
    )
    assert response.status_code == 422


def test_analyze_requires_file(monkeypatch):
    client = _client(monkeypatch)
    response = client.post("/api/analyze")
    assert response.status_code == 422


def test_index_serves_gui(monkeypatch):
    client = _client(monkeypatch)
    response = client.get("/")
    assert response.status_code == 200
    assert "ImageBlinds" in response.text


def test_tts_returns_mp3(monkeypatch):
    async def _fake_synthesize(text):
        return b"ID3fake-mp3-bytes"

    monkeypatch.setattr(tts, "synthesize", _fake_synthesize)
    client = _client(monkeypatch)
    response = client.get("/api/tts", params={"text": "This image shows a chair."})
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert "max-age" in response.headers["cache-control"]
    assert response.content == b"ID3fake-mp3-bytes"


def test_tts_rejects_empty_text(monkeypatch):
    client = _client(monkeypatch)
    assert client.get("/api/tts", params={"text": "   "}).status_code == 400
    assert client.get("/api/tts").status_code == 400


def test_tts_rejects_overlong_text(monkeypatch):
    client = _client(monkeypatch)
    response = client.get("/api/tts", params={"text": "x" * (tts.MAX_CHARS + 1)})
    assert response.status_code == 422


def test_tts_error_returns_502(monkeypatch):
    async def _failing_synthesize(text):
        raise ConnectionError("no network")

    monkeypatch.setattr(tts, "synthesize", _failing_synthesize)
    client = _client(monkeypatch)
    response = client.get("/api/tts", params={"text": "hello"})
    assert response.status_code == 502
    assert "error" in response.json()


def test_index_includes_camera_controls(monkeypatch):
    client = _client(monkeypatch)
    page = client.get("/")
    assert page.status_code == 200
    assert 'id="shutter-btn"' in page.text
    assert 'id="photo-btn"' in page.text
    assert 'aria-live="polite"' in page.text

    script = client.get("/assets/app.js")
    assert script.status_code == 200
    assert "speechSynthesis" in script.text
    assert "/api/tts" in script.text


def test_index_links_manifest_and_registers_worker(monkeypatch):
    client = _client(monkeypatch)
    page = client.get("/")
    assert page.status_code == 200
    assert 'rel="manifest"' in page.text
    assert 'name="theme-color"' in page.text
    assert "cert-banner" in page.text

    script = client.get("/assets/app.js")
    assert "serviceWorker" in script.text
    assert "/sw.js" in script.text


def test_manifest_served(monkeypatch):
    client = _client(monkeypatch)
    response = client.get("/manifest.json")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/manifest+json")
    assert "standalone" in response.text
    assert "icon-512.png" in response.text


def test_service_worker_served(monkeypatch):
    client = _client(monkeypatch)
    response = client.get("/sw.js")
    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
    assert "CACHE" in response.text


def test_icons_served(monkeypatch):
    client = _client(monkeypatch)
    for name in ("icon-192.png", "icon-512.png", "maskable-192.png"):
        response = client.get(f"/icons/{name}")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"


def test_connection_info_lists_phone_addresses(monkeypatch):
    monkeypatch.setattr(server, "_is_wsl", lambda: False)
    monkeypatch.setattr(server, "_local_ips", lambda: ["10.1.2.3"])
    monkeypatch.setattr(server, "_cert_ips", lambda: ["10.1.2.3"])

    info = server.connection_info()

    assert "https://10.1.2.3:8000" in info
    assert "http://10.1.2.3:8080" in info
    assert "WARNING" not in info


def test_connection_info_warns_when_cert_does_not_cover_ip(monkeypatch):
    monkeypatch.setattr(server, "_is_wsl", lambda: False)
    monkeypatch.setattr(server, "_local_ips", lambda: ["10.9.9.9"])
    monkeypatch.setattr(server, "_cert_ips", lambda: ["10.1.2.3"])

    info = server.connection_info()

    assert "WARNING" in info
    assert "10.9.9.9" in info


def test_connection_info_notes_missing_cert(monkeypatch):
    monkeypatch.setattr(server, "_is_wsl", lambda: False)
    monkeypatch.setattr(server, "_local_ips", lambda: [])
    monkeypatch.setattr(server, "_cert_ips", lambda: [])

    info = server.connection_info()

    assert "certificate" in info.lower() or "cert" in info.lower()


def test_cert_ips_parses_subject_alt_name(tmp_path, monkeypatch):
    cert = tmp_path / "local.crt"
    key = tmp_path / "local.key"
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(key), "-out", str(cert), "-days", "1",
            "-subj", "/CN=test",
            "-addext", "subjectAltName=IP:10.20.30.40,DNS:localhost",
        ],
        capture_output=True,
        check=True,
    )
    monkeypatch.setattr(server, "CERT_PATH", cert)

    assert server._cert_ips() == ["10.20.30.40"]


def test_cert_ips_empty_for_missing_cert(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "CERT_PATH", tmp_path / "nope.crt")

    assert server._cert_ips() == []


def test_local_ips_are_plain_ipv4():
    ips = server._local_ips()
    for ip in ips:
        assert not ip.startswith(("127.", "169.254."))
        parts = ip.split(".")
        assert len(parts) == 4 and all(part.isdigit() for part in parts)


def test_startup_banner_printed(capsys, monkeypatch):
    monkeypatch.setattr(server, "_is_wsl", lambda: False)
    monkeypatch.setattr(server, "_local_ips", lambda: ["10.1.2.3"])
    monkeypatch.setattr(server, "_cert_ips", lambda: ["10.1.2.3"])

    with TestClient(app) as client:
        client.get("/")

    captured = capsys.readouterr()
    assert "https://10.1.2.3:8000" in captured.out
