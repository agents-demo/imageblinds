"""Neural text-to-speech via Microsoft Edge voices (free, no API key)."""

from __future__ import annotations

import os

import edge_tts

DEFAULT_VOICE = "en-US-AvaNeural"
MAX_CHARS = 1000


def voice_name() -> str:
    return os.getenv("TTS_VOICE", DEFAULT_VOICE).strip() or DEFAULT_VOICE


def prepare(text: str) -> str:
    """Normalize narration text before synthesis."""
    text = text.strip()
    if not text:
        raise ValueError("Empty text.")
    if len(text) > MAX_CHARS:
        raise ValueError(f"Text too long ({len(text)} chars, max {MAX_CHARS}).")
    return " ".join(text.split())


async def synthesize(text: str) -> bytes:
    """Render narration text to MP3 bytes using the configured neural voice."""
    text = prepare(text)
    communicate = edge_tts.Communicate(text, voice_name())
    chunks = [chunk async for chunk in communicate.stream()]
    return b"".join(chunk["data"] for chunk in chunks if chunk["type"] == "audio")
