"""OmniRoute voice client.

OmniRoute exposes an OpenAI-compatible audio API:
  - POST {base_url}/audio/transcriptions   (STT — multipart/form-data with file)
  - POST {base_url}/audio/speech            (TTS — JSON body, returns audio bytes)

This module isolates all upstream HTTP calls so the rest of the codebase
never imports a vendor SDK or hard-codes a specific provider. The API key
lives only in backend environment configuration.

Per SIH26131 — this module is voice-only. It MUST NOT contain any
crop-diagnosis or business logic.
"""
from __future__ import annotations

import io
import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class OmniRouteError(Exception):
    """Raised when the OmniRoute voice API returns an error or is unavailable."""


class OmniRouteUnavailable(OmniRouteError):
    """OmniRoute is not configured or is not reachable."""


def is_configured() -> bool:
    """Return True if the OmniRoute API key has been set."""
    return bool(settings.OMNIROUTE_API_KEY)


async def transcribe_audio(
    audio_bytes: bytes,
    filename: str,
    content_type: str,
    language: str,
) -> dict:
    """Send audio bytes to OmniRoute and return the transcription.

    Returns a dict with keys: text, language, provider, confidence.
    Raises OmniRouteError or OmniRouteUnavailable on failure.
    """
    if not is_configured():
        raise OmniRouteUnavailable(
            "OMNIROUTE_API_KEY is not configured on the backend."
        )

    url = settings.OMNIROUTE_BASE_URL.rstrip("/") + "/audio/transcriptions"
    headers = {"Authorization": f"Bearer {settings.OMNIROUTE_API_KEY}"}
    files = {
        "file": (filename, io.BytesIO(audio_bytes), content_type or "audio/wav"),
    }
    data = {
        "model": settings.OMNIROUTE_STT_MODEL,
        "language": language.split("-")[0] if language else "hi",
    }

    try:
        async with httpx.AsyncClient(
            timeout=settings.OMNIROUTE_TIMEOUT_SECONDS
        ) as client:
            resp = await client.post(url, headers=headers, files=files, data=data)
    except httpx.HTTPError as e:
        raise OmniRouteError(f"OmniRoute STT transport error: {e}") from e

    if resp.status_code >= 400:
        snippet = resp.text[:300] if resp.text else ""
        raise OmniRouteError(
            f"OmniRoute STT failed (HTTP {resp.status_code}): {snippet}"
        )

    try:
        payload = resp.json()
    except ValueError as e:
        raise OmniRouteError("OmniRoute STT returned non-JSON response") from e

    text = (payload.get("text") or "").strip()
    if not text:
        raise OmniRouteError("OmniRoute STT returned empty transcript")

    return {
        "text": text,
        "language": language,
        "provider": "omniroute",
        "confidence": payload.get("confidence"),
    }


async def synthesize_speech(text: str, language: str, voice: Optional[str] = None) -> bytes:
    """Call OmniRoute /audio/speech and return the audio bytes."""
    if not is_configured():
        raise OmniRouteUnavailable(
            "OMNIROUTE_API_KEY is not configured on the backend."
        )

    url = settings.OMNIROUTE_BASE_URL.rstrip("/") + "/audio/speech"
    headers = {
        "Authorization": f"Bearer {settings.OMNIROUTE_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": settings.OMNIROUTE_TTS_MODEL,
        "voice": voice or settings.OMNIROUTE_TTS_VOICE,
        "input": text,
    }
    if language:
        body["language"] = language

    try:
        async with httpx.AsyncClient(
            timeout=settings.OMNIROUTE_TIMEOUT_SECONDS
        ) as client:
            resp = await client.post(url, headers=headers, json=body)
    except httpx.HTTPError as e:
        raise OmniRouteError(f"OmniRoute TTS transport error: {e}") from e

    if resp.status_code >= 400:
        snippet = resp.text[:300] if resp.text else ""
        raise OmniRouteError(
            f"OmniRoute TTS failed (HTTP {resp.status_code}): {snippet}"
        )

    audio = resp.content
    if not audio:
        raise OmniRouteError("OmniRoute TTS returned empty audio body")
    return audio
