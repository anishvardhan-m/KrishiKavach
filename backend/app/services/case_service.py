"""Case management service for KrishiKavach.

Handles:
- Creating cases from prediction results
- Follow-up scheduling and tracking
- Feedback collection
- Demo time simulation for SIH demonstration
"""
from __future__ import annotations

from datetime import datetime, date, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Case, CaseFeedback, Farmer, Farm, DiseaseReport
from app.services.prediction import DiseasePrediction, Recommendation


# ---------------------------------------------------------------------------
# Demo time simulation
# ---------------------------------------------------------------------------

_demo_clock: Optional[datetime] = None


def get_demo_clock() -> datetime:
    """Return current demo clock (UTC). Falls back to real time."""
    if _demo_clock is not None:
        return _demo_clock
    return datetime.now(timezone.utc)


def get_demo_date() -> date:
    """Return the current demo date."""
    return get_demo_clock().date()


def set_demo_clock(dt: datetime) -> None:
    """Set the demo clock to a specific datetime (UTC)."""
    global _demo_clock
    _demo_clock = dt


def advance_demo_days(days: int) -> date:
    """Advance the demo clock by `days` days from current demo date."""
    global _demo_clock
    current = get_demo_clock()
    _demo_clock = current + timedelta(days=days)
    return _demo_clock.date()


def reset_demo_clock() -> None:
    """Reset demo clock to real time."""
    global _demo_clock
    _demo_clock = None


# ---------------------------------------------------------------------------
# Follow-up scheduling
# ---------------------------------------------------------------------------

def calculate_next_follow_up(
    recommendation: Recommendation,
    detected_at: datetime,
) -> date:
    """Calculate the next follow-up date based on recommendation interval."""
    follow_up_delta = timedelta(days=recommendation.follow_up_days)
    return (detected_at + follow_up_delta).date()


# ---------------------------------------------------------------------------
# Case creation
# ---------------------------------------------------------------------------

async def create_case_from_prediction(
    session: AsyncSession,
    farm_id: UUID,
    farmer_id: UUID,
    prediction: DiseasePrediction,
    recommendation: Recommendation,
    image_path: Optional[str] = None,
    image_thumbnail_path: Optional[str] = None,
    district: Optional[str] = None,
) -> Case:
    """Create a new case from a prediction result."""
    now = get_demo_clock()
    next_follow_up = calculate_next_follow_up(recommendation, now)

    case = Case(
        farm_id=farm_id,
        farmer_id=farmer_id,
        image_path=image_path,
        image_thumbnail_path=image_thumbnail_path,
        predicted_disease=prediction.disease,
        predicted_crop=prediction.crop,
        confidence=prediction.confidence,
        severity=prediction.severity.value,
        uncertainty_flag=prediction.uncertainty_flag,
        detected_at=now,
        recommendation_given_at=now,
        next_follow_up_at=next_follow_up,
        case_status="active" if not prediction.severity.value == "high" else "escalated",
        notes=recommendation.recommendation_text,
    )
    session.add(case)
    await session.flush()  # Get the ID without committing
    return case


# ---------------------------------------------------------------------------
# Follow-up and feedback
# ---------------------------------------------------------------------------

async def get_cases_due_for_follow_up(
    session: AsyncSession,
    as_of_date: Optional[date] = None,
    farmer_id: Optional[UUID] = None,
) -> list[Case]:
    """Return active cases where next_follow_up_at <= as_of_date.

    When farmer_id is provided, only that farmer's cases are returned.
    """
    check_date = as_of_date or get_demo_date()
    stmt = (
        select(Case)
        .where(Case.case_status == "active")
        .where(Case.next_follow_up_at <= check_date)
    )
    if farmer_id is not None:
        stmt = stmt.where(Case.farmer_id == farmer_id)
    stmt = stmt.order_by(Case.next_follow_up_at)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def record_feedback(
    session: AsyncSession,
    case_id: UUID,
    farmer_id: Optional[UUID],
    attempted_intervention: bool,
    crop_improved: Optional[bool],
    farmer_notes: Optional[str],
) -> CaseFeedback:
    """Record farmer feedback for a case and update case state."""
    now = get_demo_clock()

    # Create feedback record
    feedback = CaseFeedback(
        case_id=case_id,
        farmer_id=farmer_id,
        attempted_intervention=attempted_intervention,
        crop_improved=crop_improved,
        farmer_notes=farmer_notes,
        feedback_at=now,
    )
    session.add(feedback)

    # Update case
    await session.execute(
        update(Case)
        .where(Case.id == case_id)
        .values(
            treatment_attempted_at=now if attempted_intervention else None,
            last_follow_up_at=now,
            # If improved, mark resolved; if not improved, schedule another follow-up
            next_follow_up_at=(
                (get_demo_date() + timedelta(days=7))
                if crop_improved is False
                else None
            ),
            case_status=(
                "resolved"
                if crop_improved is True
                else "active"
            ),
        )
    )
    await session.flush()
    return feedback


async def get_case_by_id(
    session: AsyncSession,
    case_id: UUID,
) -> Optional[Case]:
    """Fetch a single case by ID."""
    stmt = select(Case).where(Case.id == case_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_farmer_cases(
    session: AsyncSession,
    farmer_id: UUID,
    include_resolved: bool = False,
) -> list[Case]:
    """Fetch all cases for a farmer."""
    stmt = select(Case).where(Case.farmer_id == farmer_id)
    if not include_resolved:
        stmt = stmt.where(Case.case_status == "active")
    stmt = stmt.order_by(Case.detected_at.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Farmer management
# ---------------------------------------------------------------------------

async def get_or_create_demo_farmer(
    session: AsyncSession,
    name: str = "Demo Farmer",
    district: str = "Pune",
    village: str = "Pirangut",
) -> Farmer:
    """Get or create a demo farmer for the SIH demonstration.

    If a farmer already exists in the DB (e.g. from seed data),
    returns the first one found. Otherwise creates a new one.
    """
    # Try to find an existing farmer first
    stmt = select(Farmer).limit(1)
    result = await session.execute(stmt)
    farmer = result.scalar_one_or_none()

    if farmer is None:
        farmer = Farmer(
            name=name,
            phone="+919876543219",  # Different from seeded farmers
            village=village,
            district=district,
            state="Maharashtra",
            primary_language="marathi",
        )
        session.add(farmer)
        await session.flush()
        # Also create a demo farm for them
        farm = Farm(
            farmer_id=farmer.id,
            primary_crop="Tomato",
            area_hectares=1.5,
            location_point="SRID=4326;POINT(73.1276 18.5984)",  # Pirangut, Pune
        )
        session.add(farm)
        await session.flush()

    return farmer


async def get_demo_farm(session: AsyncSession, farmer_id: UUID) -> Optional[Farm]:
    """Get the first farm for a farmer."""
    stmt = select(Farm).where(Farm.farmer_id == farmer_id).limit(1)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
