"""Database connection and session management.

Supports both PostgreSQL+PostGIS (production) and SQLite (local demo).
Falls back to SQLite when DATABASE_URL is empty.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import AsyncGenerator, Generator

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


# ---------------------------------------------------------------------------
# Determine database URLs (fall back to SQLite if PostgreSQL not configured)
# ---------------------------------------------------------------------------

_backend_dir = Path(__file__).resolve().parent.parent
SQLITE_PATH = _backend_dir / "krishikavach.db"


def _resolve_async_url() -> str:
    """Resolve the async database URL.

    Falls back to SQLite if DATABASE_URL is not set (local dev).
    """
    url = settings.DATABASE_URL
    if not url or url == "postgresql+psycopg2://krishikavach:krishikavach@localhost:5432/krishikavach":
        # Use SQLite for local development demo
        return f"sqlite+aiosqlite:///{SQLITE_PATH}"
    # Convert psycopg2 URL to asyncpg for async engine
    return url.replace("postgresql+psycopg2", "postgresql+asyncpg")


def _resolve_sync_url() -> str:
    """Resolve the sync database URL for Alembic / scripts."""
    url = settings.DATABASE_URL_SYNC
    if not url or url == "postgresql+psycopg2://krishikavach:krishikavach@localhost:5432/krishikavach":
        return f"sqlite:///{SQLITE_PATH}"
    return url


ASYNC_DB_URL = _resolve_async_url()
SYNC_DB_URL = _resolve_sync_url()
IS_SQLITE = "sqlite" in ASYNC_DB_URL


# Async engine for FastAPI endpoints
async_engine: AsyncEngine = create_async_engine(
    ASYNC_DB_URL,
    echo=settings.ENV == "development",
    future=True,
)

# Sync engine for Alembic migrations
sync_engine = create_engine(
    SYNC_DB_URL,
    echo=settings.ENV == "development",
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

SyncSessionLocal = sessionmaker(bind=sync_engine, expire_on_commit=False)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for async database sessions.

    This is an async generator (not decorated with @asynccontextmanager)
    so FastAPI can use it as a dependency.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_async_session_cm() -> AsyncGenerator[AsyncSession, None]:
    """Context manager version of get_async_session for non-FastAPI code."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@contextmanager
def get_sync_session_cm() -> Generator:
    """Context manager for sync sessions (e.g., in scripts/migrations)."""
    session = SyncSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


async def init_db() -> None:
    """Create tables and enable PostGIS extension (development only)."""
    async with async_engine.begin() as conn:
        if not IS_SQLITE:
            # Enable PostGIS extension (PostgreSQL only)
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Close database connections."""
    await async_engine.dispose()
