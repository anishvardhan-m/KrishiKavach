"""Expert escalation service for KrishiKavach (SIH26131).

Implements the expert-review workflow using the existing Escalation model:
  - Create an escalation for a case
  - Submit an expert verdict (confirmed / rejected / needs_more_evidence)
  - List escalations (active / resolved / all)
  - Resolve escalation status and latest verdict for a case

Constraints:
  - No new database tables
  - No external APIs
  - Duplicate-active-escalation prevention (one active per case)
  - Validates verdict values strictly
  - Excludes farmer PII (names, phones, farmer IDs) from list responses;
    `EscalationResponse` only carries public context fields.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Case, Escalation, Expert, Farmer, Farm
from app.services.case_service import get_demo_clock


# Valid verdict values — keep aligned with the Escalation.expert_verdict column.
VALID_VERDICTS = ("confirmed", "rejected", "needs_more_evidence")


class EscalationError(Exception):
    """Raised when an escalation operation cannot be performed."""


async def get_active_escalation(
    session: AsyncSession,
    case_id: UUID,
) -> Optional[Escalation]:
    """Return the active (unresolved) escalation for a case, or None."""
    stmt = (
        select(Escalation)
        .where(Escalation.case_id == case_id)
        .where(Escalation.resolved_at.is_(None))
        .order_by(Escalation.escalated_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def escalation_status_for_case(
    session: AsyncSession,
    case_id: UUID,
) -> tuple[Optional[str], Optional[str]]:
    """Return (status, latest_verdict) for a case.

    status: "active" if any escalation exists without resolved_at;
            "resolved" if at least one escalation exists and all are resolved;
            None if no escalations exist.
    latest_verdict: most recent non-null expert_verdict across all escalations,
                    or None if no verdicts have been recorded.
    """
    stmt = (
        select(Escalation)
        .where(Escalation.case_id == case_id)
        .order_by(Escalation.escalated_at.desc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    if not rows:
        return None, None
    has_active = any(r.resolved_at is None for r in rows)
    status = "active" if has_active else "resolved"
    latest_verdict: Optional[str] = None
    for r in rows:
        if r.expert_verdict is not None:
            latest_verdict = r.expert_verdict
            break
    return status, latest_verdict


async def create_escalation(
    session: AsyncSession,
    *,
    case_id: UUID,
    expert_id: Optional[UUID] = None,
    reason: Optional[str] = None,
) -> Escalation:
    """Create an escalation for a case.

    Raises:
        EscalationError: if the case does not exist or an active escalation
        already exists for this case.
    """
    case = (await session.execute(
        select(Case).where(Case.id == case_id)
    )).scalar_one_or_none()
    if case is None:
        raise EscalationError("Case not found")

    existing = await get_active_escalation(session, case_id)
    if existing is not None:
        raise EscalationError(
            "An active escalation already exists for this case"
        )

    if expert_id is not None:
        expert = (await session.execute(
            select(Expert).where(Expert.id == expert_id)
        )).scalar_one_or_none()
        if expert is None:
            raise EscalationError(f"Expert {expert_id} not found")

    now = get_demo_clock()
    # If the existing case_status is "active" or "resolved", move it to
    # "escalated" so the farmer-side UI can surface this state. If already
    # escalated, leave it as-is.
    if case.case_status in ("active", "resolved"):
        case.case_status = "escalated"

    escalation = Escalation(
        case_id=case_id,
        expert_id=expert_id,
        escalated_at=now,
        resolved_at=None,
        expert_notes=reason,  # initial reason is stored as the first notes line
        expert_verdict=None,
    )
    session.add(escalation)
    await session.flush()
    return escalation


async def submit_verdict(
    session: AsyncSession,
    *,
    escalation_id: UUID,
    verdict: str,
    expert_notes: Optional[str] = None,
    expert_id: Optional[UUID] = None,
) -> Escalation:
    """Submit an expert verdict for an escalation.

    Validates the verdict and sets `resolved_at` to mark the escalation
    as closed. If the verdict is "needs_more_evidence", the escalation is
    still resolved (the expert has decided), and the underlying case
    returns to "active" so a new escalation can be raised if needed.

    Raises:
        EscalationError: if the escalation does not exist, the verdict is
        invalid, or the escalation is already resolved.
    """
    if verdict not in VALID_VERDICTS:
        raise EscalationError(
            f"Invalid verdict {verdict!r}. "
            f"Must be one of: {', '.join(VALID_VERDICTS)}"
        )
    esc = (await session.execute(
        select(Escalation).where(Escalation.id == escalation_id)
    )).scalar_one_or_none()
    if esc is None:
        raise EscalationError("Escalation not found")
    if esc.resolved_at is not None:
        raise EscalationError("Escalation is already resolved")

    now = get_demo_clock()
    esc.expert_verdict = verdict
    esc.expert_notes = expert_notes if expert_notes is not None else esc.expert_notes
    esc.resolved_at = now
    if expert_id is not None:
        esc.expert_id = expert_id

    # Update the underlying case status depending on the verdict.
    case = (await session.execute(
        select(Case).where(Case.id == esc.case_id)
    )).scalar_one_or_none()
    if case is not None:
        if verdict == "confirmed":
            # Confirmed — farmer should continue/apply the recommendation.
            case.case_status = "active"
        elif verdict == "rejected":
            case.case_status = "closed"
        elif verdict == "needs_more_evidence":
            # Reset to active so a new escalation can be raised.
            case.case_status = "active"

    await session.flush()
    return esc


async def list_escalations(
    session: AsyncSession,
    *,
    status: str = "all",
    limit: int = 100,
) -> list[tuple[Escalation, Optional[str], Optional[str], Optional[str]]]:
    """List escalations, joined with case/disease context and district.

    Returns a list of (Escalation, district, predicted_disease, predicted_crop)
    tuples. `status` is one of "active", "resolved", "all".

    No farmer PII is fetched — only aggregated case context already
    suitable for the officer dashboard.
    """
    stmt = (
        select(Escalation, Farmer.district, Case.predicted_disease, Case.predicted_crop)
        .join(Case, Escalation.case_id == Case.id)
        .join(Farm, Case.farm_id == Farm.id)
        .join(Farmer, Farm.farmer_id == Farmer.id)
        .order_by(Escalation.escalated_at.desc())
        .limit(limit)
    )
    if status == "active":
        stmt = stmt.where(Escalation.resolved_at.is_(None))
    elif status == "resolved":
        stmt = stmt.where(Escalation.resolved_at.isnot(None))
    elif status != "all":
        raise EscalationError(f"Invalid status filter {status!r}")
    result = await session.execute(stmt)
    return [(row[0], row[1], row[2], row[3]) for row in result.all()]


async def count_active_escalations(session: AsyncSession) -> int:
    stmt = (
        select(func.count(Escalation.id))
        .where(Escalation.resolved_at.is_(None))
    )
    return int((await session.execute(stmt)).scalar() or 0)