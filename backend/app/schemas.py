"""Pydantic schemas for KrishiKavach API — SIH26131 compliant."""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Farmer schemas
# ---------------------------------------------------------------------------

class FarmerBase(BaseModel):
    name: str = Field(..., max_length=120)
    phone: Optional[str] = Field(None, max_length=30)
    village: Optional[str] = Field(None, max_length=120)
    district: Optional[str] = Field(None, max_length=100)
    state: str = Field(default="Maharashtra", max_length=100)
    primary_language: str = Field(default="marathi", max_length=20)


class FarmerCreate(FarmerBase):
    pass


class FarmerResponse(FarmerBase):
    id: UUID
    created_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Farm schemas
# ---------------------------------------------------------------------------

class FarmCreate(BaseModel):
    location_point: Optional[str] = None
    area_hectares: Optional[float] = None
    primary_crop: Optional[str] = Field(None, max_length=80)


class FarmResponse(FarmCreate):
    id: UUID
    farmer_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Prediction / Case creation schemas
# ---------------------------------------------------------------------------

class PredictionResult(BaseModel):
    """AI prediction result for a crop image."""
    disease: str = Field(..., description="Detected disease name")
    crop: str = Field(..., description="Crop the disease was detected on")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Model confidence score")
    severity: str = Field(..., description="low | medium | high")
    uncertainty_flag: bool = Field(..., description="True if confidence is low")
    description: str = Field(..., description="Human-readable disease description")
    disease_slug: str = Field(..., description="URL-friendly disease slug")
    recommendation_text: str = Field(..., description="Treatment recommendation")
    steps: list[str] = Field(default_factory=list, description="Step-by-step treatment steps")
    warning: Optional[str] = Field(None, description="Caution/warning if any")
    escalate: bool = Field(False, description="Whether to escalate to expert")
    follow_up_days: int = Field(7, description="Follow-up interval in days")
    is_demo: bool = Field(True, description="True if this is a demo prediction (not real ML)")
    model_source: str = Field(..., description="Name of the prediction service")
    alternatives: list[dict] = Field(default_factory=list, description="Top alternative predictions")

    class Config:
        from_attributes = True


class CaseCreateResponse(BaseModel):
    """Response after creating a case from a prediction."""
    case_id: UUID
    prediction: PredictionResult
    farmer_id: UUID
    farm_id: UUID
    detected_at: datetime
    recommendation_given_at: datetime
    next_follow_up_at: date
    case_status: str
    is_demo_prediction: bool
    risk_forecast: Optional[RiskForecastResponse] = Field(
        None,
        description="Lightweight explainable risk forecast (deterministic, not a trained model)",
    )


# ---------------------------------------------------------------------------
# Feedback schemas
# ---------------------------------------------------------------------------

class FeedbackCreate(BaseModel):
    """Schema for farmer feedback on a case."""
    attempted_intervention: bool = Field(..., description="Did the farmer try the recommended treatment?")
    crop_improved: Optional[bool] = Field(None, description="Did the crop improve? (null = unknown)")
    farmer_notes: Optional[str] = Field(None, description="Additional farmer notes")


class FeedbackResponse(FeedbackCreate):
    id: UUID
    case_id: UUID
    feedback_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Case schemas
# ---------------------------------------------------------------------------

class CaseResponse(BaseModel):
    id: UUID
    farm_id: UUID
    farmer_id: UUID
    image_path: Optional[str]
    predicted_disease: Optional[str]
    predicted_crop: Optional[str]
    confidence: Optional[float]
    severity: Optional[str]
    uncertainty_flag: bool
    detected_at: datetime
    recommendation_given_at: Optional[datetime]
    treatment_attempted_at: Optional[datetime]
    next_follow_up_at: date
    last_follow_up_at: Optional[datetime]
    case_status: str
    notes: Optional[str]
    # Escalation status — none when no escalations exist; "active" when at
    # least one unresolved escalation exists; "resolved" when all are closed.
    # `latest_verdict` is the most recent verdict across escalations.
    escalation_status: Optional[str] = None
    latest_verdict: Optional[str] = None

    class Config:
        from_attributes = True


class CaseListResponse(BaseModel):
    cases: list[CaseResponse]
    total: int


# ---------------------------------------------------------------------------
# Follow-up schemas
# ---------------------------------------------------------------------------

