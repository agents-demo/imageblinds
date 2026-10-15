# edge-tts narration

Replace the robotic browser `speechSynthesis` narration with free Microsoft
neural voices via the `edge-tts` Python package, keeping `speechSynthesis` as
an offline/error fallback.

## Backend

1. `pyproject.toml`: add `"edge-tts>=6.1"` to dependencies (pure Python; no
   Dockerfile changes needed).

2. New `imageblinds/tts.py`:
   - Read voice from env `TTS_VOICE` (default `en-US-AvaNeural`).
   - Async `synthesize(text) -> bytes` using `edge_tts.Communicate` to collect
     MP3 chunks.
   - Trim/validate input; raise on empty.

3. `imageblinds/server.py`: add `GET /api/tts?text=...`
   - Reject empty/missing text (400) and text > 1000 chars (422).
   - Return MP3 `Response` with `media_type="audio/mpeg"` and
     `Cache-Control: max-age=86400` (repeat descriptions hit browser cache).
   - Catch edge-tts/network errors -> 502 JSON `{"error": ...}` so the
     frontend falls back to speechSynthesis.
   - Service worker already bypasses `/api/`, no sw.js change.

4. `.env.example`: add `TTS_VOICE=en-US-AvaNeural` with a comment
   (e.g. `en-GB-SoniaNeural`, `en-US-AndrewNeural`).

## Frontend (`static/app.js`)

5. Rework `speak(text)`:
   - Async: `fetch("/api/tts?text=" + encodeURIComponent(text))`.
   - On ok: create `new Audio(URL.createObjectURL(blob))`, keep reference,
     `.play()`; on `play()` rejection (mobile autoplay) fall back to synth.
   - On fetch error/non-ok: fall back to existing `speechSynthesis` path.
   - Track current audio element; `stopSpeaking()` pauses/cancels both audio
     and synth.

## Tests

6. `tests/test_server.py`: monkeypatch `tts.synthesize`:
   - happy path: 200, `audio/mpeg` content-type, MP3 bytes in body.
   - empty text -> 400; overlong text -> 422.
   - synthesize raising -> 502 with JSON error.
   - Existing `speechSynthesis` assertion stays (fallback remains in app.js).

## Verify

7. Run `uv lock` (updates uv.lock), `uv sync`, `uv run pytest`, `uv run ruff check`.
