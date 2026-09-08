"""KrishiKavach FastAPI Application — SIH26131.

Main entry point. Defines all API routes for the first vertical slice:
- Voice-first farmer flow: photo → prediction → case → feedback → follow-up
- Demo time simulation for SIH demonstration
"""
from __future__ import annotations

import os
import shutil
import sys
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Depends, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.database import get_async_session, init_db, close_db
from app.models import (
    Case, CaseFeedback, DiseaseReport, Escalation, Expert, Farmer, Farm,
    WeatherContext,
)
from app.schemas import (
    CaseCreateResponse,
    CaseListResponse,
    CaseResponse,
    DemoAdvanceRequest,
    DemoTimeResponse,
    DiseaseBreakdownEntry,
    DiseaseReportResponse,
    DistrictRiskProfile,
    DistrictSummary,
    EscalationCreate,
    EscalationListResponse,
    EscalationResponse,
    EscalationVerdictRequest,
    FeedbackCreate,
    FeedbackResponse,
    HealthResponse,
    InterventionStats,
    OutbreakSummary,
    PredictionResult,
    RiskFactorResponse,
    RiskForecastResponse,
    SpeakRequest,
    TranscribeResponse,
    UploadResponse,
    VoiceConfigResponse,
    WeatherSummary,
)
from app.services import omniroute
from app.services import elevenlabs_tts
from app.services import elevenlabs_stt
from app.services.case_service import (
    advance_demo_days,
    create_case_from_prediction,
    get_demo_clock,
    get_demo_date,
    get_demo_farm,
    get_farmer_cases,
    get_or_create_demo_farmer,
    record_feedback,
    reset_demo_clock,
    set_demo_clock,
)
from app.services.prediction import (
    DemoPredictionService,
    Recommendation,
    Severity,
    get_prediction_service,
    predict_and_recommend,
)
from app.services.risk_forecast import compute_forecast, parse_wkt_point
from app.services.officer_service import (
    get_all_district_summaries,
    get_district_summary,
)
from app.services.escalation_service import (
    EscalationError,
    VALID_VERDICTS,
    create_escalation,
    escalation_status_for_case,
    get_active_escalation,
    list_escalations,
    submit_verdict,
)
from app.services.voice import get_voice_controller


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and clean up database connections."""
    try:
        await init_db()
    except Exception as e:
        # If DB isn't available, log and continue
        print(f"DB init warning: {e}")
    yield
    await close_db()


app = FastAPI(
    title="KrishiKavach API",
    description="Voice-first AI crop-health and early-warning system for Maharashtra farmers (SIH26131)",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health(session: AsyncSession = Depends(get_async_session)) -> HealthResponse:
    """Health check endpoint."""
    db_status = "connected"
    try:
        await session.execute(select(func.count()).select_from(Farmer))
    except Exception as e:
        db_status = f"error: {str(e)[:100]}"

    return HealthResponse(
        status="ok",
        database=db_status,
        prediction_mode=settings.PREDICTION_MODE,
        demo_time_enabled=settings.DEMO_TIME_ENABLED,
        current_demo_date=get_demo_date() if settings.DEMO_TIME_ENABLED else None,
    )


# ---------------------------------------------------------------------------
# Photo upload + Prediction endpoint
# ---------------------------------------------------------------------------

@app.post("/api/upload", response_model=UploadResponse, tags=["farmer"])
async def upload_image(file: UploadFile = File(...)) -> UploadResponse:
    """Receive a photo from the farmer and store it locally.

    Returns the file path so the frontend can display the image.
    """
    # Validate file type
    allowed_types = {"image/jpeg", "image/png", "image/jpg", "image/webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}. Allowed: {allowed_types}",
        )

    # Create upload directory
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Generate filename
    ext = file.filename.split(".")[-1] if file.filename and "." in file.filename else "jpg"
    filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}.{ext}"
    file_path = upload_dir / filename

    # Save file
    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max: {settings.MAX_UPLOAD_BYTES} bytes",
        )

    with open(file_path, "wb") as f:
        f.write(content)

    return UploadResponse(
        image_path=str(file_path),
        image_url=f"/uploads/{filename}",
        size_bytes=len(content),
    )


@app.post("/api/predict", response_model=CaseCreateResponse, tags=["farmer"])
async def predict_and_create_case(
    file: UploadFile = File(...),
    district: Optional[str] = Form(None),
    crop_type: Optional[str] = Form(None),
    crop_stage: Optional[str] = Form(None),
    farmer_language: str = Form("marathi"),
    session: AsyncSession = Depends(get_async_session),
) -> CaseCreateResponse:
    """Main farmer endpoint: receive image → run prediction → create case.

    This is the core of the first vertical slice.
    """
    # Read image
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty image file")

    # Get or create demo farmer
    farmer = await get_or_create_demo_farmer(
        session, name="Demo Farmer", district=district or "Pune", village="Pirangut"
    )
    farm = await get_demo_farm(session, farmer.id)
    if farm is None:
        raise HTTPException(status_code=500, detail="Demo farm not initialized")

    # Save image
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    ext = file.filename.split(".")[-1] if file.filename and "." in file.filename else "jpg"
    filename = f"case-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}.{ext}"
    file_path = upload_dir / filename
    with open(file_path, "wb") as f:
        f.write(content)

    # Build context for prediction
    context = {
        "district": district or farmer.district,
        "crop_type": crop_type or farm.primary_crop,
        "crop_stage": crop_stage,
        "farmer_language": farmer_language,
    }

    # Run prediction
    prediction, recommendation = await predict_and_recommend(
        image_bytes=content,
        context=context,
        mode=settings.PREDICTION_MODE,
    )

    # Create case
    case = await create_case_from_prediction(
        session=session,
        farm_id=farm.id,
        farmer_id=farmer.id,
        prediction=prediction,
        recommendation=recommendation,
        image_path=str(file_path),
        image_thumbnail_path=None,
        district=district,
    )

    await session.commit()
    await session.refresh(case)

    # Build response
    prediction_dict = prediction.to_dict()
    prediction_dict["recommendation_text"] = recommendation.recommendation_text
    prediction_dict["steps"] = recommendation.steps
    prediction_dict["warning"] = recommendation.warning
    prediction_dict["escalate"] = recommendation.escalate
    prediction_dict["follow_up_days"] = recommendation.follow_up_days

    # Risk forecast (lightweight, deterministic, demo-time-aware, geo-aware)
    farm_loc = parse_wkt_point(farm.location_point) if farm.location_point else None
    farm_lon = farm_loc[0] if farm_loc else None
    farm_lat = farm_loc[1] if farm_loc else None
    forecast = await compute_forecast(
        session,
        district=district or farmer.district or "Unknown",
        crop=prediction.crop,
        disease=prediction.disease,
        severity=prediction.severity.value,
        confidence=prediction.confidence,
        as_of=case.detected_at,
        farm_id=str(farm.id),
        farm_lon=farm_lon,
        farm_lat=farm_lat,
    )
    forecast_response = RiskForecastResponse(
        risk_score=forecast.risk_score,
        risk_level=forecast.risk_level,
        contributing_factors=[
            RiskFactorResponse(
                name=f.name,
                weight=f.weight,
                raw_signal=f.raw_signal,
                contribution=f.contribution,
                note=f.note,
            )
            for f in forecast.contributing_factors
        ],
        recommended_action=forecast.recommended_action,
        explanation=forecast.explanation,
        computed_at=forecast.computed_at,
        demo_time_used=forecast.demo_time_used,
    )

    return CaseCreateResponse(
        case_id=case.id,
        prediction=PredictionResult(**prediction_dict),
        farmer_id=farmer.id,
        farm_id=farm.id,
        detected_at=case.detected_at,
        recommendation_given_at=case.recommendation_given_at,
        next_follow_up_at=case.next_follow_up_at,
        case_status=case.case_status,
        is_demo_prediction=prediction.is_demo,
        risk_forecast=forecast_response,
    )


# ---------------------------------------------------------------------------
# Case endpoints
# ---------------------------------------------------------------------------

@app.get("/api/cases/due-for-follow-up", response_model=CaseListResponse, tags=["farmer"])
async def list_cases_due_for_follow_up(
    farmer_id: Optional[UUID] = None,
    session: AsyncSession = Depends(get_async_session),
) -> CaseListResponse:
    """List active cases where next_follow_up_at <= today.

    When farmer_id is provided, returns only that farmer's cases.
    Without farmer_id (demo mode), returns all due cases so the farmer
    can identify their own by disease/crop.
    """
    from app.services.case_service import get_cases_due_for_follow_up
    today = get_demo_date()
    cases = await get_cases_due_for_follow_up(session, as_of_date=today, farmer_id=farmer_id)
    return CaseListResponse(
        cases=[CaseResponse.model_validate(c) for c in cases],
        total=len(cases),
    )


@app.get("/api/cases", response_model=CaseListResponse, tags=["farmer"])
async def list_cases(
    farmer_id: Optional[UUID] = None,
    status: Optional[str] = None,
    session: AsyncSession = Depends(get_async_session),
) -> CaseListResponse:
    """List cases. Filter by farmer_id and/or status."""
    stmt = select(Case)
    if farmer_id:
        stmt = stmt.where(Case.farmer_id == farmer_id)
    if status:
        stmt = stmt.where(Case.case_status == status)
    stmt = stmt.order_by(Case.detected_at.desc())

    result = await session.execute(stmt)
    cases = list(result.scalars().all())
    return CaseListResponse(
        cases=[CaseResponse.model_validate(c) for c in cases],
        total=len(cases),
    )


@app.get("/api/cases/{case_id}", response_model=CaseResponse, tags=["farmer"])
async def get_case(
    case_id: UUID,
    session: AsyncSession = Depends(get_async_session),
) -> CaseResponse:
    """Get a specific case by ID."""
    result = await session.execute(select(Case).where(Case.id == case_id))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    response = CaseResponse.model_validate(case)
    status, latest_verdict = await escalation_status_for_case(session, case.id)
    response.escalation_status = status
    response.latest_verdict = latest_verdict
    return response


# ---------------------------------------------------------------------------
# Feedback endpoint
# ---------------------------------------------------------------------------

@app.post(
    "/api/cases/{case_id}/feedback",
    response_model=FeedbackResponse,
    tags=["farmer"],
)
async def submit_feedback(
    case_id: UUID,
    payload: FeedbackCreate,
    session: AsyncSession = Depends(get_async_session),
) -> FeedbackResponse:
    """Record farmer feedback for a case.

    Per Correction #2 — uses REAL timestamps (not "7 seconds = 7 days").
    Demo time is controlled separately via /api/demo endpoints.
    """
    # Verify case exists
    result = await session.execute(select(Case).where(Case.id == case_id))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    feedback = await record_feedback(
        session=session,
        case_id=case_id,
        farmer_id=case.farmer_id,
        attempted_intervention=payload.attempted_intervention,
        crop_improved=payload.crop_improved,
        farmer_notes=payload.farmer_notes,
    )

    await session.commit()
    return FeedbackResponse.model_validate(feedback)


# ---------------------------------------------------------------------------
# Expert escalation endpoints (SIH26131 expert review workflow)
# ---------------------------------------------------------------------------

async def _escalation_to_response(
    session: AsyncSession,
    esc: Escalation,
    *,
    district: Optional[str] = None,
    predicted_disease: Optional[str] = None,
    predicted_crop: Optional[str] = None,
) -> EscalationResponse:
    """Build an EscalationResponse from an Escalation + optional joined
    context. Only public context fields are added — no farmer PII.
    """
    expert_name: Optional[str] = None
    if esc.expert_id is not None:
        expert = (await session.execute(
            select(Expert).where(Expert.id == esc.expert_id)
        )).scalar_one_or_none()
        if expert is not None:
            expert_name = expert.name

    severity: Optional[str] = None
    uncertainty_flag = False
    if predicted_disease is None or predicted_crop is None or severity is None:
        case = (await session.execute(
            select(Case).where(Case.id == esc.case_id)
        )).scalar_one_or_none()
        if case is not None:
            predicted_disease = predicted_disease or case.predicted_disease
            predicted_crop = predicted_crop or case.predicted_crop
            severity = severity or case.severity
            uncertainty_flag = case.uncertainty_flag

    return EscalationResponse(
        id=esc.id,
        case_id=esc.case_id,
        expert_id=esc.expert_id,
        expert_name=expert_name,
        escalated_at=esc.escalated_at,
        resolved_at=esc.resolved_at,
        expert_notes=esc.expert_notes,
        expert_verdict=esc.expert_verdict,
        predicted_disease=predicted_disease,
        predicted_crop=predicted_crop,
        severity=severity,
        district=district,
        uncertainty_flag=uncertainty_flag,
    )


@app.post(
    "/api/cases/{case_id}/escalate",
    response_model=EscalationResponse,
    status_code=201,
    tags=["escalation"],
)
async def escalate_case(
    case_id: UUID,
    payload: Optional[EscalationCreate] = None,
    session: AsyncSession = Depends(get_async_session),
) -> EscalationResponse:
    """Escalate a case for expert review.

    Creates an Escalation and (if the case was active/resolved) marks the
    case as `escalated`. Returns 409 if an active escalation already exists
    for the case, 404 if the case does not exist.

    The existing ML model and prediction pipeline are NOT touched. Use the
    `escalate` flag on a prediction (`PredictionResult.escalate`) — already
    surfaced in the farmer UI — to decide when to call this endpoint.
    """
    body = payload or EscalationCreate()
    try:
        esc = await create_escalation(
            session,
            case_id=case_id,
            expert_id=body.expert_id,
            reason=body.reason,
        )
    except EscalationError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e)) from e
        raise HTTPException(status_code=409, detail=str(e)) from e
    await session.commit()
    await session.refresh(esc)
    response = await _escalation_to_response(session, esc)
    return response


@app.post(
    "/api/escalations/{escalation_id}/verdict",
    response_model=EscalationResponse,
    tags=["escalation"],
)
async def submit_escalation_verdict(
    escalation_id: UUID,
    payload: EscalationVerdictRequest,
    session: AsyncSession = Depends(get_async_session),
) -> EscalationResponse:
    """Submit an expert verdict on an escalation.

    Verdict values: `confirmed` | `rejected` | `needs_more_evidence`.
    Marks the escalation resolved and updates the underlying case status:
      - confirmed    → case stays/returns to `active`
      - rejected     → case is `closed`
      - needs_more_evidence → case returns to `active` (a new escalation
                              can be raised if the farmer reports back)
    Returns 400 for invalid verdicts, 404 for unknown escalation,
    409 if the escalation is already resolved.
    """
    try:
        esc = await submit_verdict(
            session,
            escalation_id=escalation_id,
            verdict=payload.verdict,
            expert_notes=payload.expert_notes,
            expert_id=payload.expert_id,
        )
    except EscalationError as e:
        msg = str(e).lower()
        if "invalid verdict" in msg:
            raise HTTPException(
                status_code=400,
                detail=f"{str(e)} (valid: {', '.join(VALID_VERDICTS)})",
            ) from e
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=str(e)) from e
        raise HTTPException(status_code=409, detail=str(e)) from e
    await session.commit()
    await session.refresh(esc)
    response = await _escalation_to_response(session, esc)
    return response


@app.get(
    "/api/escalations",
    response_model=EscalationListResponse,
    tags=["escalation"],
)
async def list_escalations_endpoint(
    status: str = "all",
    session: AsyncSession = Depends(get_async_session),
) -> EscalationListResponse:
    """List escalations for the officer/expert dashboard.

    Query params:
      - `status`: `active` (default unresolved), `resolved`, or `all`.

    Farmer PII (names, phones, farmer IDs) is NEVER included. Each row
    carries only public context: case_id, district, predicted disease/crop,
    severity, uncertainty flag, escalation timestamps, and verdict (when
    recorded).
    """
    try:
        rows = await list_escalations(session, status=status)
    except EscalationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    items: list[EscalationResponse] = []
    for esc, district, predicted_disease, predicted_crop in rows:
        items.append(
            await _escalation_to_response(
                session,
                esc,
                district=district,
                predicted_disease=predicted_disease,
                predicted_crop=predicted_crop,
            )
        )
    return EscalationListResponse(escalations=items, total=len(items))


@app.get(
    "/api/escalations/{escalation_id}",
    response_model=EscalationResponse,
    tags=["escalation"],
)
async def get_escalation(
    escalation_id: UUID,
    session: AsyncSession = Depends(get_async_session),
) -> EscalationResponse:
    """Fetch a single escalation by ID."""
    result = await session.execute(
        select(Escalation).where(Escalation.id == escalation_id)
    )
    esc = result.scalar_one_or_none()
    if esc is None:
        raise HTTPException(status_code=404, detail="Escalation not found")
    # Resolve public context fields
    case = (await session.execute(
        select(Case).where(Case.id == esc.case_id)
    )).scalar_one_or_none()
    district = None
    if case is not None:
        farmer_district = (
            await session.execute(
                select(Farmer.district)
                .join(Farm, Farm.farmer_id == Farmer.id)
                .where(Farm.id == case.farm_id)
            )
        ).scalar_one_or_none()
        district = farmer_district
    return await _escalation_to_response(
        session,
        esc,
        district=district,
        predicted_disease=case.predicted_disease if case else None,
        predicted_crop=case.predicted_crop if case else None,
    )


# ---------------------------------------------------------------------------
# Demo time simulation (clearly isolated)
# ---------------------------------------------------------------------------

@app.post("/api/demo/advance-time", response_model=DemoTimeResponse, tags=["demo"])
async def advance_demo_time(
    payload: DemoAdvanceRequest,
) -> DemoTimeResponse:
    """Advance the demo clock by `payload.days` days.

    This is CLEARLY ISOLATED demo functionality for SIH demonstration only.
    In production, follow-up time is calculated from real timestamps.
    """
    if not settings.DEMO_TIME_ENABLED:
        raise HTTPException(status_code=403, detail="Demo time is disabled in production")

    new_date = advance_demo_days(payload.days)
    return DemoTimeResponse(
        current_date=new_date,
        message=f"Demo time advanced by {payload.days} day(s). Current demo date: {new_date}",
    )


@app.post("/api/demo/set-time", response_model=DemoTimeResponse, tags=["demo"])
async def set_demo_time(date_str: str) -> DemoTimeResponse:
    """Set the demo clock to a specific date (YYYY-MM-DD)."""
    if not settings.DEMO_TIME_ENABLED:
        raise HTTPException(status_code=403, detail="Demo time is disabled in production")

    try:
        target = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    set_demo_clock(target)
    return DemoTimeResponse(
        current_date=target.date(),
        message=f"Demo time set to {target.date()}",
    )


@app.post("/api/demo/reset-time", response_model=DemoTimeResponse, tags=["demo"])
async def reset_demo_time_endpoint() -> DemoTimeResponse:
    """Reset demo clock to real time."""
    if not settings.DEMO_TIME_ENABLED:
        raise HTTPException(status_code=403, detail="Demo time is disabled in production")

    reset_demo_clock()
    return DemoTimeResponse(
        current_date=get_demo_date(),
        message="Demo time reset to real time",
    )


@app.get("/api/demo/current-time", response_model=DemoTimeResponse, tags=["demo"])
async def get_current_demo_time() -> DemoTimeResponse:
    """Return the current demo time."""
    return DemoTimeResponse(
        current_date=get_demo_date(),
        message=f"Current demo date: {get_demo_date()}",
    )


# ---------------------------------------------------------------------------
# Outbreak / disease report endpoints
# ---------------------------------------------------------------------------

@app.get("/api/outbreaks", response_model=list[DiseaseReportResponse], tags=["outbreak"])
async def list_disease_reports(
    district: Optional[str] = None,
    crop_type: Optional[str] = None,
    session: AsyncSession = Depends(get_async_session),
) -> list[DiseaseReportResponse]:
    """List disease outbreak reports. Filter by district or crop."""
    stmt = select(DiseaseReport)
    if district:
        stmt = stmt.where(DiseaseReport.district == district)
    if crop_type:
        stmt = stmt.where(DiseaseReport.crop_type == crop_type)
    stmt = stmt.order_by(DiseaseReport.valid_from.desc())
    result = await session.execute(stmt)
    reports = list(result.scalars().all())
    return [DiseaseReportResponse.model_validate(r) for r in reports]


# ---------------------------------------------------------------------------
# Risk forecast endpoints
# ---------------------------------------------------------------------------

@app.get(
    "/api/risk/{district}/{crop}",
    response_model=RiskForecastResponse,
    tags=["risk"],
)
async def get_risk_forecast(
    district: str,
    crop: str,
    disease: Optional[str] = None,
    session: AsyncSession = Depends(get_async_session),
) -> RiskForecastResponse:
    """Compute a lightweight explainable risk forecast for a district/crop.

    Uses ONLY data already in the project:
    - Live cases in the district (last 14 days)
    - Seeded disease_reports aggregates
    - Seeded weather_contexts (soil moisture, evapotranspiration;
      temperature/humidity contribute 0 if not yet populated)
    - Predicted severity (if provided via disease) and model confidence (fixed 0.5
      when not provided, as this endpoint is read-only without a prediction).

    This is NOT a trained model. It is a deterministic blend of trusted signals.
    """
    forecast = await compute_forecast(
        session,
        district=district,
        crop=crop,
        disease=disease,
        severity=None,
        confidence=0.5,
    )
    return RiskForecastResponse(
        risk_score=forecast.risk_score,
        risk_level=forecast.risk_level,
        contributing_factors=[
            RiskFactorResponse(
                name=f.name,
                weight=f.weight,
                raw_signal=f.raw_signal,
                contribution=f.contribution,
                note=f.note,
            )
            for f in forecast.contributing_factors
        ],
        recommended_action=forecast.recommended_action,
        explanation=forecast.explanation,
        computed_at=forecast.computed_at,
        demo_time_used=forecast.demo_time_used,
    )


# ---------------------------------------------------------------------------
# Agriculture Officer dashboard endpoints
# ---------------------------------------------------------------------------

@app.get(
    "/api/officer/district-summary",
    response_model=list[DistrictSummary],
    tags=["officer"],
)
async def get_officer_district_summary(
    district: Optional[str] = None,
    include_factors: bool = False,
    session: AsyncSession = Depends(get_async_session),
) -> list[DistrictSummary]:
    """District-level summary for the Agriculture Officer dashboard.

    Returns aggregated data from existing tables — no new DB tables, no farmer PII.

    Per-district data:
    - Case counts: total, active, resolved, escalated, follow-up due
    - Severity breakdown: low / medium / high
    - Disease breakdown: per (crop, disease) with case + farm counts
    - Intervention stats: from CaseFeedback (attempted treatment, improved, etc.)
    - Active outbreaks: from seeded DiseaseReport (no farmer PII)
    - Weather context: latest from WeatherContext
    - Risk profile: via existing compute_forecast engine
    - Centroid: hardcoded WGS-84 coordinates for Maharashtra district HQ

    Query params:
    - `district`: if provided, returns a single-item list for that district.
      If omitted, returns summaries for all Maharashtra districts.
    - `include_factors`: if true, includes the per-factor risk breakdown
      (weights, contributions) in the response. Default false.

    Privacy: farmer names, phone numbers, and farmer IDs are NEVER included.
    Suitable as the data source for a future Maharashtra heatmap.
    """
    if district:
        summary = await get_district_summary(
            session, district, include_factors=include_factors,
        )
        return [_district_summary_to_schema(summary)]
    summaries = await get_all_district_summaries(
        session, include_factors=include_factors,
    )
    return [_district_summary_to_schema(s) for s in summaries]


def _district_summary_to_schema(s) -> DistrictSummary:
    """Convert the dataclass DistrictSummary to the Pydantic schema."""
    return DistrictSummary(
        district=s.district,
        state=s.state,
        centroid_lon=s.centroid_lon,
        centroid_lat=s.centroid_lat,
        total_cases=s.total_cases,
        active_cases=s.active_cases,
        resolved_cases=s.resolved_cases,
        escalated_cases=s.escalated_cases,
        follow_up_due=s.follow_up_due,
        severity_low=s.severity_low,
        severity_medium=s.severity_medium,
        severity_high=s.severity_high,
        disease_breakdown=[
            DiseaseBreakdownEntry(
                crop=e.crop,
                disease=e.disease,
                case_count=e.case_count,
                farm_count=e.farm_count,
                severity=e.severity,
                risk_level=e.risk_level,
                last_detected=e.last_detected,
            )
            for e in s.disease_breakdown
        ],
        interventions=(
            InterventionStats(
                total_feedbacks=s.interventions.total_feedbacks,
                attempted_treatment=s.interventions.attempted_treatment,
                crop_improved=s.interventions.crop_improved,
                crop_not_improved=s.interventions.crop_not_improved,
                no_feedback_yet=s.interventions.no_feedback_yet,
            )
            if s.interventions
            else None
        ),
        active_outbreaks=[
            OutbreakSummary(
                crop_type=o.crop_type,
                disease_type=o.disease_type,
                risk_level=o.risk_level,
                affected_farms=o.affected_farms,
                total_cases_reported=o.total_cases_reported,
            )
            for o in s.active_outbreaks
        ],
        weather=(
            WeatherSummary(
                soil_moisture_percent=s.weather.soil_moisture_percent,
                evapotranspiration_mm=s.weather.evapotranspiration_mm,
                temperature_c=s.weather.temperature_c,
                humidity_percent=s.weather.humidity_percent,
                recorded_at=s.weather.recorded_at,
            )
            if s.weather
            else None
        ),
        risk_profile=(
            DistrictRiskProfile(
                risk_score=s.risk_profile.risk_score,
                risk_level=s.risk_profile.risk_level,
                recommended_action=s.risk_profile.recommended_action,
                explanation=s.risk_profile.explanation,
                contributing_factors=s.risk_profile.contributing_factors,
            )
            if s.risk_profile
            else None
        ),
        computed_at=s.computed_at,
    )


# ---------------------------------------------------------------------------
# Voice prompt endpoint (for the frontend VoiceInteractionController)
# ---------------------------------------------------------------------------

@app.get("/api/voice/prompt/{prompt_key}", tags=["voice"])
async def get_voice_prompt(prompt_key: str, language: str = "marathi") -> dict:
    """Return a localized voice prompt for the given key."""
    voice = get_voice_controller()
    voice.set_language(language)
    try:
        text = voice.get_prompt(prompt_key)
        listening_prompt = voice.get_listening_prompt()
        return {
            "prompt": text,
            "listening_prompt": listening_prompt,
            "language": language,
        }
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown prompt: {prompt_key}")


@app.post("/api/voice/parse-intent", tags=["voice"])
async def parse_voice_intent(payload: dict) -> dict:
    """Parse a farmer's speech transcript into a structured intent."""
    voice = get_voice_controller()
    transcript = payload.get("transcript", "")
    language = payload.get("language", "marathi")
    voice.set_language(language)
    intent = voice.parse_intent(transcript)
    return {
        "raw_text": intent.raw_text,
        "intent": intent.intent,
        "confidence": intent.confidence,
        "language": intent.language,
    }


