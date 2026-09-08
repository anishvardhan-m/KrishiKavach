"""Shared pytest fixtures for KrishiKavach backend tests."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import AsyncGenerator
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_async_session
from app.main import app


# ---------------------------------------------------------------------------
# Database engine (shared-file SQLite so fixtures share state within a test)
# ---------------------------------------------------------------------------

TEST_DB_FILE = Path(__file__).parent.parent / "test_krishi.db"
TEST_DB_URL = f"sqlite+aiosqlite:///{TEST_DB_FILE}"


@pytest.fixture(scope="function")
async def test_engine():
    """A function-scoped engine with tables created per test."""
    engine = create_async_engine(TEST_DB_URL, echo=False, future=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()
    try:
        TEST_DB_FILE.unlink(missing_ok=True)
    except OSError:
        pass


@pytest.fixture(scope="function")
async def setup_schema(test_engine):
    """Alias for test_engine for backward compatibility."""
    return test_engine


@pytest_asyncio.fixture(scope="function")
async def session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """A single async session for a test that needs direct DB access."""
    session_factory = async_sessionmaker(
        bind=test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as sess:
        yield sess


# ---------------------------------------------------------------------------
# FastAPI test client
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="function")
async def client(test_engine) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client pointing at the FastAPI app with test DB."""

    async def _override_session():
        session_factory = async_sessionmaker(
            bind=test_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with session_factory() as sess:
            yield sess

    app.dependency_overrides[get_async_session] = _override_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
