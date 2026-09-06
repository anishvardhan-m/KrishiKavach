"""SQLAlchemy models for KrishiKavach - SIH26131 compliant."""
from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    Boolean,
    ForeignKey,
    Index,
    func,
    Date,
    Numeric,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

import uuid

from app.database import Base


# ---------------------------------------------------------------------------
# Helpers for demo time simulation
# ---------------------------------------------------------------------------

_DEMO_DATE: date | None = None


def set_demo_date(d: date) -> None:
    """Set the simulated demo date. Used for testing follow-up timelines."""
    global _DEMO_DATE
    _DEMO_DATE = d


def get_demo_date() -> date:
    """Return the current demo date, falling back to real date if not set."""
    from datetime import date as _date
    if _DEMO_DATE is not None:
        return _DEMO_DATE
    return _date.today()


# ---------------------------------------------------------------------------
# Farmer
# ---------------------------------------------------------------------------

class Farmer(Base):
    """Farmer profile — linked to one or more farms."""
    __tablename__ = "farmers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True, unique=True)
    village: Mapped[str | None] = mapped_column(String(120), nullable=True)
    district: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True, default="Maharashtra")
    primary_language: Mapped[str | None] = mapped_column(String(20), nullable=True, default="marathi")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    farms = relationship("Farm", back_populates="farmer", cascade="all, delete-orphan")
    feedbacks = relationship("CaseFeedback", back_populates="farmer", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# Farm
# ---------------------------------------------------------------------------

class Farm(Base):
    """A farmer's field/farm with geolocation."""
    __tablename__ = "farms"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    farmer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("farmers.id", ondelete="CASCADE"), nullable=False
    )
    location_point: Mapped[str | None] = mapped_column(
        String(42),  # PostGIS WKT / GeoJSON text; could use WKB via geoalchemy2
        nullable=True,
    )
    area_hectares: Mapped[float | None] = mapped_column(Float, nullable=True)
    primary_crop: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    farmer = relationship("Farmer", back_populates="farms")
    cases = relationship("Case", back_populates="farm", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# Case / Crop Health Report
# ---------------------------------------------------------------------------

class Case(Base):
    """A crop-health case created when a farmer reports a disease/pest."""
    __tablename__ = "cases"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    farm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("farms.id", ondelete="CASCADE"), nullable=False
    )
    farmer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("farmers.id", ondelete="CASCADE"), nullable=False
    )

    # Detection metadata
    image_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_thumbnail_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    # AI prediction
    predicted_disease: Mapped[str | None] = mapped_column(String(120), nullable=True)
    predicted_crop: Mapped[str | None] = mapped_column(String(80), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    severity: Mapped[str | None] = mapped_column(
        String(20),  # low | medium | high
        nullable=True,
    )
    uncertainty_flag: Mapped[Boolean] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # Timestamp tracking
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    recommendation_given_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    treatment_attempted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_follow_up_at: Mapped[date] = mapped_column(
        Date, nullable=False
    )
    last_follow_up_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Case status
    case_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",  # active | resolved | escalated | closed
    )

    # Notes / farmer feedback
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    farm = relationship("Farm", back_populates="cases")
    feedbacks = relationship("CaseFeedback", back_populates="case", cascade="all, delete-orphan")
    escalations = relationship("Escalation", back_populates="case", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# Case Feedback
# ---------------------------------------------------------------------------

class CaseFeedback(Base):
    """Feedback collected from farmer after a recommendation/treatment."""
    __tablename__ = "case_feedbacks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    farmer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("farmers.id", ondelete="SET NULL"), nullable=True
    )

    # Farmer's response
    attempted_intervention: Mapped[Boolean] = mapped_column(
        Boolean, nullable=False, default=False
    )
    crop_improved: Mapped[Boolean | None] = mapped_column(
        Boolean, nullable=True
    )
    farmer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # When feedback was recorded
    feedback_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    case = relationship("Case", back_populates="feedbacks")
    farmer = relationship("Farmer", back_populates="feedbacks")