# ---------------------------------------------------------------------------
# Voice provider endpoints (OmniRoute STT/TTS)
# ---------------------------------------------------------------------------
# These endpoints are the only place that talks to the upstream voice API.
# The frontend never sees the API key.
# ---------------------------------------------------------------------------

@app.get("/api/voice/config", response_model=VoiceConfigResponse, tags=["voice"])
async def get_voice_config() -> VoiceConfigResponse:
    """Return voice configuration for the frontend.

    Includes the active STT/TTS provider, default language, and configured
    model + voice — but NEVER the upstream API key.
    """
    stt_provider = settings.VOICE_STT_PROVIDER
    tts_provider = settings.VOICE_TTS_PROVIDER
    return VoiceConfigResponse(
        provider=stt_provider if stt_provider == tts_provider else "mixed",
        stt_provider=stt_provider,
        tts_provider=tts_provider,
        default_language=settings.DEFAULT_VOICE_LANGUAGE,
        stt_model=(
            settings.OMNIROUTE_STT_MODEL
            if stt_provider == "omniroute"
            else settings.ELEVENLABS_STT_MODEL
            if stt_provider == "elevenlabs"
            else None
        ),
        tts_model=(
            settings.OMNIROUTE_TTS_MODEL
            if tts_provider == "omniroute"
            else settings.ELEVENLABS_MODEL_ID
            if tts_provider == "elevenlabs"
            else None
        ),
        tts_voice=(
            settings.OMNIROUTE_TTS_VOICE
            if tts_provider == "omniroute"
            else None
        ),
        elevenlabs_stt_model=(
            settings.ELEVENLABS_STT_MODEL
            if stt_provider == "elevenlabs"
            else None
        ),
        elevenlabs_voice_id=(
            settings.ELEVENLABS_VOICE_ID
            if tts_provider == "elevenlabs"
            else None
        ),
        elevenlabs_model_id=(
            settings.ELEVENLABS_MODEL_ID
            if tts_provider == "elevenlabs"
            else None
        ),
        browser_fallback_supported=True,
    )


