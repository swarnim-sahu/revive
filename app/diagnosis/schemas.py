"""
Data Models and Enum Schemas for Revive Root-Cause Diagnosis Engine (Phase 4).
Uses Pydantic v2 for validation and strict domain contracts.
"""

from enum import Enum
from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, field_validator, ValidationInfo

from app.models.entities import _validate_non_empty_string


class DiagnosisCategory(str, Enum):
    """Authoritative taxonomy of root-cause diagnoses."""

    NO_MEANINGFUL_RISK = "NO_MEANINGFUL_RISK"
    LOW_INTENT = "LOW_INTENT"
    CHECKOUT_ABANDONMENT = "CHECKOUT_ABANDONMENT"
    PAYMENT_FRICTION = "PAYMENT_FRICTION"
    TRIAL_EXPIRATION = "TRIAL_EXPIRATION"
    ENGAGEMENT_DECLINE = "ENGAGEMENT_DECLINE"
    MIXED_SIGNALS = "MIXED_SIGNALS"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    ALREADY_CONVERTED = "ALREADY_CONVERTED"


class EvidenceCategory(str, Enum):
    """Categories of observable journey evidence."""

    PAYMENT_ATTEMPT = "PAYMENT_ATTEMPT"
    PAYMENT_FAILURE = "PAYMENT_FAILURE"
    PAYMENT_SUCCESS = "PAYMENT_SUCCESS"
    CHECKOUT_STARTED = "CHECKOUT_STARTED"
    CHECKOUT_COMPLETED = "CHECKOUT_COMPLETED"
    CHECKOUT_ABANDONED = "CHECKOUT_ABANDONED"
    PAYMENT_METHOD_ADDED = "PAYMENT_METHOD_ADDED"
    PRICING_VIEW = "PRICING_VIEW"
    SESSION_ACTIVITY = "SESSION_ACTIVITY"
    FEATURE_USAGE = "FEATURE_USAGE"
    PRODUCT_ACTIVITY = "PRODUCT_ACTIVITY"
    RECENCY_DECLINE = "RECENCY_DECLINE"
    TRIAL_EXPIRY_PROXIMITY = "TRIAL_EXPIRY_PROXIMITY"
    CONVERSION_STATE = "CONVERSION_STATE"


class ConfidenceTier(str, Enum):
    """Operational diagnostic confidence tiers."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class Actionability(str, Enum):
    """Downstream actionability state for decision layer."""

    NONE = "NONE"
    CANDIDATE = "CANDIDATE"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"


class EvidenceItem(BaseModel):
    """Structured observable evidence supporting or contradicting a candidate cause."""

    model_config = ConfigDict(extra="forbid")

    evidence_type: EvidenceCategory
    strength: float
    source_event: Optional[str] = None
    description: str
    observed_at: Optional[str] = None

    @field_validator("strength")
    @classmethod
    def validate_strength(cls, v: float) -> float:
        if not (-1.0 <= v <= 1.0):
            raise ValueError("strength must be between -1.0 and 1.0")
        return round(float(v), 4)

    @field_validator("description")
    @classmethod
    def validate_desc(cls, v: str) -> str:
        return _validate_non_empty_string("description", v)


class CandidateCauseScore(BaseModel):
    """Normalized evidence score for a single candidate cause."""

    model_config = ConfigDict(extra="forbid")

    cause: DiagnosisCategory
    score: float
    supporting_count: int = 0
    contradictory_count: int = 0

    @field_validator("score")
    @classmethod
    def validate_score(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError("Candidate cause score must be between 0.0 and 1.0")
        return round(float(v), 4)


class CustomerDiagnosis(BaseModel):
    """Output root-cause diagnosis for a customer."""

    model_config = ConfigDict(extra="forbid")

    customer_id: str
    prediction_timestamp: str
    risk_score: float
    risk_tier: str
    diagnosis: DiagnosisCategory
    confidence: float
    confidence_tier: ConfidenceTier
    actionability: Actionability
    candidate_causes: List[CandidateCauseScore]
    supporting_evidence: List[EvidenceItem]
    explanation: str

    @field_validator("customer_id", "prediction_timestamp", "risk_tier", "explanation")
    @classmethod
    def validate_strings(cls, v: str, info: ValidationInfo) -> str:
        return _validate_non_empty_string(info.field_name or "field", v)

    @field_validator("risk_score", "confidence")
    @classmethod
    def validate_probabilities(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError("Probabilities/scores must be between 0.0 and 1.0")
        return round(float(v), 4)
