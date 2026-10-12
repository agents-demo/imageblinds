"""Endpoint tests for the upload API (service stubbed — no model calls)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from imageblinds import service
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


def test_index_includes_text_to_speech_controls(monkeypatch):
    client = _client(monkeypatch)
    page = client.get("/")
    assert page.status_code == 200
    assert "Read aloud" in page.text
    assert 'aria-live="polite"' in page.text

    script = client.get("/assets/app.js")
    assert script.status_code == 200
    assert "speechSynthesis" in script.text