@app.post("/api/voice/transcribe", response_model=TranscribeResponse, tags=["voice"])
async def transcribe(
    file: UploadFile = File(...),
    language: str = Form("hi-IN"),
) -> TranscribeResponse:
    """Receive recorded audio and return a transcript using ElevenLabs STT.

    The browser records audio, POSTs the audio file here, and the backend
    forwards it to ElevenLabs. If ElevenLabs is unavailable, the response
    status signals the client to fall back to browser STT.
    """
    stt_provider = settings.VOICE_STT_PROVIDER

    if stt_provider == "elevenlabs":
        if not elevenlabs_stt.is_configured():
            raise HTTPException(
                status_code=503,
                detail=(
                    "ElevenLabs STT is not configured on the backend. "
                    "Set ELEVENLABS_API_KEY in the backend environment."
                ),
            )

        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Empty audio payload")

        # ~10MB cap to match upload limit
        if len(content) > settings.MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Audio too large. Max: {settings.MAX_UPLOAD_BYTES} bytes",
            )

        filename = file.filename or "recording.webm"
        content_type = file.content_type or "audio/webm"

        try:
            result = await elevenlabs_stt.transcribe_audio(
                audio_bytes=content,
                filename=filename,
                content_type=content_type,
                language=language,
            )
        except elevenlabs_stt.ElevenLabsSTTError as e:
            raise HTTPException(status_code=502, detail=f"STT upstream error: {e}") from e
        except elevenlabs_stt.ElevenLabsSTTUnavailable as e:
            raise HTTPException(status_code=503, detail=str(e)) from e

        return TranscribeResponse(
            text=result["text"],
            language=result["language"],
            provider=result["provider"],
            confidence=result.get("confidence"),
        )

    if stt_provider == "omniroute":
        # Legacy path — kept for backward compatibility
        if not omniroute.is_configured():
            raise HTTPException(
                status_code=503,
                detail=(
                    "OmniRoute is not configured on the backend. "
                    "Set OMNIROUTE_API_KEY in the backend environment."
                ),
            )

        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Empty audio payload")

        if len(content) > settings.MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Audio too large. Max: {settings.MAX_UPLOAD_BYTES} bytes",
            )

        filename = file.filename or "recording.webm"
        content_type = file.content_type or "audio/webm"

        try:
            result = await omniroute.transcribe_audio(
                audio_bytes=content,
                filename=filename,
                content_type=content_type,
                language=language,
            )
        except omniroute.OmniRouteError as e:
            raise HTTPException(status_code=502, detail=f"STT upstream error: {e}") from e
        except omniroute.OmniRouteUnavailable as e:
            raise HTTPException(status_code=503, detail=str(e)) from e

        return TranscribeResponse(
            text=result["text"],
            language=result["language"],
            provider=result["provider"],
            confidence=result.get("confidence"),
        )

    # stt_provider == "browser" or unknown — signal frontend to use Web Speech API.
    raise HTTPException(
        status_code=503,
        detail="Backend STT is disabled. Use browser STT.",
    )


