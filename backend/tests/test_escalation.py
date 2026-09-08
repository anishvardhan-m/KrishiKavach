"""Tests for the expert escalation workflow (SIH26131)."""
from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.main import app
from app.models import Case, Escalation, Farmer, Farm
from app.services.escalation_service import (
    EscalationError,
    create_escalation,
    escalation_status_for_case,
    submit_verdict,
    list_escalations,
    VALID_VERDICTS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _new_session(test_engine) -> AsyncSession:
    """Create a fresh async session for a unit-test block."""
    factory = async_sessionmaker(
        bind=test_engine, class_=AsyncSession, expire_on_commit=False
    )
    return factory()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def seeded(test_engine):
    """Create a farmer, farm, and active case. Returns (case, farmer, farm)."""
    farmer = Farmer(
        id=uuid4(),
        name="Test Farmer",
        phone="9999999999",
        district="Pune",
        state="Maharashtra",
        primary_language="marathi",
    )
    farm = Farm(
        id=uuid4(),
        farmer_id=farmer.id,
        primary_crop="tomato",
    )
    case = Case(
        id=uuid4(),
        farm_id=farm.id,
        farmer_id=farmer.id,
        predicted_disease="Tomato_Late_blight",
        predicted_crop="tomato",
        confidence=0.87,
        severity="high",
        uncertainty_flag=False,
        case_status="active",
        next_follow_up_at=date.today() + timedelta(days=7),
    )
    async with await _new_session(test_engine) as session:
        session.add_all([farmer, farm, case])
        await session.commit()
        # Detach IDs for tests
        return case, farmer, farm


# ---------------------------------------------------------------------------
# Service-layer unit tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_escalation_success(test_engine, seeded):
    """An active case can be escalated once."""
    case, _, _ = seeded
    async with await _new_session(test_engine) as session:
        esc = await create_escalation(
            session, case_id=case.id, reason="Low confidence prediction"
        )
        await session.commit()
    assert esc.case_id == case.id
    assert esc.resolved_at is None
    assert esc.expert_verdict is None
    assert esc.expert_notes == "Low confidence prediction"


@pytest.mark.asyncio
async def test_create_escalation_case_not_found(test_engine):
    """Escalating a non-existent case raises EscalationError."""
    fake_id = uuid4()
    async with await _new_session(test_engine) as session:
        with pytest.raises(EscalationError, match="not found"):
            await create_escalation(session, case_id=fake_id)


@pytest.mark.asyncio
async def test_duplicate_active_escalation_prevented(test_engine, seeded):
    """A second escalation on the same case raises EscalationError."""
    case, _, _ = seeded
    async with await _new_session(test_engine) as session:
        await create_escalation(session, case_id=case.id)
        await session.commit()

    async with await _new_session(test_engine) as session:
        with pytest.raises(EscalationError, match="active escalation already exists"):
            await create_escalation(session, case_id=case.id)


@pytest.mark.asyncio
async def test_duplicate_prevented_after_resolved(test_engine, seeded):
    """After a verdict is submitted, a new escalation CAN be created."""
    case, _, _ = seeded
    async with await _new_session(test_engine) as session:
        esc = await create_escalation(session, case_id=case.id)
        await session.commit()
        esc_id = esc.id

    async with await _new_session(test_engine) as session:
        await submit_verdict(session, escalation_id=esc_id, verdict="confirmed")
        await session.commit()

    async with await _new_session(test_engine) as session:
        new_esc = await create_escalation(session, case_id=case.id, reason="Second review")
        await session.commit()
    assert new_esc.case_id == case.id
    assert new_esc.resolved_at is None


@pytest.mark.asyncio
async def test_escalation_status_for_case_active(test_engine, seeded):
    """status='active' when an unresolved escalation exists."""
    case, _, _ = seeded
    async with await _new_session(test_engine) as session:
        await create_escalation(session, case_id=case.id)
        await session.commit()

    async with await _new_session(test_engine) as session:
        status, verdict = await escalation_status_for_case(session, case.id)
    assert status == "active"
    assert verdict is None


@pytest.mark.asyncio
async def test_escalation_status_for_case_resolved(test_engine, seeded):
    """status='resolved' after a verdict."""
    case, _, _ = seeded
    async with await _new_session(test_engine) as session:
        esc = await create_escalation(session, case_id=case.id)
        await session.commit()
        esc_id = esc.id

    async with await _new_session(test_engine) as session:
        await submit_verdict(session, escalation_id=esc_id, verdict="rejected")
        await session.commit()

    async with await _new_session(test_engine) as session:
        status, verdict = await escalation_status_for_case(session, case.id)
    assert status == "resolved"
    assert verdict == "rejected"


@pytest.mark.asyncio
async def test_escalation_status_for_case_none(test_engine, seeded):
    """No escalations → (None, None)."""
    case, _, _ = seeded
    async with await _new_session(test_engine) as session:
        status, verdict = await escalation_status_for_case(session, case.id)
    assert status is None
    assert verdict is None


@pytest.mark.asyncio
async def test_valid_verdicts(test_engine, seeded):
    """All three verdict values are accepted and update case status correctly."""
    case, _, _ = seeded
    for verdict in VALID_VERDICTS:
        # Create a fresh escalation for each verdict
        async with await _new_session(test_engine) as session:
            new_esc = await create_escalation(session, case_id=case.id)
            await session.commit()
            eid = new_esc.id

        async with await _new_session(test_engine) as session:
            updated = await submit_verdict(
                session,
                escalation_id=eid,
                verdict=verdict,
                expert_notes=f"Verdict: {verdict}",
            )
            await session.commit()
            assert updated.expert_verdict == verdict
            assert updated.resolved_at is not None

            case_row = (
                await session.execute(select(Case).where(Case.id == case.id))
            ).scalar_one()
            if verdict == "rejected":
                assert case_row.case_status == "closed"
            else:
                assert case_row.case_status == "active"


@pytest.mark.asyncio
async def test_invalid_verdict_rejected(test_engine, seeded):
    """An invalid verdict string raises EscalationError."""
    case, _, _ = seeded
    async with await _new_session(test_engine) as session:
        esc = await create_escalation(session, case_id=case.id)
        await session.commit()
        esc_id = esc.id

    async with await _new_session(test_engine) as session:
        with pytest.raises(EscalationError, match="Invalid verdict"):
            await submit_verdict(session, escalation_id=esc_id, verdict="maybe")


@pytest.mark.asyncio
async def test_verdict_on_resolved_escalation_fails(test_engine, seeded):
    """Submitting a verdict twice raises EscalationError."""
    case, _, _ = seeded
    async with await _new_session(test_engine) as session:
        esc = await create_escalation(session, case_id=case.id)
        await session.commit()
        esc_id = esc.id

    async with await _new_session(test_engine) as session:
        await submit_verdict(session, escalation_id=esc_id, verdict="confirmed")
        await session.commit()

    async with await _new_session(test_engine) as session:
        with pytest.raises(EscalationError, match="already resolved"):
            await submit_verdict(session, escalation_id=esc_id, verdict="rejected")


@pytest.mark.asyncio
async def test_list_escalations_active(test_engine, seeded):
    """list_escalations(status='active') returns only unresolved escalations."""
    case, _, _ = seeded
    async with await _new_session(test_engine) as session:
        esc = await create_escalation(session, case_id=case.id)
        await session.commit()
        esc_id = esc.id

    async with await _new_session(test_engine) as session:
        rows = await list_escalations(session, status="active")
        ids = [r[0].id for r in rows]
        assert esc_id in ids

    async with await _new_session(test_engine) as session:
        rows = await list_escalations(session, status="resolved")
        ids = [r[0].id for r in rows]
        assert esc_id not in ids


@pytest.mark.asyncio
async def test_list_escalations_invalid_status(test_engine):
    """An invalid status filter raises EscalationError."""
    async with await _new_session(test_engine) as session:
        with pytest.raises(EscalationError, match="Invalid status"):
            await list_escalations(session, status="invalid")


# ---------------------------------------------------------------------------
# API integration tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_escalate_endpoint_201(test_engine, seeded):
    """POST /api/cases/{case_id}/escalate returns 201 with the escalation."""
    case, _, _ = seeded

    async def _override_session():
        factory = async_sessionmaker(
            bind=test_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with factory() as s:
            yield s

    app.dependency_overrides[get_async_session_override := __import__(
        "app.database", fromlist=["get_async_session"]
    ).get_async_session] = _override_session

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/cases/{case.id}/escalate", json={"reason": "Test escalation"}
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 201
    data = resp.json()
    assert data["case_id"] == str(case.id)
    assert data["expert_verdict"] is None
    assert data["resolved_at"] is None


@pytest.mark.asyncio
async def test_escalate_endpoint_404(test_engine):
    """Escalating a non-existent case returns 404."""
    fake_id = uuid4()

    async def _override_session():
        factory = async_sessionmaker(
            bind=test_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with factory() as s:
            yield s

    dep = __import__("app.database", fromlist=["get_async_session"]).get_async_session
    app.dependency_overrides[dep] = _override_session

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(f"/api/cases/{fake_id}/escalate", json={})
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_escalate_endpoint_409_duplicate(test_engine, seeded):
    """Escalating the same case twice returns 409."""
    case, _, _ = seeded

    async def _override_session():
        factory = async_sessionmaker(
            bind=test_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with factory() as s:
            yield s

    dep = __import__("app.database", fromlist=["get_async_session"]).get_async_session
    app.dependency_overrides[dep] = _override_session

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r1 = await client.post(f"/api/cases/{case.id}/escalate", json={})
            assert r1.status_code == 201
            r2 = await client.post(f"/api/cases/{case.id}/escalate", json={})
            assert r2.status_code == 409
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_verdict_endpoint_200_confirmed(test_engine, seeded):
    """POST /api/escalations/{id}/verdict returns 200 for a valid verdict."""
    case, _, _ = seeded

    async def _override_session():
        factory = async_sessionmaker(
            bind=test_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with factory() as s:
            yield s

    dep = __import__("app.database", fromlist=["get_async_session"]).get_async_session
    app.dependency_overrides[dep] = _override_session

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            esc_resp = await client.post(f"/api/cases/{case.id}/escalate", json={})
            esc_id = esc_resp.json()["id"]
            verdict_resp = await client.post(
                f"/api/escalations/{esc_id}/verdict",
                json={
                    "verdict": "confirmed",
                    "expert_notes": "Prediction correct",
                    "computed_at": "2024-01-01",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert verdict_resp.status_code == 200
    data = verdict_resp.json()
    assert data["expert_verdict"] == "confirmed"
    assert data["resolved_at"] is not None


@pytest.mark.asyncio
async def test_verdict_endpoint_200_rejected_closes_case(test_engine, seeded):
    """A 'rejected' verdict sets the case status to 'closed'."""
    case, _, _ = seeded

    async def _override_session():
        factory = async_sessionmaker(
            bind=test_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with factory() as s:
            yield s

    dep = __import__("app.database", fromlist=["get_async_session"]).get_async_session
    app.dependency_overrides[dep] = _override_session

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            esc_resp = await client.post(f"/api/cases/{case.id}/escalate", json={})
            esc_id = esc_resp.json()["id"]
            await client.post(
                f"/api/escalations/{esc_id}/verdict",
                json={"verdict": "rejected", "computed_at": "2024-01-01"},
            )
    finally:
        app.dependency_overrides.clear()

    async with await _new_session(test_engine) as session:
        case_row = (
            await session.execute(select(Case).where(Case.id == case.id))
        ).scalar_one()
        assert case_row.case_status == "closed"


@pytest.mark.asyncio
async def test_verdict_endpoint_400_invalid(test_engine, seeded):
    """An invalid verdict value returns 400."""
    case, _, _ = seeded

    async def _override_session():
        factory = async_sessionmaker(
            bind=test_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with factory() as s:
            yield s

    dep = __import__("app.database", fromlist=["get_async_session"]).get_async_session
    app.dependency_overrides[dep] = _override_session

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            esc_resp = await client.post(f"/api/cases/{case.id}/escalate", json={})
            esc_id = esc_resp.json()["id"]
            resp = await client.post(
                f"/api/escalations/{esc_id}/verdict",
                json={"verdict": "maybe", "computed_at": "2024-01-01"},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 400
    assert "Invalid verdict" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_verdict_endpoint_404(test_engine):
    """Verdict on a non-existent escalation returns 404."""
    fake_id = uuid4()

    async def _override_session():
        factory = async_sessionmaker(
            bind=test_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with factory() as s:
            yield s

    dep = __import__("app.database", fromlist=["get_async_session"]).get_async_session
    app.dependency_overrides[dep] = _override_session

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/escalations/{fake_id}/verdict",
                json={"verdict": "confirmed", "computed_at": "2024-01-01"},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_escalations_endpoint(test_engine, seeded):
    """GET /api/escalations returns escalation rows without farmer PII."""
    case, _, _ = seeded

    async def _override_session():
        factory = async_sessionmaker(
            bind=test_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with factory() as s:
            yield s

    dep = __import__("app.database", fromlist=["get_async_session"]).get_async_session
    app.dependency_overrides[dep] = _override_session

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(f"/api/cases/{case.id}/escalate", json={})
            resp = await client.get("/api/escalations", params={"status": "active"})
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "escalations" in data
    for item in data["escalations"]:
        assert "farmer_name" not in item
        assert "farmer_phone" not in item
        assert "farmer_id" not in item


@pytest.mark.asyncio
async def test_get_escalation_endpoint(test_engine, seeded):
    """GET /api/escalations/{id} returns the escalation details."""
    case, _, _ = seeded

    async def _override_session():
        factory = async_sessionmaker(
            bind=test_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with factory() as s:
            yield s

    dep = __import__("app.database", fromlist=["get_async_session"]).get_async_session
    app.dependency_overrides[dep] = _override_session

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            esc_resp = await client.post(f"/api/cases/{case.id}/escalate", json={})
            esc_id = esc_resp.json()["id"]
            get_resp = await client.get(f"/api/escalations/{esc_id}")
    finally:
        app.dependency_overrides.clear()

    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == esc_id


@pytest.mark.asyncio
async def test_get_case_includes_escalation_status(test_engine, seeded):
    """GET /api/cases/{id} includes escalation_status and latest_verdict."""
    case, _, _ = seeded

    async def _override_session():
        factory = async_sessionmaker(
            bind=test_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with factory() as s:
            yield s

    dep = __import__("app.database", fromlist=["get_async_session"]).get_async_session
    app.dependency_overrides[dep] = _override_session

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(f"/api/cases/{case.id}/escalate", json={})
            resp = await client.get(f"/api/cases/{case.id}")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["escalation_status"] == "active"
    assert data["latest_verdict"] is None


@pytest.mark.asyncio
async def test_get_case_includes_latest_verdict(test_engine, seeded):
    """GET /api/cases/{id} shows the latest verdict after one is recorded."""
    case, _, _ = seeded

    async def _override_session():
        factory = async_sessionmaker(
            bind=test_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with factory() as s:
            yield s

    dep = __import__("app.database", fromlist=["get_async_session"]).get_async_session
    app.dependency_overrides[dep] = _override_session

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            esc_resp = await client.post(f"/api/cases/{case.id}/escalate", json={})
            esc_id = esc_resp.json()["id"]
            await client.post(
                f"/api/escalations/{esc_id}/verdict",
                json={"verdict": "confirmed", "computed_at": "2024-01-01"},
            )
            resp = await client.get(f"/api/cases/{case.id}")
    finally:
        app.dependency_overrides.clear()

    data = resp.json()
    assert data["escalation_status"] == "resolved"
    assert data["latest_verdict"] == "confirmed"
