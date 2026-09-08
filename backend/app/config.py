"""Configuration for KrishiKavach backend."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env from backend directory if present
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class Settings:
    """Application settings with sensible defaults for development."""

    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://krishikavach:krishikavach@localhost:5432/krishikavach",
    )
    DATABASE_URL_SYNC: str = os.getenv(
        "DATABASE_URL_SYNC",
        "postgresql+psycopg2://krishikavach:krishikavach@localhost:5432/krishikavach",
    )

    # Auth (JWT secret - placeholder for future auth; never commit real value)
    SECRET_KEY: str = os.getenv("SECRET_KEY", "krishikavach-dev-secret-change-me")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

    # File storage
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", str(Path(__file__).resolve().parent.parent / "uploads"))
    MAX_UPLOAD_BYTES: int = int(os.getenv("MAX_UPLOAD_BYTES", "10485760"))  # 10 MB

    # ML / prediction
    PREDICTION_MODE: str = os.getenv("PREDICTION_MODE", "demo")  # demo | real
    ML_MODEL_PATH: str = os.getenv(
        "ML_MODEL_PATH", str(Path(__file__).resolve().parent.parent / "ml" / "models" / "plantvillage.onnx")
    )

    # Voice / speech
    SPEECH_ENABLED: bool = os.getenv("SPEECH_ENABLED", "true").lower() == "true"

    # Voice provider: ElevenLabs for both STT and TTS (or "browser" as fallback).
    VOICE_STT_PROVIDER: str = os.getenv("VOICE_STT_PROVIDER", "elevenlabs").lower()
    # TTS is "elevenlabs" (production) or "browser" (fallback).
    VOICE_TTS_PROVIDER: str = os.getenv("VOICE_TTS_PROVIDER", "elevenlabs").lower()
    # Legacy alias — still used when both STT and TTS point to OmniRoute.
    VOICE_PROVIDER: str = os.getenv("VOICE_PROVIDER", "omniroute").lower()

    # Default voice language (BCP-47). Frontend also reads this via /api/voice/config.
    DEFAULT_VOICE_LANGUAGE: str = os.getenv("DEFAULT_VOICE_LANGUAGE", "hi-IN")

    # OmniRoute-compatible endpoint configuration
    OMNIROUTE_BASE_URL: str = os.getenv(
        "OMNIROUTE_BASE_URL", "https://api.omniroute.online/v1"
    )
    OMNIROUTE_API_KEY: str = os.getenv("OMNIROUTE_API_KEY", "")
    # STT (transcription) model name. Leave empty to use the gateway default.
    OMNIROUTE_STT_MODEL: str = os.getenv("OMNIROUTE_STT_MODEL", "whisper-1")
    # TTS (speech) model name.
    OMNIROUTE_TTS_MODEL: str = os.getenv("OMNIROUTE_TTS_MODEL", "tts-1")
    # TTS voice identifier (e.g. "alloy", "echo", "shimmer" or a provider-specific voice).
    OMNIROUTE_TTS_VOICE: str = os.getenv("OMNIROUTE_TTS_VOICE", "alloy")
    # Request timeout for upstream voice API calls (seconds).
    OMNIROUTE_TIMEOUT_SECONDS: float = float(
        os.getenv("OMNIROUTE_TIMEOUT_SECONDS", "20")
    )

    # ElevenLabs configuration (shared for STT and TTS)
    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
    # STT: model_id for speech-to-text
    ELEVENLABS_STT_MODEL: str = os.getenv("ELEVENLABS_STT_MODEL", "scribe_v2")
    ELEVENLABS_VOICE_ID: str = os.getenv(
        "ELEVENLABS_VOICE_ID", "IvLWq57RKibBrqZGpQrC"
    )
    ELEVENLABS_MODEL_ID: str = os.getenv(
        "ELEVENLABS_MODEL_ID", "eleven_multilingual_v2"
    )
    ELEVENLABS_OUTPUT_FORMAT: str = os.getenv(
        "ELEVENLABS_OUTPUT_FORMAT", "mp3_44100_128"
    )
    ELEVENLABS_TIMEOUT_SECONDS: float = float(
        os.getenv("ELEVENLABS_TIMEOUT_SECONDS", "20")
    )

    # Demo time simulation
    DEMO_TIME_ENABLED: bool = os.getenv("DEMO_TIME_ENABLED", "true").lower() == "true"

    # CORS
    CORS_ORIGINS: list[str] = os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://localhost:3000"
    ).split(",")

    # Environment label
    ENV: str = os.getenv("ENV", "development")


settings = Settings()