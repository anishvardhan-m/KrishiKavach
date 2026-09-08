"""Tests for the farmer feedback / follow-up loop (SIH26131).

Covers:
  - GET /api/cases/due-for-follow-up (with and without farmer_id filter)
  - POST /api/cases/{case_id}/feedback
  - Case status transitions: improved -> resolved, not improved -> active
  - Storage of actual feedback data (CaseFeedback row written)

No new tables; no new schema; uses the existing CaseFeedback model and
`record_feedback` service.
"""
from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.main import app
from app.models import Case, CaseFeedback, Farmer, Farm
from app.services.case_service import (
    get_cases_due_for_follow_up,
    record_feedback,
)


async def _new_session(test_engine) -> AsyncSession:
    factory = async_sessionmaker(
        bind=test_engine, class_=AsyncSession, expire_on_commit=False
    )
    return factory()


@pytest_asyncio.fixture
async def two_farmers(test_engine):
    """Two farmers with one due case each."""
    today = date.today()
    f1 = Farmer(
        id=uuid4(), name="F1", phone="111", district="Pune", state="Maharashtra",
        primary_language="marathi",
    )
    f2 = Farmer(
        id=uuid4(), name="F2", phone="222", district="Nashik", state="Maharashtra",
        primary_language="marathi",
    )
    farm1 = Farm(id=uuid4(), farmer_id=f1.id, primary_crop="tomato")
    farm2 = Farm(id=uuid4(), farmer_id=f2.id, primary_crop="potato")
    case1 = Case(
        id=uuid4(),
        farm_id=farm1.id, farmer_id=f1.id,
        predicted_disease="Tomato_Late_blight", predicted_crop="tomato",
        confidence=0.9, severity="high", uncertainty_flag=False,
        case_status="active",
        next_follow_up_at=today - timedelta(days=1),  # due yesterday
    )
    case2 = Case(
        id=uuid4(),
        farm_id=farm2.id, farmer_id=f2.id,
        predicted_disease="Potato_Blight", predicted_crop="potato",
        confidence=0.85, severity="medium", uncertainty_flag=False,
        case_status="active",
        next_follow_up_at=today - timedelta(days=2),
    )
    async with await _new_session(test_engine) as session:
        session.add_all([f1, f2, farm1, farm2, case1, case2])
        await session.commit()
    return {"f1": f1, "f2": f2, "case1": case1, "case2": case2}


# ---------------------------------------------------------------------------
# Service-layer tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_due_returns_all_active(test_engine, two_farmers):
    async with await _new_session(test_engine) as session:
        cases = await get_cases_due_for_follow_up(session)
    assert len(cases) == 2
    ids = {c.id for c in cases}
    assert two_farmers["case1"].id in ids
    assert two_farmers["case2"].id in ids


@pytest.mark.asyncio
async def test_get_due_filters_by_farmer(test_engine, two_farmers):
    async with await _new_session(test_engine) as session:
        cases = await get_cases_due_for_follow_up(
            session, farmer_id=two_farmers["f1"].id
        )
    assert len(cases) == 1
    assert cases[0].id == two_farmers["case1"].id


@pytest.mark.asyncio
async def test_get_due_excludes_resolved(test_engine, two_farmers):
    """Cases that are not 'active' should not be returned, even if due date passed."""
    case1 = two_farmers["case1"]
    async with await _new_session(test_engine) as session:
        # Mark case1 as resolved
        c = (await session.execute(
            select(Case).where(Case.id == case1.id)
        )).scalar_one()
        c.case_status = "resolved"
        await session.commit()

    async with await _new_session(test_engine) as session:
        cases = await get_cases_due_for_follow_up(session)
    assert all(c.id != case1.id for c in cases)


@pytest.mark.asyncio
async def test_record_feedback_improved_marks_resolved(test_engine, two_farmers):
    case1 = two_farmers["case1"]
    async with await _new_session(test_engine) as session:
        feedback = await record_feedback(
            session,
            case_id=case1.id,
            farmer_id=case1.farmer_id,
            attempted_intervention=True,
            crop_improved=True,
            farmer_notes="Crop is now healthy",
        )
        await session.commit()
        assert feedback.id is not None
        assert feedback.crop_improved is True
        assert feedback.attempted_intervention is True
        assert feedback.farmer_notes == "Crop is now healthy"

        # Case should be resolved
        c = (await session.execute(
            select(Case).where(Case.id == case1.id)
        )).scalar_one()
        assert c.case_status == "resolved"


@pytest.mark.asyncio
async def test_record_feedback_not_improved_keeps_active(test_engine, two_farmers):
    case1 = two_farmers["case1"]
    async with await _new_session(test_engine) as session:
        feedback = await record_feedback(
            session,
            case_id=case1.id,
            farmer_id=case1.farmer_id,
            attempted_intervention=True,
            crop_improved=False,
            farmer_notes="Still has spots",
        )
        await session.commit()
        assert feedback.crop_improved is False

        c = (await session.execute(
            select(Case).where(Case.id == case1.id)
        )).scalar_one()
        # Not improved → status stays active, follow-up rescheduled
        assert c.case_status == "active"


