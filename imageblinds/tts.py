"""Neural text-to-speech via Microsoft Edge voices (free, no API key)."""

from __future__ import annotations

import os

import edge_tts

DEFAULT_VOICE = "en-US-AvaNeural"
ZH_VOICE = "zh-CN-XiaoxiaoNeural"
MAX_CHARS = 1000


def voice_name() -> str:
    return os.getenv("TTS_VOICE", DEFAULT_VOICE).strip() or DEFAULT_VOICE


def voice_for(lang: str = "en") -> str:
    """The edge-tts voice for the requested language.

    The ``TTS_VOICE`` environment override wins for English; Chinese always
    uses the built-in Chinese voice.
    """
    if lang == "zh":
        return ZH_VOICE
    return voice_name()


def prepare(text: str) -> str:
    """Normalize narration text before synthesis."""
    text = text.strip()
    if not text:
        raise ValueError("Empty text.")
    if len(text) > MAX_CHARS:
        raise ValueError(f"Text too long ({len(text)} chars, max {MAX_CHARS}).")
    return " ".join(text.split())


async def synthesize(text: str, lang: str = "en") -> bytes:
    """Render narration text to MP3 bytes using the configured neural voice."""
    text = prepare(text)
    communicate = edge_tts.Communicate(text, voice_for(lang))
    chunks = [chunk async for chunk in communicate.stream()]
    return b"".join(chunk["data"] for chunk in chunks if chunk["type"] == "audio")
