"""
Pydantic Schemas for REVIVE FastAPI Presentation & Dashboard Layer.
Defines explicit response models for summary benchmarks and customer evidence endpoints.
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class DatasetSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customers_evaluated: int
    events_processed: int
    customers_with_payment_failures: int


class RiskSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    critical: int
    high: int
    medium: int
    low: int
    average_risk_score: float
    average_revenue_at_risk: float


class DiagnosisSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payment_friction: int
    actionable: int
    non_actionable: int


class PolicySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eligible_customers: int
    ineligible_customers: int
    payment_recovery_actions: int
    reminder_actions: int


class ExpectedRecoverySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_revenue_at_risk: float
    total_expected_recovery: float
    expected_recovery_rate_pct: float


class MeasuredRecoverySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gross_observed_revenue: float
    attributable_revenue: float
    intervention_cost: float
    net_recovered_revenue: float
    measured_recovery_rate_pct: float
    recovered_customers: int


class OutcomesSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    distribution: Dict[str, int]


class AttributionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    distribution: Dict[str, int]


class ExecutionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: int
    successful: int
    failed: int
    blocked: int
    duplicates_prevented: int


class DashboardSummaryResponse(BaseModel):
    """Aggregate dashboard benchmark summary response model."""

    model_config = ConfigDict(extra="forbid")

    dataset: DatasetSummary
    risk: RiskSummary
    diagnosis: DiagnosisSummary
    policy: PolicySummary
    expected_recovery: ExpectedRecoverySummary
    measured_recovery: MeasuredRecoverySummary
    outcomes: OutcomesSummary
    attribution: AttributionSummary
    execution: ExecutionSummary


class CustomerEvidenceResponse(BaseModel):
    """Safe, auditable per-customer evidence response model."""

    model_config = ConfigDict(extra="forbid")

    customer_id: str
    risk_score: float
    risk_tier: str
    revenue_at_risk: float
    diagnosis: str
    diagnosis_confidence: float
    ai_status: str
    ai_confidence: float
    fallback_used: bool
    eligibility_status: str
    selected_action: str
    expected_value: float
    decision_reason: str
    execution_status: str
    failure_reason: Optional[str] = None
    outcome: Optional[str] = None
    outcome_confidence: Optional[float] = None
    attribution_status: Optional[str] = None
    attributable_revenue: Optional[float] = None
    net_recovered_revenue: Optional[float] = None
    payment_reference: Optional[str] = None
    evidence_event_ids: List[str] = Field(default_factory=list)


class HealthCheckResponse(BaseModel):
    """API service health check response model."""

    model_config = ConfigDict(extra="forbid")

    status: str = "ok"
    service: str = "revive-api"