@pytest.mark.asyncio
async def test_feedback_persisted_in_db(test_engine, two_farmers):
    """The CaseFeedback row must actually exist after record_feedback."""
    case1 = two_farmers["case1"]
    async with await _new_session(test_engine) as session:
        await record_feedback(
            session,
            case_id=case1.id,
            farmer_id=case1.farmer_id,
            attempted_intervention=True,
            crop_improved=True,
            farmer_notes="All good",
        )
        await session.commit()

    async with await _new_session(test_engine) as session:
        rows = (await session.execute(
            select(CaseFeedback).where(CaseFeedback.case_id == case1.id)
        )).scalars().all()
    assert len(rows) == 1
    assert rows[0].farmer_notes == "All good"
    assert rows[0].crop_improved is True


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

def _override_session(test_engine):
    """Factory for an app dependency that uses the test engine."""
    async def _override():
        factory = async_sessionmaker(
            bind=test_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with factory() as s:
            yield s
    return _override


@pytest.mark.asyncio
async def test_due_endpoint_returns_due_cases(test_engine, two_farmers):
    dep = __import__("app.database", fromlist=["get_async_session"]).get_async_session
    app.dependency_overrides[dep] = _override_session(test_engine)
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/cases/due-for-follow-up")
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    case_ids = {c["id"] for c in data["cases"]}
    assert str(two_farmers["case1"].id) in case_ids
    assert str(two_farmers["case2"].id) in case_ids


@pytest.mark.asyncio
async def test_due_endpoint_farmer_filter(test_engine, two_farmers):
    f1_id = str(two_farmers["f1"].id)
    dep = __import__("app.database", fromlist=["get_async_session"]).get_async_session
    app.dependency_overrides[dep] = _override_session(test_engine)
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                f"/api/cases/due-for-follow-up?farmer_id={f1_id}"
            )
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["cases"][0]["id"] == str(two_farmers["case1"].id)


@pytest.mark.asyncio
async def test_feedback_endpoint_200(test_engine, two_farmers):
    case1 = two_farmers["case1"]
    dep = __import__("app.database", fromlist=["get_async_session"]).get_async_session
    app.dependency_overrides[dep] = _override_session(test_engine)
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/cases/{case1.id}/feedback",
                json={
                    "attempted_intervention": True,
                    "crop_improved": True,
                    "farmer_notes": "Crop is much better now",
                },
            )
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200
    data = resp.json()
    assert data["crop_improved"] is True
    assert data["farmer_notes"] == "Crop is much better now"
    assert data["case_id"] == str(case1.id)


@pytest.mark.asyncio
async def test_feedback_endpoint_persists_data(test_engine, two_farmers):
    """Submitting feedback via the API must actually write a CaseFeedback row."""
    case1 = two_farmers["case1"]
    dep = __import__("app.database", fromlist=["get_async_session"]).get_async_session
    app.dependency_overrides[dep] = _override_session(test_engine)
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                f"/api/cases/{case1.id}/feedback",
                json={
                    "attempted_intervention": True,
                    "crop_improved": False,
                    "farmer_notes": "Need expert",
                },
            )
    finally:
        app.dependency_overrides.clear()

    async with await _new_session(test_engine) as session:
        rows = (await session.execute(
            select(CaseFeedback).where(CaseFeedback.case_id == case1.id)
        )).scalars().all()
    assert len(rows) == 1
    assert rows[0].farmer_notes == "Need expert"
    assert rows[0].crop_improved is False


@pytest.mark.asyncio
async def test_feedback_endpoint_404(test_engine):
    fake_id = uuid4()
    dep = __import__("app.database", fromlist=["get_async_session"]).get_async_session
    app.dependency_overrides[dep] = _override_session(test_engine)
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/cases/{fake_id}/feedback",
                json={
                    "attempted_intervention": True,
                    "crop_improved": True,
                },
            )
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_feedback_endpoint_case_status_improved(test_engine, two_farmers):
    """Improved feedback transitions case to 'resolved'."""
    case1 = two_farmers["case1"]
    dep = __import__("app.database", fromlist=["get_async_session"]).get_async_session
    app.dependency_overrides[dep] = _override_session(test_engine)
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                f"/api/cases/{case1.id}/feedback",
                json={"attempted_intervention": True, "crop_improved": True},
            )
    finally:
        app.dependency_overrides.clear()

    async with await _new_session(test_engine) as session:
        c = (await session.execute(
            select(Case).where(Case.id == case1.id)
        )).scalar_one()
    assert c.case_status == "resolved"


@pytest.mark.asyncio
async def test_feedback_endpoint_case_status_not_improved(test_engine, two_farmers):
    """Not-improved feedback keeps case 'active'."""
    case1 = two_farmers["case1"]
    dep = __import__("app.database", fromlist=["get_async_session"]).get_async_session
    app.dependency_overrides[dep] = _override_session(test_engine)
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                f"/api/cases/{case1.id}/feedback",
                json={"attempted_intervention": True, "crop_improved": False},
            )
    finally:
        app.dependency_overrides.clear()

    async with await _new_session(test_engine) as session:
        c = (await session.execute(
            select(Case).where(Case.id == case1.id)
        )).scalar_one()
    assert c.case_status == "active"