class FollowUpPrompt(BaseModel):
    """Schema for follow-up prompts."""
    case_id: UUID
    disease: str
    recommendation_text: str
    follow_up_message: str = Field(
        ..., description="The question to ask the farmer"
    )


# ---------------------------------------------------------------------------
# Demo time simulation schemas
# ---------------------------------------------------------------------------

class DemoTimeResponse(BaseModel):
    current_date: date
    message: str


class DemoAdvanceRequest(BaseModel):
    days: int = Field(1, ge=1, le=365, description="Number of days to advance")


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    database: str
    prediction_mode: str
    demo_time_enabled: bool
    current_demo_date: Optional[date] = None
    version: str = "0.1.0"


# ---------------------------------------------------------------------------
# Upload response
# ---------------------------------------------------------------------------

class UploadResponse(BaseModel):
    image_path: str
    image_url: str
    size_bytes: int


# ---------------------------------------------------------------------------
# Disease reports / outbreak schemas
# ---------------------------------------------------------------------------

class DiseaseReportResponse(BaseModel):
    id: UUID
    district: Optional[str]
    crop_type: Optional[str]
    disease_type: Optional[str]
    risk_level: Optional[str]
    affected_farms: int
    total_cases_reported: int
    valid_from: date
    valid_to: date

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Voice provider schemas (OmniRoute + browser fallback)
# ---------------------------------------------------------------------------

class VoiceConfigResponse(BaseModel):
    """Voice configuration exposed to the frontend.

    The frontend uses this to know which provider to prefer, the default
    language, and whether the browser fallback is supported. NEVER expose
    the upstream API key here.
    """
    # Primary provider — kept for backwards compat when both STT and TTS
    # route through the same service.
    provider: str = Field(..., description="elevenlabs | omniroute | browser")
    # Separate provider per pipeline stage.
    stt_provider: str = Field(..., description="elevenlabs | omniroute | browser")
    tts_provider: str = Field(
        ..., description="elevenlabs | omniroute | browser"
    )
    default_language: str = Field(..., description="BCP-47 default language")
    stt_model: Optional[str] = Field(None, description="Configured STT model name")
    tts_model: Optional[str] = Field(None, description="Configured TTS model name")
    tts_voice: Optional[str] = Field(None, description="Configured TTS voice id")
    elevenlabs_stt_model: Optional[str] = Field(
        None, description="ElevenLabs STT model (when stt_provider == elevenlabs)"
    )
    elevenlabs_voice_id: Optional[str] = Field(
        None, description="ElevenLabs voice ID (when tts_provider == elevenlabs)"
    )
    elevenlabs_model_id: Optional[str] = Field(
        None, description="ElevenLabs TTS model ID (when tts_provider == elevenlabs)"
    )
    browser_fallback_supported: bool = Field(
        True, description="Whether the browser has Web Speech API as a fallback"
    )


class TranscribeResponse(BaseModel):
    """Response from POST /api/voice/transcribe."""
    text: str = Field(..., description="Transcribed text")
    language: str = Field(..., description="BCP-47 language of the audio")
    provider: str = Field(..., description="elevenlabs | omniroute")
    confidence: Optional[float] = Field(
        None, description="Model confidence if available"
    )


class SpeakRequest(BaseModel):
    """Request body for POST /api/voice/speak.

    Returns synthesized audio as an octet-stream response, NOT a JSON body,
    so this schema is informational only.
    """
    text: str = Field(..., max_length=4000, description="Text to synthesize")
    language: str = Field("hi-IN", description="BCP-47 language code")
    voice: Optional[str] = Field(None, description="Override TTS voice id")


# ---------------------------------------------------------------------------
# Risk forecast schemas
# ---------------------------------------------------------------------------

class RiskFactorResponse(BaseModel):
    """One named contribution to the risk score."""
    name: str = Field(..., description="Factor name")
    weight: float = Field(..., description="Maximum weight allocated to this factor")
    raw_signal: float = Field(..., description="Signal value before weight scaling")
    contribution: float = Field(..., description="How much this factor added to the final score")
    note: str = Field(..., description="Human-readable explanation")


