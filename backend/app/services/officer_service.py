"""Officer dashboard backend service for KrishiKavach (SIH26131).

Provides district-level aggregated data for the Agriculture Officer dashboard:
  - Case counts (total, active, resolved, escalated, follow-up due)
  - Disease breakdown per (crop, disease)
  - Severity counts
  - District risk level (via compute_forecast engine)
  - Intervention / feedback counts (from CaseFeedback)
  - Active outbreak reports
  - Latest weather context
  - Hardcoded district centroids (no external API) for future heatmap

No farmer PII (names, phones, farmer IDs) is ever exposed.
No new database tables are created.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy import select, func, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Case, CaseFeedback, DiseaseReport, Farmer, Farm, WeatherContext
from app.services.case_service import get_demo_clock
from app.services.risk_forecast import compute_forecast


# ---------------------------------------------------------------------------
# Maharashtra district centroids (WGS-84, hardcoded — no external API).
# Sources: public geocoding references for Maharashtra district headquarters.
# ---------------------------------------------------------------------------

DISTRICT_CENTROIDS: dict[str, tuple[float, float]] = {
    "Ahmednagar":    (74.73, 19.58),
    "Akola":         (77.00, 20.71),
    "Amravati":      (77.75, 20.92),
    "Aurangabad":   (75.34, 19.88),
    "Beed":          (75.75, 18.99),
    "Bidar":         (77.52, 17.91),
    "Buldhana":      (76.18, 20.53),
    "Chandrapur":    (79.30, 19.48),
    "Dhule":         (74.77, 20.90),
    "Gadchiroli":    (80.31, 19.36),
    "Gondia":        (80.22, 21.45),
    "Hingoli":       (77.15, 19.75),
    "Jalgaon":       (75.56, 20.99),
    "Jalna":         (75.89, 19.83),
    "Kolhapur":      (74.26, 16.69),
    "Latur":         (76.56, 18.40),
    "Mumbai City":   (72.83, 18.97),
    "Mumbai Suburban": (72.87, 19.06),
    "Nagpur":        (79.09, 21.15),
    "Nanded":        (77.32, 19.14),
    "Nandurbar":     (74.24, 21.37),
    "Nashik":        (73.79, 19.99),
    "Osmanabad":     (76.04, 18.20),
    "Palghar":       (72.77, 19.67),
    "Parbhani":      (76.77, 19.27),
    "Pune":          (73.86, 18.52),
    "Raigad":        (73.01, 18.51),
    "Ratnagiri":     (73.34, 16.99),
    "Sangli":        (74.56, 16.85),
    "Satara":        (73.99, 17.69),
    "Sindhudurg":    (73.53, 16.05),
    "Solapur":       (75.92, 17.66),
    "Thane":         (72.97, 19.22),
    "Wardha":        (78.60, 20.79),
    "Washim":        (77.11, 20.12),
    "Yavatmal":      (78.13, 20.40),
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class DiseaseBreakdownEntry:
    crop: str
    disease: str
    case_count: int
    farm_count: int
    severity: str
    risk_level: str
    last_detected: Optional[str] = None


@dataclass
class InterventionStats:
    total_feedbacks: int
    attempted_treatment: int
    crop_improved: int
    crop_not_improved: int
    no_feedback_yet: int   # cases with no feedback record


@dataclass
class OutbreakSummary:
    crop_type: str
    disease_type: str
    risk_level: str
    affected_farms: int
    total_cases_reported: int


@dataclass
class WeatherSummary:
    soil_moisture_percent: Optional[float]
    evapotranspiration_mm: Optional[float]
    temperature_c: Optional[float]
    humidity_percent: Optional[float]
    recorded_at: Optional[str] = None


@dataclass
class DistrictRiskProfile:
    risk_score: float
    risk_level: str
    recommended_action: str
    explanation: str
    # contributing_factors is optional — only included when ?include_factors=true
    contributing_factors: Optional[list[dict]] = None


@dataclass
class DistrictSummary:
    district: str
    state: str = "Maharashtra"
    centroid_lon: Optional[float] = None
    centroid_lat: Optional[float] = None
    # Case counts
    total_cases: int = 0
    active_cases: int = 0
    resolved_cases: int = 0
    escalated_cases: int = 0
    follow_up_due: int = 0
    # Severity breakdown
    severity_low: int = 0
    severity_medium: int = 0
    severity_high: int = 0
    # Disease breakdown
    disease_breakdown: list[DiseaseBreakdownEntry] = field(default_factory=list)
    # Interventions
    interventions: Optional[InterventionStats] = None
    # Active outbreaks (from seeded DiseaseReport)
    active_outbreaks: list[OutbreakSummary] = field(default_factory=list)
    # Weather
    weather: Optional[WeatherSummary] = None
    # Risk profile (from compute_forecast engine)
    risk_profile: Optional[DistrictRiskProfile] = None
    # Meta
    computed_at: str = field(default_factory=lambda: get_demo_clock().isoformat())


# ---------------------------------------------------------------------------
# Aggregation helpers (async, DB-backed)
# ---------------------------------------------------------------------------

async def _case_counts(
    session: AsyncSession,
    district: str,
) -> tuple[int, int, int, int, int]:
    """Return (total, active, resolved, escalated, follow_up_due) for a district."""
    stmt = (
        select(func.count(Case.id))
        .join(Farm, Case.farm_id == Farm.id)
        .join(Farmer, Farm.farmer_id == Farmer.id)
        .where(Farmer.district == district)
    )
    total = (await session.execute(stmt)).scalar() or 0

    active = (await session.execute(
        select(func.count(Case.id))
        .join(Farm, Case.farm_id == Farm.id)
        .join(Farmer, Farm.farmer_id == Farmer.id)
        .where(Farmer.district == district)
        .where(Case.case_status == "active")
    )).scalar() or 0

    resolved = (await session.execute(
        select(func.count(Case.id))
        .join(Farm, Case.farm_id == Farm.id)
        .join(Farmer, Farm.farmer_id == Farmer.id)
        .where(Farmer.district == district)
        .where(Case.case_status == "resolved")
    )).scalar() or 0

    escalated = (await session.execute(
        select(func.count(Case.id))
        .join(Farm, Case.farm_id == Farm.id)
        .join(Farmer, Farm.farmer_id == Farmer.id)
        .where(Farmer.district == district)
        .where(Case.case_status == "escalated")
    )).scalar() or 0

    today = get_demo_clock().date()
    follow_up_due = (await session.execute(
        select(func.count(Case.id))
        .join(Farm, Case.farm_id == Farm.id)
        .join(Farmer, Farm.farmer_id == Farmer.id)
        .where(Farmer.district == district)
        .where(Case.next_follow_up_at <= today)
        .where(Case.case_status == "active")
    )).scalar() or 0

    return total, active, resolved, escalated, follow_up_due


async def _severity_counts(
    session: AsyncSession,
    district: str,
) -> tuple[int, int, int]:
    """Return (low, medium, high) severity counts for a district."""
    low = (await session.execute(
        select(func.count(Case.id))
        .join(Farm, Case.farm_id == Farm.id)
        .join(Farmer, Farm.farmer_id == Farmer.id)
        .where(Farmer.district == district)
        .where(Case.severity == "low")
    )).scalar() or 0

    medium = (await session.execute(
        select(func.count(Case.id))
        .join(Farm, Case.farm_id == Farm.id)
        .join(Farmer, Farm.farmer_id == Farmer.id)
        .where(Farmer.district == district)
        .where(Case.severity == "medium")
    )).scalar() or 0

    high = (await session.execute(
        select(func.count(Case.id))
        .join(Farm, Case.farm_id == Farm.id)
        .join(Farmer, Farm.farmer_id == Farmer.id)
        .where(Farmer.district == district)
        .where(Case.severity == "high")
    )).scalar() or 0

    return low, medium, high


async def _disease_breakdown(
    session: AsyncSession,
    district: str,
) -> list[DiseaseBreakdownEntry]:
    """Return per-(crop, disease) breakdown for a district.

    Aggregates case counts, farm counts, most-recent severity and risk_level.
    """
    # Group by crop + disease, count cases and distinct farms.
    stmt = (
        select(
            Case.predicted_crop,
            Case.predicted_disease,
            Case.severity,
            func.count(Case.id).label("case_count"),
            func.count(distinct(Case.farm_id)).label("farm_count"),
            func.max(Case.detected_at).label("last_detected"),
        )
        .join(Farm, Case.farm_id == Farm.id)
        .join(Farmer, Farm.farmer_id == Farmer.id)
        .where(Farmer.district == district)
        .where(Case.predicted_disease.isnot(None))
        .group_by(Case.predicted_crop, Case.predicted_disease, Case.severity)
        .order_by(func.count(Case.id).desc())
    )
    result = await session.execute(stmt)
    rows = result.all()

    # Also fetch the latest DiseaseReport risk_level per crop+ disease.
    outbreak_stmt = (
        select(
            DiseaseReport.crop_type,
            DiseaseReport.disease_type,
            DiseaseReport.risk_level,
        )
        .where(DiseaseReport.district == district)
        .order_by(DiseaseReport.valid_from.desc())
    )
    outbreak_result = await session.execute(outbreak_stmt)
    outbreak_map: dict[tuple[str, str], str] = {}
    for row in outbreak_result.all():
        key = (row.crop_type or "", row.disease_type or "")
        if key not in outbreak_map:
            outbreak_map[key] = row.risk_level or "medium"

    entries: list[DiseaseBreakdownEntry] = []
    for row in rows:
        key = (row.predicted_crop or "Unknown", row.predicted_disease or "Unknown")
        outbreak_risk = outbreak_map.get(key, "medium")
        entries.append(DiseaseBreakdownEntry(
            crop=row.predicted_crop or "Unknown",
            disease=row.predicted_disease or "Unknown",
            case_count=row.case_count,
            farm_count=row.farm_count,
            severity=row.severity or "medium",
            risk_level=outbreak_risk,
            last_detected=row.last_detected.isoformat() if row.last_detected else None,
        ))
    return entries


async def _intervention_stats(
    session: AsyncSession,
    district: str,
) -> InterventionStats:
    """Return intervention/feedback statistics for a district.

    Joins CaseFeedback → Case → Farm → Farmer to filter by district.
    Cases with no feedback record count toward no_feedback_yet.
    """
    total_feedbacks = (await session.execute(
        select(func.count(CaseFeedback.id))
        .join(Case, CaseFeedback.case_id == Case.id)
        .join(Farm, Case.farm_id == Farm.id)
        .join(Farmer, Farm.farmer_id == Farmer.id)
        .where(Farmer.district == district)
    )).scalar() or 0

    attempted = (await session.execute(
        select(func.count(CaseFeedback.id))
        .join(Case, CaseFeedback.case_id == Case.id)
        .join(Farm, Case.farm_id == Farm.id)
        .join(Farmer, Farm.farmer_id == Farmer.id)
        .where(Farmer.district == district)
        .where(CaseFeedback.attempted_intervention == True)
    )).scalar() or 0

    improved = (await session.execute(
        select(func.count(CaseFeedback.id))
        .join(Case, CaseFeedback.case_id == Case.id)
        .join(Farm, Case.farm_id == Farm.id)
        .join(Farmer, Farm.farmer_id == Farmer.id)
        .where(Farmer.district == district)
        .where(CaseFeedback.crop_improved == True)
    )).scalar() or 0

    not_improved = (await session.execute(
        select(func.count(CaseFeedback.id))
        .join(Case, CaseFeedback.case_id == Case.id)
        .join(Farm, Case.farm_id == Farm.id)
        .join(Farmer, Farm.farmer_id == Farmer.id)
        .where(Farmer.district == district)
        .where(CaseFeedback.crop_improved == False)
    )).scalar() or 0

    # Cases with no feedback record at all
    no_feedback = (await session.execute(
        select(func.count(Case.id))
        .join(Farm, Case.farm_id == Farm.id)
        .join(Farmer, Farm.farmer_id == Farmer.id)
        .where(Farmer.district == district)
        .where(
            ~Case.id.in_(
                select(CaseFeedback.case_id)
            )
        )
    )).scalar() or 0

    return InterventionStats(
        total_feedbacks=total_feedbacks,
        attempted_treatment=attempted,
        crop_improved=improved,
        crop_not_improved=not_improved,
        no_feedback_yet=no_feedback,
    )


async def _active_outbreaks(
    session: AsyncSession,
    district: str,
) -> list[OutbreakSummary]:
    """Return active outbreak reports for a district (no farmer PII)."""
    today = get_demo_clock().date()
    stmt = (
        select(DiseaseReport)
        .where(DiseaseReport.district == district)
        .where(DiseaseReport.valid_from <= today)
        .where(DiseaseReport.valid_to >= today)
        .order_by(DiseaseReport.risk_level.desc(), DiseaseReport.valid_from.desc())
    )
    result = await session.execute(stmt)
    return [
        OutbreakSummary(
            crop_type=r.crop_type or "Unknown",
            disease_type=r.disease_type or "Unknown",
            risk_level=r.risk_level or "medium",
            affected_farms=r.affected_farms,
            total_cases_reported=r.total_cases_reported,
        )
        for r in result.scalars().all()
    ]


async def _latest_weather(
    session: AsyncSession,
    district: str,
) -> Optional[WeatherSummary]:
    """Return the latest weather context for a district."""
    stmt = (
        select(WeatherContext)
        .where(WeatherContext.district == district)
        .order_by(WeatherContext.recorded_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    r = result.scalar_one_or_none()
    if r is None:
        return None
    return WeatherSummary(
        soil_moisture_percent=r.soil_moisture_percent,
        evapotranspiration_mm=r.evapotranspiration_mm,
        temperature_c=r.temperature_c,
        humidity_percent=r.humidity_percent,
        recorded_at=r.recorded_at.isoformat() if r.recorded_at else None,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def get_district_summary(
    session: AsyncSession,
    district: str,
    *,
    include_factors: bool = False,
) -> DistrictSummary:
    """Build a complete district summary for the officer dashboard.

    Uses ONLY existing tables. No farmer PII is included.
    The risk profile is computed via the existing compute_forecast engine.
    """
    total, active, resolved, escalated, follow_up_due = await _case_counts(
        session, district,
    )
    sev_low, sev_medium, sev_high = await _severity_counts(session, district)
    disease_breakdown = await _disease_breakdown(session, district)
    interventions = await _intervention_stats(session, district)
    outbreaks = await _active_outbreaks(session, district)
    weather = await _latest_weather(session, district)

    # Risk profile via the existing engine
    forecast = await compute_forecast(session, district=district, crop=None, disease=None)
    risk_factors = None
    if include_factors:
        risk_factors = [
            {
                "name": f.name,
                "weight": f.weight,
                "raw_signal": round(f.raw_signal, 2),
                "contribution": round(f.contribution, 2),
                "note": f.note,
            }
            for f in forecast.contributing_factors
        ]
    risk_profile = DistrictRiskProfile(
        risk_score=round(forecast.risk_score, 2),
        risk_level=forecast.risk_level,
        recommended_action=forecast.recommended_action,
        explanation=forecast.explanation,
        contributing_factors=risk_factors,
    )

    centroid = DISTRICT_CENTROIDS.get(district)
    lon, lat = centroid if centroid else (None, None)

    return DistrictSummary(
        district=district,
        state="Maharashtra",
        centroid_lon=lon,
        centroid_lat=lat,
        total_cases=total,
        active_cases=active,
        resolved_cases=resolved,
        escalated_cases=escalated,
        follow_up_due=follow_up_due,
        severity_low=sev_low,
        severity_medium=sev_medium,
        severity_high=sev_high,
        disease_breakdown=disease_breakdown,
        interventions=interventions,
        active_outbreaks=outbreaks,
        weather=weather,
        risk_profile=risk_profile,
    )


async def get_all_district_summaries(
    session: AsyncSession,
    *,
    include_factors: bool = False,
) -> list[DistrictSummary]:
    """Build summaries for all Maharashtra districts that have data or a centroid.

    Returns a list sorted by district name.
    """
    summaries: list[DistrictSummary] = []
    for district in sorted(DISTRICT_CENTROIDS.keys()):
        s = await get_district_summary(session, district, include_factors=include_factors)
        summaries.append(s)
    return summaries