@app.post("/api/voice/speak", tags=["voice"])
async def speak(payload: SpeakRequest):
    """Synthesize speech and return the audio bytes.

    Routes to the configured TTS provider:
      - elevenlabs → ElevenLabs (voice: Rian, model: eleven_multilingual_v2)
      - omniroute  → OmniRoute-compatible endpoint
    Returns the raw audio body (audio/mpeg). The frontend plays it
    directly with the HTMLAudioElement. If the TTS provider is unavailable,
    the response status signals the client to fall back to browser TTS.
    """
    tts_provider = settings.VOICE_TTS_PROVIDER

    if tts_provider == "elevenlabs":
        if not elevenlabs_tts.is_configured():
            raise HTTPException(
                status_code=503,
                detail=(
                    "ElevenLabs TTS is not configured on the backend. "
                    "Set ELEVENLABS_API_KEY in the backend environment."
                ),
            )
        try:
            audio = await elevenlabs_tts.synthesize_speech(
                text=payload.text,
                language=payload.language,
            )
        except elevenlabs_tts.ElevenLabsError as e:
            raise HTTPException(status_code=502, detail=f"TTS upstream error: {e}") from e
        except elevenlabs_tts.ElevenLabsUnavailable as e:
            raise HTTPException(status_code=503, detail=str(e)) from e
        return Response(content=audio, media_type="audio/mpeg")

    if tts_provider == "omniroute":
        if not omniroute.is_configured():
            raise HTTPException(
                status_code=503,
                detail=(
                    "OmniRoute TTS is not configured on the backend. "
                    "Set OMNIROUTE_API_KEY in the backend environment."
                ),
            )
        try:
            audio = await omniroute.synthesize_speech(
                text=payload.text,
                language=payload.language,
                voice=payload.voice,
            )
        except omniroute.OmniRouteError as e:
            raise HTTPException(status_code=502, detail=f"TTS upstream error: {e}") from e
        except omniroute.OmniRouteUnavailable as e:
            raise HTTPException(status_code=503, detail=str(e)) from e
        return Response(content=audio, media_type="audio/mpeg")

    # tts_provider == "browser" or unknown — signal frontend to use Web Speech API.
    raise HTTPException(
        status_code=503,
        detail="Backend TTS is disabled. Use browser TTS.",
    )


