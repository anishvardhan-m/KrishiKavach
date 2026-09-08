"""Lightweight, explainable risk forecasting for KrishiKavach (SIH26131).

Computes a deterministic 0-100 risk score at case-creation time and via the
GET /api/risk endpoint, using ONLY data already in the project:

  * Live cases table (district/crop/disease in last 14 days)
  * Seeded disease_reports (district/crop/disease aggregates)
  * Seeded weather_contexts (soil moisture + evapotranspiration only —
    temperature/humidity are NOT in the project yet, so that factor
    contributes 0 when those columns are NULL)
  * Predicted severity (low/medium/high)
  * Model confidence (uncertainty inverted)

No external APIs, no LLM, no ML model, no new tables. Heuristic only.

Honesty contract:
    This is NOT a trained model. Every contribution is named and explainable.
    The risk_forecast is a transparent blend of signals the project already
    trusts. It MUST NOT be presented as "ML-based prediction".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Case, DiseaseReport, Farm, WeatherContext
from app.services.case_service import get_demo_clock


# ---------------------------------------------------------------------------
# Constants — weight allocations and bucketing
# ---------------------------------------------------------------------------

# Maximum contribution each factor can add to the 0-100 score.
W_CASES = 30.0
W_OUTBREAK = 25.0
W_WEATHER = 20.0          # reduced from 25 to make room for W_GEO; clipped at W_WEATHER anyway
W_SEVERITY = 15.0
W_CONFIDENCE = 5.0
W_GEO = 10.0             # proximity to nearby farm-coordinate cases (0-10 km)

# Recent-cases lookback window in days.
RECENT_CASES_WINDOW_DAYS = 14

# Outbreak-signal values per seeded risk_level.
OUTBREAK_SIGNAL = {
    "low": 5.0,
    "medium": 20.0,
    "high": 35.0,
    "critical": 45.0,
}

# Severity-signal values per predicted severity.
SEVERITY_SIGNAL = {
    "low": 2.0,
    "medium": 8.0,
    "high": 15.0,
}

# Score thresholds for risk levels.
RISK_BUCKET_THRESHOLDS = [
    (30.0, "low"),
    (60.0, "medium"),
    (85.0, "high"),
    (float("inf"), "critical"),
]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class RiskFactor:
    """One named contribution to the final risk score."""
    name: str
    weight: float          # max weight allocated to this factor
    raw_signal: float      # signal value before weight scaling
    contribution: float    # how much this factor added to the final score
    note: str              # human-readable note for the explanation


@dataclass
class RiskForecast:
    """Result of a risk forecast computation."""
    risk_score: float              # 0-100, clipped
    risk_level: str                # low | medium | high | critical
    contributing_factors: list[RiskFactor] = field(default_factory=list)
    recommended_action: str = ""
    explanation: str = ""
    computed_at: datetime = field(default_factory=lambda: get_demo_clock())
    demo_time_used: datetime = field(default_factory=lambda: get_demo_clock())

    def to_dict(self) -> dict:
        return {
            "risk_score": round(self.risk_score, 2),
            "risk_level": self.risk_level,
            "contributing_factors": [
                {
                    "name": f.name,
                    "weight": f.weight,
                    "raw_signal": round(f.raw_signal, 2),
                    "contribution": round(f.contribution, 2),
                    "note": f.note,
                }
                for f in self.contributing_factors
            ],
            "recommended_action": self.recommended_action,
            "explanation": self.explanation,
            "computed_at": self.computed_at.isoformat(),
            "demo_time_used": self.demo_time_used.isoformat(),
        }


# ---------------------------------------------------------------------------
# Pure helpers — deterministic, no I/O, easy to unit-test
# ---------------------------------------------------------------------------

# Geospatial proximity parameters.
# Within this radius (km) of the farmer's farm, OTHER farms with the same
# predicted crop+ disease are counted as nearby risk sources. Uses simple
# great-circle approximation (haversine) — no PostGIS dependency.
GEO_NEAR_RADIUS_KM = 10.0
# Map a count of nearby cases to the 0..W_GEO signal.
GEO_FULL_SIGNAL_COUNT = 3

EARTH_RADIUS_KM = 6371.0088


def parse_wkt_point(text: Optional[str]) -> Optional[tuple[float, float]]:
    """Parse a PostGIS-style WKT POINT(lon lat) string.

    Returns (lon, lat) in degrees, or None if the input is not parseable.
    Accepts whitespace and optional trailing precision. Case-sensitive on
    the leading 'POINT' token but tolerant of trailing extra text.
    """
    if not text:
        return None
    s = text.strip()
    # Accept "POINT(lon lat)" and "POINT ( lon lat )"
    upper = s.upper()
    if not upper.startswith("POINT"):
        return None
    # Find the first '(' and the matching ')'
    lparen = s.find("(")
    rparen = s.rfind(")")
    if lparen < 0 or rparen < 0 or rparen <= lparen:
        return None
    body = s[lparen + 1 : rparen].strip()
    parts = body.replace(",", " ").split()
    if len(parts) != 2:
        return None
    try:
        lon = float(parts[0])
        lat = float(parts[1])
    except ValueError:
        return None
    if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
        return None
    return (lon, lat)


def haversine_km(
    lon1: float, lat1: float, lon2: float, lat2: float,
) -> float:
    """Great-circle distance in kilometres between two (lon, lat) points."""
    import math
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2.0) ** 2
    )
    c = 2.0 * math.asin(min(1.0, math.sqrt(a)))
    return EARTH_RADIUS_KM * c


def geo_proximity_signal(
    nearby_count: int,
    full_signal_count: int = GEO_FULL_SIGNAL_COUNT,
) -> tuple[float, str]:
    """Map a count of nearby (within GEO_NEAR_RADIUS_KM) cases to 0..W_GEO.

    Linear ramp: 0 cases -> 0, full_signal_count cases -> W_GEO.
    Capped at W_GEO.
    """
    if nearby_count <= 0 or full_signal_count <= 0:
        return 0.0, (
            "No nearby farm-coordinate cases within "
            f"{GEO_NEAR_RADIUS_KM:.0f} km"
        )
    ratio = min(nearby_count / full_signal_count, 1.0)
    return ratio * W_GEO, (
        f"{nearby_count} nearby farm-coordinate case(s) within "
        f"{GEO_NEAR_RADIUS_KM:.0f} km"
    )


def bucketize(score: float) -> str:
    """Map a 0-100 score to a low/medium/high/critical bucket.

    Thresholds (from RISK_BUCKET_THRESHOLDS):
        <30   -> low
        <60   -> medium
        <85   -> high
        >=85  -> critical
    """
    if score < 0:
        score = 0.0
    if score > 100:
        score = 100.0
    for upper, label in RISK_BUCKET_THRESHOLDS:
        if score < upper:
            return label
    return "critical"


def clip_score(score: float) -> float:
    """Clip a raw score to [0, 100]."""
    if score < 0.0:
        return 0.0
    if score > 100.0:
        return 100.0
    return score


def recent_cases_signal(
    recent_count: int,
    max_for_full_signal: int = 5,
) -> tuple[float, str]:
    """Map a recent-case count to a 0..W_CASES signal.

    Linear ramp: 0 cases -> 0, max_for_full_signal cases -> W_CASES.
    Capped at W_CASES.
    """
    if recent_count <= 0 or max_for_full_signal <= 0:
        return 0.0, "0 cases of the same disease in this district in the last 14 days"
    ratio = min(recent_count / max_for_full_signal, 1.0)
    return ratio * W_CASES, (
        f"{recent_count} case(s) of the same disease in this district in the last 14 days"
    )


def outbreak_signal(risk_level: Optional[str]) -> tuple[float, str]:
    """Map a seeded disease_report risk_level to a 0..W_OUTBREAK signal.

    Unknown / missing risk_level contributes 0.
    """
    if not risk_level:
        return 0.0, "No seeded outbreak report for this district/crop"
    key = risk_level.strip().lower()
    value = OUTBREAK_SIGNAL.get(key, 0.0)
    if value == 0.0:
        return 0.0, f"No seeded outbreak report for this district/crop (risk_level={risk_level!r})"
    return value, f"District outbreak report risk_level={risk_level!r}"


def weather_signal(
    soil_moisture_percent: Optional[float],
    evapotranspiration_mm: Optional[float],
    temperature_c: Optional[float],
    humidity_percent: Optional[float],
) -> tuple[float, str]:
    """Compute the environmental risk signal.

    IMPORTANT: We ONLY use data that exists in the project. If a column is
    NULL (e.g. temperature_c, humidity_percent are not seeded yet), the
    factor gracefully contributes 0. We do NOT invent or stub values.
    """
    parts: list[str] = []
    score = 0.0

    # Soil moisture: very wet (>70%) or very dry (<20%) increases risk
    if soil_moisture_percent is not None:
        sm = float(soil_moisture_percent)
        if sm > 70.0:
            contribution = 12.0
            parts.append(f"soil moisture {sm:.1f}% (high — fungal pressure)")
        elif sm < 20.0:
            contribution = 8.0
            parts.append(f"soil moisture {sm:.1f}% (very dry — drought stress)")
        else:
            contribution = 0.0
            parts.append(f"soil moisture {sm:.1f}% (within normal range)")
        score += contribution
    # else: column not populated yet; do not invent a value

    # Evapotranspiration: high ET (water demand) increases stress risk
    if evapotranspiration_mm is not None:
        et = float(evapotranspiration_mm)
        if et > 5.0:
            contribution = 13.0
            parts.append(f"evapotranspiration {et:.2f} mm (high water demand)")
        elif et > 3.0:
            contribution = 7.0
            parts.append(f"evapotranspiration {et:.2f} mm (moderate)")
        else:
            contribution = 0.0
            parts.append(f"evapotranspiration {et:.2f} mm (normal)")
        score += contribution

    # Temperature and humidity — the WeatherContext model has these columns
    # but the seed loader does not populate them. We only score if BOTH are
    # present. Otherwise we contribute 0 honestly.
    if temperature_c is not None and humidity_percent is not None:
        t = float(temperature_c)
        h = float(humidity_percent)
        # Warm + humid favours fungal/oomycete disease pressure
        if t >= 20.0 and h >= 80.0:
            score = min(score + 10.0, W_WEATHER)
            parts.append(f"temp {t:.1f}°C + humidity {h:.1f}% (fungal-pressure band)")
        else:
            parts.append(
                f"temp {t:.1f}°C + humidity {h:.1f}% (not in fungal-pressure band)"
            )

    if not parts:
        return 0.0, "No environmental data available for this district yet"

    score = min(score, W_WEATHER)
    return score, "; ".join(parts)


def severity_signal(severity: Optional[str]) -> tuple[float, str]:
    """Map predicted severity to a 0..W_SEVERITY signal."""
    if not severity:
        return 0.0, "Predicted severity not available"
    key = severity.strip().lower()
    value = SEVERITY_SIGNAL.get(key, 0.0)
    if value == 0.0:
        return 0.0, f"Predicted severity {severity!r} (unknown level)"
    return value, f"Predicted severity={severity!r}"


def confidence_signal(confidence: Optional[float]) -> tuple[float, str]:
    """Map model confidence to a 0..W_CONFIDENCE uncertainty signal.

    Lower confidence -> more uncertainty -> more risk.
    contribution = (1 - confidence) * W_CONFIDENCE
    """
    if confidence is None:
        # Treat unknown confidence as maximum uncertainty
        return W_CONFIDENCE, "Model confidence unknown (treating as maximum uncertainty)"
    try:
        c = float(confidence)
    except (TypeError, ValueError):
        return W_CONFIDENCE, "Model confidence not numeric (treating as maximum uncertainty)"
    if c < 0.0:
        c = 0.0
    if c > 1.0:
        c = 1.0
    contribution = (1.0 - c) * W_CONFIDENCE
    return contribution, f"Model confidence={c:.2f} (uncertainty={1.0 - c:.2f})"


def explain(forecast: RiskForecast) -> str:
    """Compose a 1-2 sentence human-readable explanation."""
    level = forecast.risk_level
    score = forecast.risk_score
    notes = [f.note for f in forecast.contributing_factors]
    notes = [n for n in notes if n]
    summary = "; ".join(notes) if notes else "no contributing signals"
    return f"Risk level {level} (score {score:.1f}/100). Drivers: {summary}."


def recommend_action(level: str, crop: Optional[str], disease: Optional[str]) -> str:
    """Pick a recommended action string for the bucket."""
    if level == "critical":
        return (
            f"Escalate immediately. Multiple high-risk signals align for "
            f"{crop or 'this crop'}/{disease or 'this disease'}. Consider "
            f"coordinated treatment and notify the local agriculture officer."
        )
    if level == "high":
        return (
            f"Apply recommended treatment promptly for {crop or 'this crop'} "
            f"and monitor closely over the next 7 days."
        )
    if level == "medium":
        return (
            f"Apply recommended treatment for {crop or 'this crop'} and "
            f"schedule a follow-up in 7 days."
        )
    return (
        f"Continue routine monitoring for {crop or 'this crop'}; no urgent "
        f"action required at this time."
    )


# ---------------------------------------------------------------------------
# DB-backed computation
# ---------------------------------------------------------------------------

async def _count_recent_cases(
    session: AsyncSession,
    district: str,
    crop: Optional[str],
    disease: Optional[str],
    as_of: datetime,
) -> int:
    """Count cases in this district for the same crop+ disease in the last 14 days.

    Farm has no district column — district lives on Farmer, so we join
    Case -> Farm -> Farmer.
    """
    from app.models import Farmer
    cutoff = as_of - timedelta(days=RECENT_CASES_WINDOW_DAYS)
    stmt = (
        select(func.count(Case.id))
        .join(Farm, Case.farm_id == Farm.id)
        .join(Farmer, Farm.farmer_id == Farmer.id)
        .where(Farmer.district == district)
        .where(Case.detected_at >= cutoff)
    )
    if crop:
        stmt = stmt.where(Case.predicted_crop == crop)
    if disease:
        stmt = stmt.where(Case.predicted_disease == disease)
    result = await session.execute(stmt)
    return int(result.scalar() or 0)


async def _latest_outbreak(
    session: AsyncSession,
    district: str,
    crop: Optional[str],
    disease: Optional[str],
) -> Optional[DiseaseReport]:
    """Find the most recent seeded DiseaseReport for the given filters.

    Match priority: (district, crop, disease) > (district, crop) > (district).
    """
    # 1) exact match
    stmt = (
        select(DiseaseReport)
        .where(DiseaseReport.district == district)
        .order_by(DiseaseReport.valid_from.desc())
    )
    if crop:
        stmt = stmt.where(DiseaseReport.crop_type == crop)
    if disease:
        stmt = stmt.where(DiseaseReport.disease_type == disease)
    result = await session.execute(stmt.limit(1))
    report = result.scalar_one_or_none()
    if report is not None:
        return report

    # 2) (district, crop) fallback
    if crop:
        stmt = (
            select(DiseaseReport)
            .where(DiseaseReport.district == district)
            .where(DiseaseReport.crop_type == crop)
            .order_by(DiseaseReport.valid_from.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        report = result.scalar_one_or_none()
        if report is not None:
            return report

    # 3) (district) fallback
    stmt = (
        select(DiseaseReport)
        .where(DiseaseReport.district == district)
        .order_by(DiseaseReport.valid_from.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _latest_weather(
    session: AsyncSession,
    district: str,
) -> Optional[WeatherContext]:
    """Fetch the most recent weather context row for a district."""
    stmt = (
        select(WeatherContext)
        .where(WeatherContext.district == district)
        .order_by(WeatherContext.recorded_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _count_nearby_cases(
    session: AsyncSession,
    *,
    farm_id: str,
    farm_lon: float,
    farm_lat: float,
    crop: Optional[str],
    disease: Optional[str],
    as_of: datetime,
) -> int:
    """Count recent cases (same crop + disease) on farms whose stored
    WKT POINT is within GEO_NEAR_RADIUS_KM of (farm_lon, farm_lat).

    Uses the haversine formula in Python — no PostGIS required. The Case
    is fetched in Python and the distance check is done in-memory, which
    is fine for the demo dataset sizes.
    """
    cutoff = as_of - timedelta(days=RECENT_CASES_WINDOW_DAYS)
    # Get all recent cases with non-null location_point. We exclude the
    # current farm_id so we don't count the farmer's own case.
    stmt = (
        select(Case.id, Farm.location_point)
        .join(Farm, Case.farm_id == Farm.id)
        .where(Case.detected_at >= cutoff)
        .where(Farm.location_point.isnot(None))
        .where(Case.farm_id != farm_id)
    )
    if crop:
        stmt = stmt.where(Case.predicted_crop == crop)
    if disease:
        stmt = stmt.where(Case.predicted_disease == disease)

    result = await session.execute(stmt)
    count = 0
    for _case_id, loc in result.all():
        other = parse_wkt_point(loc)
        if other is None:
            continue
        d = haversine_km(farm_lon, farm_lat, other[0], other[1])
        if d <= GEO_NEAR_RADIUS_KM:
            count += 1
    return count


async def _farm_location(
    session: AsyncSession,
    farm_id: str,
) -> Optional[tuple[float, float]]:
    """Return parsed (lon, lat) for the given farm, or None if absent."""
    stmt = select(Farm.location_point).where(Farm.id == farm_id)
    result = await session.execute(stmt)
    raw = result.scalar_one_or_none()
    return parse_wkt_point(raw)


async def compute_forecast(
    session: AsyncSession,
    *,
    district: str,
    crop: Optional[str] = None,
    disease: Optional[str] = None,
    severity: Optional[str] = None,
    confidence: Optional[float] = None,
    as_of: Optional[datetime] = None,
    # Geospatial signals — optional; all three must be provided together.
    farm_id: Optional[str] = None,
    farm_lon: Optional[float] = None,
    farm_lat: Optional[float] = None,
) -> RiskForecast:
    """Compute a RiskForecast for a (district, crop, disease) tuple.

    The signature is intentionally narrow: it does NOT require a Case
    object. This makes it usable both from POST /api/predict (where a
    Case is freshly created) and from GET /api/risk (where the request
    only carries district + crop).

    When farm_id + farm_lon + farm_lat are all provided, a geospatial
    proximity signal is computed from other farm-coordinate cases within
    GEO_NEAR_RADIUS_KM. If any are missing, the geo factor contributes 0.
    """
    now = as_of or get_demo_clock()
    factors: list[RiskFactor] = []

    # 1) Recent-cases signal (district-level, no coordinates)
    recent = await _count_recent_cases(session, district, crop, disease, now)
    sig, note = recent_cases_signal(recent)
    factors.append(RiskFactor(
        name="Recent cases in district (last 14d)",
        weight=W_CASES,
        raw_signal=recent,
        contribution=sig,
        note=note,
    ))

    # 2) Outbreak signal
    outbreak = await _latest_outbreak(session, district, crop, disease)
    risk_level = outbreak.risk_level if outbreak is not None else None
    sig, note = outbreak_signal(risk_level)
    factors.append(RiskFactor(
        name="Seeded district outbreak report",
        weight=W_OUTBREAK,
        raw_signal=OUTBREAK_SIGNAL.get((risk_level or "").lower(), 0.0),
        contribution=sig,
        note=note,
    ))

    # 3) Weather signal — only use columns the project actually populates.
    weather = await _latest_weather(session, district)
    sm = weather.soil_moisture_percent if weather else None
    et = weather.evapotranspiration_mm if weather else None
    t = weather.temperature_c if weather else None
    h = weather.humidity_percent if weather else None
    sig, note = weather_signal(sm, et, t, h)
    factors.append(RiskFactor(
        name="Environmental conditions",
        weight=W_WEATHER,
        raw_signal=sig,
        contribution=sig,
        note=note,
    ))

    # 4) Severity signal
    sig, note = severity_signal(severity)
    factors.append(RiskFactor(
        name="Predicted severity",
        weight=W_SEVERITY,
        raw_signal=SEVERITY_SIGNAL.get((severity or "").lower(), 0.0),
        contribution=sig,
        note=note,
    ))

    # 5) Confidence signal
    sig, note = confidence_signal(confidence)
    factors.append(RiskFactor(
        name="Model confidence (uncertainty)",
        weight=W_CONFIDENCE,
        raw_signal=(1.0 - float(confidence)) if confidence is not None else 1.0,
        contribution=sig,
        note=note,
    ))

    # 6) Geospatial proximity signal — only when farm coordinates are available.
    if farm_id and farm_lon is not None and farm_lat is not None:
        nearby = await _count_nearby_cases(
            session,
            farm_id=farm_id,
            farm_lon=farm_lon,
            farm_lat=farm_lat,
            crop=crop,
            disease=disease,
            as_of=now,
        )
        sig, note = geo_proximity_signal(nearby)
    else:
        sig, note = 0.0, "No farm coordinates available for geospatial proximity"
    factors.append(RiskFactor(
        name="Nearby farm-coordinate cases (0-10 km)",
        weight=W_GEO,
        raw_signal=float(sig),   # raw_signal mirrors contribution for geo
        contribution=sig,
        note=note,
    ))

    total = sum(f.contribution for f in factors)
    total = clip_score(total)
    level = bucketize(total)

    forecast = RiskForecast(
        risk_score=total,
        risk_level=level,
        contributing_factors=factors,
        recommended_action=recommend_action(level, crop, disease),
        explanation="",
        computed_at=now,
        demo_time_used=now,
    )
    forecast.explanation = explain(forecast)
    return forecast


async def compute_forecast_for_case(
    session: AsyncSession,
    case: Case,
) -> RiskForecast:
    """Compute a RiskForecast for an existing Case (uses its farm district
    and farm coordinates for the geospatial proximity signal).

    District lives on the Farmer (not the Farm), so we join via Farm.farmer_id.
    Farm coordinates come from Farm.location_point (WKT POINT text).
    """
    from app.models import Farmer
    stmt = (
        select(Farmer.district)
        .join(Farm, Farm.farmer_id == Farmer.id)
        .where(Farm.id == case.farm_id)
    )
    district = (await session.execute(stmt)).scalar_one_or_none() or "Unknown"

    farm_loc = await _farm_location(session, str(case.farm_id))
    farm_lon = farm_loc[0] if farm_loc else None
    farm_lat = farm_loc[1] if farm_loc else None

    return await compute_forecast(
        session,
        district=district,
        crop=case.predicted_crop,
        disease=case.predicted_disease,
        severity=case.severity,
        confidence=case.confidence,
        as_of=case.detected_at,
        farm_id=str(case.farm_id),
        farm_lon=farm_lon,
        farm_lat=farm_lat,
    )
