"""ElevenLabs Speech-to-Text service.

Transcribes Hindi/multilingual audio via the ElevenLabs API and returns
the transcribed text. The API key lives only in backend environment
configuration and is never exposed to the browser.

Model: scribe_v2 (supports Hindi, Marathi, English, and more)
Endpoint: POST /v1/speech-to-text
"""
from __future__ import annotations

import io
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class ElevenLabsSTTError(Exception):
    """Raised when the ElevenLabs STT API returns an error."""


class ElevenLabsSTTUnavailable(ElevenLabsSTTError):
    """ElevenLabs STT is not configured or is not reachable."""


def is_configured() -> bool:
    """Return True if the ElevenLabs API key has been set."""
    return bool(settings.ELEVENLABS_API_KEY)


async def transcribe_audio(
    audio_bytes: bytes,
    filename: str,
    content_type: str,
    language: str | None = None,
) -> dict:
    """Transcribe audio via ElevenLabs and return the transcription result.

    Args:
        audio_bytes: Raw audio bytes from the browser recording.
        filename: Original filename (used only for the multipart field name).
        content_type: MIME type of the audio (e.g. "audio/webm", "audio/mp4").
        language: Optional BCP-47 language code hint (e.g. "hi-IN", "mr-IN").
                  If None, ElevenLabs uses automatic language detection.

    Returns:
        dict with keys: text, language, provider, confidence.

    Raises:
        ElevenLabsSTTUnavailable: API key not set.
        ElevenLabsSTTError: Upstream API error.
    """
    if not is_configured():
        raise ElevenLabsSTTUnavailable(
            "ELEVENLABS_API_KEY is not configured on the backend."
        )

    # ElevenLabs scribe_v2 endpoint
    url = "https://api.elevenlabs.io/v1/speech-to-text"

    headers = {
        "Accept": "application/json",
        # content-type set automatically by httpx from files dict
        "xi-api-key": settings.ELEVENLABS_API_KEY,
    }

    # Infer file extension from content type for the multipart field
    ext_map = {
        "audio/webm": "webm",
        "audio/mp4": "mp4",
        "audio/mpeg": "mp3",
        "audio/wav": "wav",
        "audio/ogg": "ogg",
        "audio/flac": "flac",
    }
    ext = ext_map.get(content_type.lower(), "webm")
    base_name = filename.rsplit(".", 1)[0] if "." in filename else "recording"
    multipart_filename = f"{base_name}.{ext}"

    files = {
        "file": (multipart_filename, io.BytesIO(audio_bytes), content_type or "audio/webm"),
    }

    # Build request body
    # model_id is required; tag the version so we can route it clearly in logs
    data: dict = {
        "model_id": settings.ELEVENLABS_STT_MODEL,
    }

    # Pass language hint if provided; scribe_v2 respects it for better accuracy
    if language:
        # Extract base language (hi, mr, en) from BCP-47
        lang_code = language.split("-")[0]
        # Map to ElevenLabs-supported language codes
        lang_map = {
            "hi": "hi",
            "mr": "mr",
            "en": "en",
        }
        mapped_lang = lang_map.get(lang_code, lang_code)
        data["language"] = mapped_lang

    try:
        async with httpx.AsyncClient(
            timeout=settings.ELEVENLABS_TIMEOUT_SECONDS
        ) as client:
            resp = await client.post(url, headers=headers, files=files, data=data)
    except httpx.HTTPError as e:
        raise ElevenLabsSTTError(f"ElevenLabs STT transport error: {e}") from e

    if resp.status_code == 401:
        raise ElevenLabsSTTUnavailable("ElevenLabs API key is invalid or expired.")
    if resp.status_code == 429:
        raise ElevenLabsSTTUnavailable(
            "ElevenLabs STT rate limit reached. Try again later."
        )
    if resp.status_code >= 400:
        snippet = resp.text[:300] if resp.text else ""
        raise ElevenLabsSTTError(
            f"ElevenLabs STT failed (HTTP {resp.status_code}): {snippet}"
        )

    try:
        payload = resp.json()
    except ValueError as e:
        raise ElevenLabsSTTError(
            f"ElevenLabs STT returned non-JSON response: {resp.text[:200]}"
        ) from e

    text = (payload.get("text") or "").strip()
    if not text:
        raise ElevenLabsSTTError("ElevenLabs STT returned empty transcript")

    # scribe_v2 may return language detection
    detected_lang = payload.get("language", language or "hi-IN")

    return {
        "text": text,
        "language": detected_lang,
        "provider": "elevenlabs",
        "confidence": payload.get("confidence"),
    }
