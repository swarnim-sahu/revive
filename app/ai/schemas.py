"""
Schemas and Data Models for Revive Phase 8 AI Intelligence Layer.
Defines failure taxonomy, structured AI proposals, audit metadata, and analysis result envelopes.
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, field_validator

from app.diagnosis.schemas import Actionability, CustomerDiagnosis, DiagnosisCategory


class AIFailureStatus(str, Enum):
    """Explicit failure status taxonomy for AI requests."""

    AI_SUCCESS = "AI_SUCCESS"
    AI_TIMEOUT = "AI_TIMEOUT"
    AI_RATE_LIMITED = "AI_RATE_LIMITED"
    AI_UNAVAILABLE = "AI_UNAVAILABLE"
    AI_SCHEMA_INVALID = "AI_SCHEMA_INVALID"
    AI_GROUNDING_FAILED = "AI_GROUNDING_FAILED"
    AI_LOW_CONFIDENCE = "AI_LOW_CONFIDENCE"
    AI_PROVIDER_ERROR = "AI_PROVIDER_ERROR"


class AIAnalysis(BaseModel):
    """Structured candidate analysis returned by AI intelligence providers."""

    model_config = ConfigDict(extra="forbid")

    diagnosis_candidate: DiagnosisCategory
    confidence: float
    actionability: Actionability
    supporting_evidence: List[str]
    uncertainty_reasons: List[str] = []
    explanation: str

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError("confidence must be between 0.0 and 1.0")
        return round(float(v), 4)


class AIAnalysisMetadata(BaseModel):
    """Audit metadata tracking execution details, latency, provider status, and fallback usage."""

    model_config = ConfigDict(extra="forbid")

    analysis_id: str
    customer_id: str
    context_timestamp: str
    provider: str
    model: str
    prompt_version: str
    schema_version: str
    status: AIFailureStatus
    latency_ms: float
    confidence: float
    fallback_used: bool
    validation_status: str


class AIAnalysisResult(BaseModel):
    """Complete envelope containing AI analysis, audit metadata, and canonical CustomerDiagnosis."""

    model_config = ConfigDict(extra="forbid")

    analysis: Optional[AIAnalysis] = None
    metadata: AIAnalysisMetadata
    fallback_diagnosis: Optional[CustomerDiagnosis] = None
    final_diagnosis: CustomerDiagnosis