class RiskForecastResponse(BaseModel):
    """Result of a risk forecast computation.

    The risk_forecast is a deterministic blend of signals already in the
    project. It is NOT a trained model. The endpoint that produces this
    response labels the source as `model_source` elsewhere.
    """
    risk_score: float = Field(..., ge=0.0, le=100.0, description="Overall 0-100 risk score")
    risk_level: str = Field(..., description="low | medium | high | critical")
    contributing_factors: list[RiskFactorResponse] = Field(
        default_factory=list,
        description="Per-factor contributions",
    )
    recommended_action: str = Field(..., description="Suggested next action")
    explanation: str = Field(..., description="1-2 sentence summary")
    computed_at: datetime = Field(..., description="When this forecast was computed")
    demo_time_used: datetime = Field(..., description="Demo clock value used")
    model_source: str = Field(
        default="HeuristicRiskForecaster (deterministic, explainable, not a trained model)",
        description="Honest label of how this score was produced",
    )


# ---------------------------------------------------------------------------
# Officer dashboard schemas — district-level aggregation for SIH26131
# ---------------------------------------------------------------------------

class DiseaseBreakdownEntry(BaseModel):
    crop: str
    disease: str
    case_count: int
    farm_count: int
    severity: str
    risk_level: str
    last_detected: Optional[str] = None


class InterventionStats(BaseModel):
    total_feedbacks: int
    attempted_treatment: int
    crop_improved: int
    crop_not_improved: int
    no_feedback_yet: int


class OutbreakSummary(BaseModel):
    crop_type: str
    disease_type: str
    risk_level: str
    affected_farms: int
    total_cases_reported: int


class WeatherSummary(BaseModel):
    soil_moisture_percent: Optional[float] = None
    evapotranspiration_mm: Optional[float] = None
    temperature_c: Optional[float] = None
    humidity_percent: Optional[float] = None
    recorded_at: Optional[str] = None


class DistrictRiskProfile(BaseModel):
    risk_score: float
    risk_level: str
    recommended_action: str
    explanation: str
    contributing_factors: Optional[list[RiskFactorResponse]] = None


class DistrictSummary(BaseModel):
    """District-level summary for the Agriculture Officer dashboard.

    All aggregations come from existing tables. Farmer PII (name, phone,
    farmer_id) is intentionally NEVER included in this response.
    """
    district: str
    state: str = "Maharashtra"
    centroid_lon: Optional[float] = None
    centroid_lat: Optional[float] = None
    total_cases: int = 0
    active_cases: int = 0
    resolved_cases: int = 0
    escalated_cases: int = 0
    follow_up_due: int = 0
    severity_low: int = 0
    severity_medium: int = 0
    severity_high: int = 0
    disease_breakdown: list[DiseaseBreakdownEntry] = Field(default_factory=list)
    interventions: Optional[InterventionStats] = None
    active_outbreaks: list[OutbreakSummary] = Field(default_factory=list)
    weather: Optional[WeatherSummary] = None
    risk_profile: Optional[DistrictRiskProfile] = None


# ---------------------------------------------------------------------------
# Expert escalation schemas — SIH26131 expert review workflow
# ---------------------------------------------------------------------------

class EscalationCreate(BaseModel):
    """Body for POST /api/cases/{case_id}/escalate."""
    expert_id: Optional[UUID] = Field(
        None, description="Optional expert to assign. If omitted, unassigned.",
    )
    reason: Optional[str] = Field(
        None, max_length=1000, description="Reason for escalation.",
    )


class EscalationResponse(BaseModel):
    id: UUID
    case_id: UUID
    expert_id: Optional[UUID]
    expert_name: Optional[str] = None
    escalated_at: datetime
    resolved_at: Optional[datetime]
    expert_notes: Optional[str]
    expert_verdict: Optional[str]
    # Lightweight context (no farmer PII)
    predicted_disease: Optional[str] = None
    predicted_crop: Optional[str] = None
    severity: Optional[str] = None
    district: Optional[str] = None
    uncertainty_flag: bool = False

    class Config:
        from_attributes = True


class EscalationListResponse(BaseModel):
    escalations: list[EscalationResponse]
    total: int


class EscalationVerdictRequest(BaseModel):
    """Body for POST /api/escalations/{escalation_id}/verdict."""
    expert_id: Optional[UUID] = Field(
        None, description="Optional expert to record (if not set on the escalation).",
    )
    verdict: str = Field(
        ..., description="confirmed | rejected | needs_more_evidence",
    )
    expert_notes: Optional[str] = Field(
        None, max_length=2000,
        description="Optional notes explaining the verdict.",
    )
    computed_at: str
