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

    # Demo time simulation
    DEMO_TIME_ENABLED: bool = os.getenv("DEMO_TIME_ENABLED", "true").lower() == "true"

    # CORS
    CORS_ORIGINS: list[str] = os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://localhost:3000"
    ).split(",")

    # Environment label
    ENV: str = os.getenv("ENV", "development")


settings = Settings()