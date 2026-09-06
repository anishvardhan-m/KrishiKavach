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

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.database import get_async_session, init_db, close_db
from app.models import (
    Case, CaseFeedback, DiseaseReport, Expert, Farmer, Farm, WeatherContext,
)
from app.schemas import (
    CaseCreateResponse,
    CaseListResponse,
    CaseResponse,
    DemoAdvanceRequest,
    DemoTimeResponse,
    DiseaseReportResponse,
    FeedbackCreate,
    FeedbackResponse,
    HealthResponse,
    PredictionResult,
    UploadResponse,
)
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
    )


# ---------------------------------------------------------------------------
# Case endpoints
# ---------------------------------------------------------------------------

@app.get("/api/cases/due-for-follow-up", response_model=CaseListResponse, tags=["farmer"])
async def list_cases_due_for_follow_up(
    session: AsyncSession = Depends(get_async_session),
) -> CaseListResponse:
    """List cases that are due for follow-up based on current demo time."""
    from app.services.case_service import get_cases_due_for_follow_up
    today = get_demo_date()
    cases = await get_cases_due_for_follow_up(session, as_of_date=today)
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
    return CaseResponse.model_validate(case)


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
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
