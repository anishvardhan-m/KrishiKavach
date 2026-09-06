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