# ---------------------------------------------------------------------------
# Expert / Escalation
# ---------------------------------------------------------------------------

class Expert(Base):
    """Agronomy expert who can validate/escalate cases."""
    __tablename__ = "experts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    specialty: Mapped[str | None] = mapped_column(String(80), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_active: Mapped[Boolean] = mapped_column(
        Boolean, nullable=False, default=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    escalations = relationship("Escalation", back_populates="expert")


class Escalation(Base):
    """Links a case to an expert for validation."""
    __tablename__ = "escalations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    expert_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("experts.id", ondelete="SET NULL"), nullable=True
    )
    escalated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expert_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    expert_verdict: Mapped[str | None] = mapped_column(
        String(80),  # confirmed | rejected | needs_more_info
        nullable=True,
    )

    # Relationships
    case = relationship("Case", back_populates="escalations")
    expert = relationship("Expert", back_populates="escalations")


# ---------------------------------------------------------------------------
# Disease Outbreak / Geospatial Intelligence
# ---------------------------------------------------------------------------

class DiseaseReport(Base):
    """Aggregated outbreak / risk report per district/crop."""
    __tablename__ = "disease_reports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    district: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True, default="Maharashtra")
    crop_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    disease_type: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # Risk metrics
    risk_level: Mapped[str | None] = mapped_column(
        String(20),  # low | medium | high | critical
        nullable=True,
    )
    affected_farms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_cases_reported: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    confirmed_cases: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
    )

    # Time range
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date] = mapped_column(Date, nullable=False)

    # Metadata
    source_cases: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
    )  # number of primary case records
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Spatial index (geoalchemy2 will handle this)
    __table_args__ = (
        Index(
            "ix_disease_reports_district_crop",
            "district",
            "crop_type",
            "disease_type",
        ),
    )


# ---------------------------------------------------------------------------
# Weather / Environmental Context
# ---------------------------------------------------------------------------

class WeatherContext(Base):
    """Latest weather / environmental data for a farmer's district."""
    __tablename__ = "weather_contexts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    district: Mapped[str | None] = mapped_column(String(100), nullable=False)
    state: Mapped[str | None] = mapped_column(
        String(100), nullable=False, default="Maharashtra"
    )

    # Current conditions
    soil_moisture_percent: Mapped[float | None] = mapped_column(
        Float, nullable=True,
    )
    evapotranspiration_mm: Mapped[float | None] = mapped_column(
        Float, nullable=True,
    )
    temperature_c: Mapped[float | None] = mapped_column(
        Float, nullable=True,
    )
    humidity_percent: Mapped[float | None] = mapped_column(
        Float, nullable=True,
    )

    # When data was fetched/recorded
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    source: Mapped[str | None] = mapped_column(
        String(80),  # e.g. "soil_moisture_csv", "evapotranspiration_csv", "api"
        nullable=True,
    )


# ---------------------------------------------------------------------------
# Indexes for common query patterns
# ---------------------------------------------------------------------------

# Cases by farm, ordered by creation
Index("ix_cases_farm_id", Case.farm_id)
Index("ix_cases_next_follow_up", Case.next_follow_up_at)
Index("ix_cases_status", Case.case_status)
Index("ix_cases_uncertainty", Case.uncertainty_flag)

# Farm lookups
Index("ix_farms_farmer_id", Farm.farmer_id)

# Feedback lookups
Index("ix_case_feedbacks_case_id", CaseFeedback.case_id)

# Outbreak reports
Index("ix_disease_reports_district", DiseaseReport.district)
Index("ix_disease_reports_crop", DiseaseReport.crop_type)


# ---------------------------------------------------------------------------
# Migration helpers
# ---------------------------------------------------------------------------

def migration_id() -> str:
    """Return a migration identifier string for Alembic."""
    import uuid as _uuid
    return str(_uuid.uuid4())


def migration_uuid(raw: str) -> UUID:
    """Parse a UUID from a migration string."""
    import uuid as _uuid
    return _uuid.UUID(raw)