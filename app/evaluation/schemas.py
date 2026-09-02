"""
Evaluation Schemas and Data Transfer Objects for REVIVE Phase B.
Defines strict Pydantic models for Control vs Treatment paired evaluation,
comparative economics, diagnosis accuracy, intervention appropriateness,
lifecycle exceptions, decision funnels, and performance throughput.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ControlCaseRecord(BaseModel):
    """Evaluation record for a single customer in the Control Arm (No Intervention baseline)."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    customer_id: str
    control_converted: bool
    control_gross_revenue: float
    control_net_revenue: float
    control_revenue_at_risk: float
    control_case_status: str


class TreatmentCaseRecord(BaseModel):
    """Evaluation record for a single customer in the Treatment Arm (Full REVIVE Pipeline)."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    customer_id: str
    risk_score: float
    risk_tier: str
    revenue_at_risk: float
    diagnosis: str
    diagnosis_confidence: float
    diagnosis_actionability: str
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
    treatment_converted: bool
    conversion_classification: str = Field(
        ...,
        description="4-way conversion taxonomy: NATURAL_CONVERSION, GENUINE_INCREMENTAL_RECOVERY, OBSERVED_UNRECOVERABLE_CONVERSION, NO_TREATMENT_CONVERSION",
    )
    is_natural_conversion: bool = False
    is_genuine_incremental_recovery: bool = False
    is_observed_unrecoverable_conversion: bool = False
    gross_observed_revenue: float
    attributable_revenue: float
    intervention_cost: float
    net_recovered_revenue: float
    total_net_revenue: float
    payment_reference: Optional[str] = None


class PairedCaseResult(BaseModel):
    """Joined experimental record pairing identical counterfactual control and treatment outcomes."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    customer_id: str
    plan_id: str
    plan_price: float
    control: ControlCaseRecord
    treatment: TreatmentCaseRecord
    conversion_classification: str = Field(
        ...,
        description="4-way conversion classification for the treatment arm outcome",
    )
    is_incremental_conversion: bool = Field(
        ...,
        description="True ONLY if treatment converted, control did NOT convert, and case is genuinely recoverable (gt.recoverable=True)",
    )
    incremental_net_revenue: float = Field(
        ...,
        description="Treatment Realized Net Revenue minus Control Net Revenue",
    )


class ExceptionRecord(BaseModel):
    """Structured audit record for an exception, block, or non-standard case."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    stage: str
    status: str
    failure_type: str
    retryable: bool
    safe_action_taken: str
    financial_impact: float
    human_escalation_required: bool
    reason: str
    timestamp: Optional[str] = None


class ComparativeEconomics(BaseModel):
    """Macro-economic comparison between Control and Treatment arms."""

    model_config = ConfigDict(extra="forbid")

    paired_experimental_units: int
    control_evaluations: int
    control_conversions: int
    control_conversion_rate: float
    control_gross_revenue: float
    control_net_revenue: float
    control_revenue_at_risk: float

    treatment_evaluations: int
    treatment_total_conversions: int
    treatment_total_conversion_rate: float
    treatment_natural_conversions: int
    treatment_genuine_incremental_recoveries: int
    treatment_observed_unrecoverable_conversions: int
    treatment_total_gross_revenue: float
    treatment_attributable_recovery_revenue: float
    treatment_intervention_cost: float
    treatment_net_recovered_revenue: float
    treatment_total_net_revenue: float
    treatment_genuine_incremental_revenue: float
    treatment_expected_recovery_value: float

    conversion_lift_points: float
    conversion_relative_lift_pct: float
    incremental_net_revenue: float
    maximum_recoverable_revenue: float
    recoverable_capture_rate_pct: float
    recovery_roi: float


class DiagnosisAccuracySummary(BaseModel):
    """Offline accuracy metrics for the Diagnosis Engine against simulation ground truth."""

    model_config = ConfigDict(extra="forbid")

    overall_accuracy: float
    macro_precision: float
    macro_recall: float
    macro_f1: float
    uncertain_rate: float
    per_class_report: Dict[str, Any]
    confusion_matrix: List[List[int]]
    labels: List[str]


class InterventionAppropriatenessSummary(BaseModel):
    """Post-hoc intervention appropriateness, safety, evidence consistency, and NO_ACTION analysis."""

    model_config = ConfigDict(extra="forbid")

    active_interventions_count: int
    targeted_recoverable_count: int
    targeted_recoverable_rate: float
    unnecessary_on_natural_count: int
    unnecessary_on_natural_rate: float
    ineffective_on_unrecoverable_count: int
    ineffective_on_unrecoverable_rate: float
    safety_policy_compliance_rate: float
    evidence_action_consistency_rate: float

    no_action_count: int
    no_action_rate: float
    no_action_on_natural_count: int
    no_action_on_non_recoverable_count: int
    no_action_on_recoverable_missed_count: int
    no_action_safe_avoidance_rate: float
    no_action_missed_opportunity_rate: float


class DecisionFunnelSummary(BaseModel):
    """Aggregate 10-stage decision funnel."""

    model_config = ConfigDict(extra="forbid")

    total_population: int
    at_risk_population: int
    diagnosable_population: int
    eligible_population: int
    no_action_count: int
    no_action_rate: float
    human_review_count: int
    human_review_rate: float
    automated_intervention_count: int
    automated_intervention_rate: float
    per_action_distribution: Dict[str, Any]


class SafetyGovernanceSummary(BaseModel):
    """Safety, stopping rules, and operational escalation summary."""

    model_config = ConfigDict(extra="forbid")

    stop_rate: float
    escalation_rate: float
    blocked_ineligible_rate: float
    unnecessary_intervention_rate: float
    execution_failure_rate: float
    retryable_failure_count: int
    terminal_failure_count: int


class ThroughputSummary(BaseModel):
    """Actual wall-clock performance and throughput measurements."""

    model_config = ConfigDict(extra="forbid")

    start_time: str
    end_time: str
    elapsed_seconds: float
    paired_experimental_units: int
    control_arm_evaluations: int
    treatment_arm_evaluations: int
    total_arm_evaluations: int
    initial_journey_events: int
    post_treatment_events: int
    events_processed: int
    paired_units_per_second: float
    total_evaluations_per_second: float
    events_per_second: float
    initial_journey_events_per_second: float
    average_case_latency_ms: float
    p95_case_latency_ms: float


class ExperimentMetadata(BaseModel):
    """Reproducibility metadata envelope for Phase B benchmark runs."""

    model_config = ConfigDict(extra="forbid")

    experiment_id: str
    seed: int
    paired_experimental_units: int
    control_evaluations: int
    treatment_evaluations: int
    total_arm_evaluations: int
    simulator_version: str
    policy_version: str
    assumption_version: str
    risk_model_version: str
    python_version: str
    timestamp: str
    git_revision: Optional[str] = None


class PhaseBEvaluationResult(BaseModel):
    """Master structured benchmark result schema for Phase B."""

    model_config = ConfigDict(extra="forbid")

    metadata: ExperimentMetadata
    economics: ComparativeEconomics
    diagnosis_accuracy: DiagnosisAccuracySummary
    intervention_appropriateness: InterventionAppropriatenessSummary
    decision_funnel: DecisionFunnelSummary
    safety_governance: SafetyGovernanceSummary
    throughput: ThroughputSummary
    outcome_distribution: Dict[str, int]
    attribution_distribution: Dict[str, int]
    exception_summary: Dict[str, Any]
    reconciliation_passed: bool
