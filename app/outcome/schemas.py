"""
Pydantic Schema Models for Revive Phase 7 Outcome Measurement & Revenue Attribution Engine.
Defines canonical outcome types, attribution levels, attribution methods, and outcome audit records.
"""

from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, ValidationInfo

from app.models.entities import _validate_non_empty_string
from app.intervention.schemas import InterventionAction
from app.execution.schemas import ExecutionStatus


class OutcomeType(str, Enum):
    """Canonical Phase 7 Outcome Taxonomy."""

    RECOVERED = "RECOVERED"
    CONVERTED = "CONVERTED"
    NOT_RECOVERED = "NOT_RECOVERED"
    EXPIRED = "EXPIRED"
    ALREADY_CONVERTED = "ALREADY_CONVERTED"
    NO_OBSERVABLE_OUTCOME = "NO_OBSERVABLE_OUTCOME"
    UNKNOWN = "UNKNOWN"


class AttributionStatus(str, Enum):
    """Canonical Phase 7 Attribution Levels."""

    DIRECTLY_OBSERVED = "DIRECTLY_OBSERVED"
    TEMPORALLY_ASSOCIATED = "TEMPORALLY_ASSOCIATED"
    ATTRIBUTION_SUPPORTED = "ATTRIBUTION_SUPPORTED"
    ATTRIBUTION_UNCERTAIN = "ATTRIBUTION_UNCERTAIN"
    UNATTRIBUTED = "UNATTRIBUTED"


class AttributionMethod(str, Enum):
    """Methodology applied to assign revenue attribution."""

    DETERMINISTIC_RULES = "DETERMINISTIC_RULES"
    RULE_BASED_ASSOCIATION = "RULE_BASED_ASSOCIATION"
    TEMPORAL_WINDOW_ASSOCIATION = "TEMPORAL_WINDOW_ASSOCIATION"
    COUNTERFACTUAL_OFFLINE = "COUNTERFACTUAL_OFFLINE"
    NONE = "NONE"


class OutcomeRecord(BaseModel):
    """Canonical, auditable Phase 7 outcome measurement and revenue attribution record."""

    model_config = ConfigDict(extra="forbid")

    outcome_id: str = Field(..., description="Deterministic outcome identity (out_{customer_id}_{execution_id}_{window}h)")
    customer_id: str
    execution_id: str
    decision_id: str
    action: InterventionAction
    execution_status: ExecutionStatus
    execution_timestamp: str

    observation_window_hours: float = Field(..., description="Configured observation window duration in hours")
    observation_start: str = Field(..., description="ISO timestamp marking start of observation window")
    observation_end: str = Field(..., description="ISO timestamp marking end of observation window")

    outcome: OutcomeType = Field(..., description="Canonical resolved outcome category")
    outcome_confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score of resolved outcome")

    attribution_status: AttributionStatus = Field(..., description="Assigned attribution level")
    attribution_method: AttributionMethod = Field(..., description="Method used to calculate attribution")

    evidence_event_ids: List[str] = Field(default_factory=list, description="IDs of observable events supporting outcome")
    evidence_timestamps: List[str] = Field(default_factory=list, description="Timestamps of evidence events")
    payment_reference: Optional[str] = Field(None, description="Authoritative payment/subscription reference if available")

    gross_observed_revenue: Decimal = Field(..., description="Total gross revenue observed post-intervention in INR")
    attributable_revenue: Decimal = Field(..., description="Revenue attributed to intervention in INR")
    intervention_cost: Decimal = Field(..., description="Direct intervention execution cost in INR")
    net_recovered_revenue: Decimal = Field(..., description="Net revenue recovered (Attributable - Cost) in INR")
    revenue_at_risk_at_decision: Decimal = Field(..., description="Original Phase 3/5 revenue-at-risk snapshot in INR")

    resolution_timestamp: str = Field(..., description="ISO timestamp when outcome was resolved")
    resolver_version: str = Field("v1.0.0", description="Version of the outcome resolver logic")

    @field_validator(
        "outcome_id",
        "customer_id",
        "execution_id",
        "decision_id",
        "execution_timestamp",
        "observation_start",
        "observation_end",
        "resolution_timestamp",
    )
    @classmethod
    def validate_outcome_strings(cls, v: Any, info: ValidationInfo) -> str:
        return _validate_non_empty_string(info.field_name or "field", v)