# ---------------------------------------------------------------------------
# Root endpoint
# ---------------------------------------------------------------------------

@app.get("/", tags=["health"])
async def root() -> dict:
    """API root — basic info."""
    return {
        "name": "KrishiKavach API",
        "version": "0.1.0",
        "sih_problem_id": "SIH26131",
        "prediction_mode": settings.PREDICTION_MODE,
        "demo_time_enabled": settings.DEMO_TIME_ENABLED,
        "endpoints": {
            "health": "/health",
            "predict": "/api/predict (POST multipart with file)",
            "upload": "/api/upload (POST multipart with file)",
            "case": "/api/cases/{case_id}",
            "cases": "/api/cases",
            "cases_due": "/api/cases/due-for-follow-up",
            "feedback": "/api/cases/{case_id}/feedback",
            "demo_advance": "/api/demo/advance-time",
            "demo_set": "/api/demo/set-time?date_str=YYYY-MM-DD",
            "demo_reset": "/api/demo/reset-time",
            "demo_current": "/api/demo/current-time",
            "outbreaks": "/api/outbreaks",
            "voice_prompt": "/api/voice/prompt/{key}?language=marathi",
            "voice_intent": "/api/voice/parse-intent",
            "voice_config": "/api/voice/config",
            "voice_transcribe": "/api/voice/transcribe (POST multipart with file)",
            "voice_speak": "/api/voice/speak (POST JSON {text, language, voice})",
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
