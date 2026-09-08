"""ElevenLabs TTS service.

Synthesizes Hindi/multilingual speech via the ElevenLabs API and returns
raw audio bytes. The API key lives only in backend environment configuration
and is never exposed to the browser.

Voice: Rian — Energetic Hindi Conversational
Voice ID: IvLWq57RKibBrqZGpQrC
Model: eleven_multilingual_v2
"""
from __future__ import annotations

import io
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class ElevenLabsError(Exception):
    """Raised when the ElevenLabs API returns an error."""


class ElevenLabsUnavailable(ElevenLabsError):
    """ElevenLabs is not configured or is not reachable."""


def is_configured() -> bool:
    """Return True if the ElevenLabs API key has been set."""
    return bool(settings.ELEVENLABS_API_KEY)


async def synthesize_speech(text: str, language: str = "hi-IN") -> bytes:
    """Synthesize speech via ElevenLabs and return audio bytes.

    Args:
        text: Text to synthesize.
        language: BCP-47 language code (currently unused — voice handles
            multilingual automatically; kept for future model routing).

    Returns:
        Raw audio bytes (MP3).

    Raises:
        ElevenLabsUnavailable: API key not set.
        ElevenLabsError: Upstream API error.
    """
    if not is_configured():
        raise ElevenLabsUnavailable(
            "ELEVENLABS_API_KEY is not configured on the backend."
        )

    url = (
        f"https://api.elevenlabs.io/v1/text-to-speech/{settings.ELEVENLABS_VOICE_ID}"
        "/stream"
    )
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": settings.ELEVENLABS_API_KEY,
    }
    body = {
        "text": text,
        "model_id": settings.ELEVENLABS_MODEL_ID,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.5,
            "use_speaker_boost": True,
        },
    }

    try:
        async with httpx.AsyncClient(
            timeout=settings.ELEVENLABS_TIMEOUT_SECONDS
        ) as client:
            resp = await client.post(url, headers=headers, json=body)
    except httpx.HTTPError as e:
        raise ElevenLabsError(f"ElevenLabs TTS transport error: {e}") from e

    if resp.status_code == 401:
        raise ElevenLabsUnavailable("ElevenLabs API key is invalid or expired.")
    if resp.status_code == 429:
        raise ElevenLabsUnavailable("ElevenLabs rate limit reached. Try again later.")
    if resp.status_code >= 400:
        snippet = resp.text[:300] if resp.text else ""
        raise ElevenLabsError(
            f"ElevenLabs TTS failed (HTTP {resp.status_code}): {snippet}"
        )

    audio = resp.content
    if not audio:
        raise ElevenLabsError("ElevenLabs TTS returned empty audio body")
    return audio
