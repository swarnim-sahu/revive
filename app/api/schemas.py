"""
Pydantic Schemas for REVIVE FastAPI Presentation & Dashboard Layer.
Defines explicit response models for summary benchmarks, customer evidence,
Phase B 10k-pair evaluation, Phase A real Test Mode proof, 9-stage audit timeline,
exceptions ledger, and controlled failure scenarios.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# 1. Operational Batch Models (Seed 42, 100 cases)
# ---------------------------------------------------------------------------

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

    provenance: str = "CUSTOMER OPERATIONAL STATE (100-Customer Batch)"
    dataset: DatasetSummary
    risk: RiskSummary
    diagnosis: DiagnosisSummary
    policy: PolicySummary
    expected_recovery: ExpectedRecoverySummary
    measured_recovery: MeasuredRecoverySummary
    outcomes: OutcomesSummary
    attribution: AttributionSummary
    execution: ExecutionSummary


class CandidateActionScoreResponse(BaseModel):
    """Candidate intervention score and policy evaluation details."""

    model_config = ConfigDict(extra="forbid")

    action: str
    expected_value: float
    recovery_probability: float
    direct_cost: float
    eligible: bool
    selected: bool
    rejection_reason: Optional[str] = None


class CustomerEvidenceResponse(BaseModel):
    """Safe, auditable per-customer evidence response model."""

    model_config = ConfigDict(extra="forbid")

    customer_id: str
    risk_score: float
    risk_tier: str
    revenue_at_risk: float
    plan: str = "pro"
    diagnosis: str
    diagnosis_confidence: float
    actionability: str = "CANDIDATE"
    ai_status: str
    ai_confidence: float
    fallback_used: bool
    eligibility_status: str
    policy_version: str = "Phase 5 Bounded EV v1.0"
    assumption_version: str = "Recovery Probability v1.0"
    selected_action: str
    expected_value: float
    decision_reason: str
    candidate_actions: List[CandidateActionScoreResponse] = Field(default_factory=list)
    execution_status: str
    failure_reason: Optional[str] = None
    outcome: Optional[str] = None
    outcome_confidence: Optional[float] = None
    attribution_status: Optional[str] = None
    attributable_revenue: Optional[float] = None
    net_recovered_revenue: Optional[float] = None
    payment_reference: Optional[str] = None
    evidence_event_ids: List[str] = Field(default_factory=list)
    supporting_evidence: List[str] = Field(default_factory=list)
    risk_signals: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# 2. Phase B Benchmark Presentation Models (10,000 paired units)
# ---------------------------------------------------------------------------

class BenchmarkMetadata(BaseModel):
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


class BenchmarkEconomics(BaseModel):
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
    treatment_no_treatment_conversions: int
    treatment_total_gross_revenue: float
    gross_revenue_delta_vs_control: float
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


class BenchmarkDiagnosisAccuracy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall_accuracy: float
    macro_f1: float
    macro_precision: float
    macro_recall: float


class BenchmarkInterventionAppropriateness(BaseModel):
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


class BenchmarkActionStat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int
    rate: float


class BenchmarkDecisionFunnel(BaseModel):
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
    per_action_distribution: Dict[str, BenchmarkActionStat]


class BenchmarkSafetyGovernance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stop_rate: float
    escalation_rate: float
    blocked_ineligible_rate: float
    unnecessary_intervention_rate: float
    execution_failure_rate: float
    retryable_failure_count: int
    terminal_failure_count: int


class BenchmarkThroughput(BaseModel):
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


class BenchmarkResponse(BaseModel):
    """Authoritative Phase B benchmark response model."""

    model_config = ConfigDict(extra="forbid")

    available: bool
    diagnostic_message: Optional[str] = None
    provenance: str = "PHASE B BENCHMARK (Synthetic Controlled Evaluation)"
    source_artifact: str = "docs/evidence/phase_b_summary.json"
    metadata: Optional[BenchmarkMetadata] = None
    economics: Optional[BenchmarkEconomics] = None
    diagnosis_accuracy: Optional[BenchmarkDiagnosisAccuracy] = None
    intervention_appropriateness: Optional[BenchmarkInterventionAppropriateness] = None
    decision_funnel: Optional[BenchmarkDecisionFunnel] = None
    safety_governance: Optional[BenchmarkSafetyGovernance] = None
    throughput: Optional[BenchmarkThroughput] = None
    exception_summary: Optional[Dict[str, Any]] = None
    reconciliation_passed: Optional[bool] = None


# ---------------------------------------------------------------------------
# 3. Phase A Real Razorpay Test Mode Proof Models
# ---------------------------------------------------------------------------

class RazorpayProofResponse(BaseModel):
    """Authoritative Phase A real Razorpay Test Mode proof evidence response."""

    model_config = ConfigDict(extra="forbid")

    proof_type: str
    status: str
    environment: str
    payment_link_id: str
    payment_id: str
    webhook_event_id: str
    reference_id: str
    correlated_customer_id: str
    plan_id: str
    plan_name: str
    plan_price: float
    currency: str
    outcome: str
    outcome_confidence: float
    attribution_status: str
    attributable_revenue: float
    intervention_cost: float
    net_recovered_revenue: float
    duplicate_delivery_status: str
    proof_timestamp: str
    signature_verification: str
    disclosure: str
    provenance: str = "RAZORPAY TEST MODE (Captured Proof)"


# ---------------------------------------------------------------------------
# 4. 9-Stage Chronological Audit Timeline Models
# ---------------------------------------------------------------------------

class AuditStageRecord(BaseModel):
    """Single stage in the 9-stage chronological audit timeline."""

    model_config = ConfigDict(extra="forbid")

    stage_index: int
    stage_name: str
    status: str
    timestamp: Optional[str] = None
    summary: str
    details: Dict[str, Any] = Field(default_factory=dict)


class AuditTimelineResponse(BaseModel):
    """Full 9-stage chronological audit timeline response for a customer."""

    model_config = ConfigDict(extra="forbid")

    customer_id: str
    provenance: str = "CUSTOMER OPERATIONAL STATE"
    total_stages: int = 9
    completed_stages: int
    final_status: str
    stages: List[AuditStageRecord]


# ---------------------------------------------------------------------------
# 5. Exceptions & Governed Non-Actions Center
# ---------------------------------------------------------------------------

class ExceptionItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    customer_id: Optional[str] = None
    decision: str
    reason: str
    policy_action: str
    financial_impact: float
    retryable: bool


class ExceptionCenterResponse(BaseModel):
    """Aggregate exception accounting and governed non-actions response."""

    model_config = ConfigDict(extra="forbid")

    provenance: str = "PHASE B BENCHMARK & EXECUTION EXCEPTIONS"
    total_exceptions: int
    retryable_count: int
    terminal_count: int
    human_escalation_count: int
    total_financial_impact: float
    by_stage: Dict[str, int]
    by_failure_type: Dict[str, int]
    sample_exceptions: List[ExceptionItemResponse] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 6. Controlled Failure Demonstration Models
# ---------------------------------------------------------------------------

class FailureScenarioStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_number: int
    step_name: str
    status: str
    description: str
    state_snapshot: Dict[str, Any] = Field(default_factory=dict)


class FailureScenarioResponse(BaseModel):
    """Deterministic controlled failure scenario with real runtime semantics."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    title: str
    category: str
    label: str = "CONTROLLED DETERMINISTIC FAILURE FIXTURE"
    customer_id: str
    action: str
    failure_reason: str
    failure_type: str
    retryable: bool
    attempt_count: int
    max_retries: int
    safe_action: str
    final_state: str
    financial_exposure: float
    steps: List[FailureScenarioStep]


# ---------------------------------------------------------------------------
# 7. Health Check Model
# ---------------------------------------------------------------------------

class HealthCheckResponse(BaseModel):
    """API service health check response model."""

    model_config = ConfigDict(extra="forbid")

    status: str = "ok"
    service: str = "revive-api"


# ---------------------------------------------------------------------------
# 8. Phase D Gemini Evaluation Response Models
# ---------------------------------------------------------------------------

class GeminiOperationalMetricsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempted_evaluations: int
    successful_evaluations: int
    schema_rejections: int
    model_errors: int
    unavailable_evaluations: int
    fallback_evaluations: int
    scoreable_evaluations: int = 0
    not_scoreable_evaluations: int = 0
    total_retries: int = 0
    rate_limit_events: int = 0
    success_rate_pct: float
    average_latency_ms: float
    p95_latency_ms: float
    reconciliation_passed: bool
    reconciliation_formula: str


class GeminiQualityMetricsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available: bool
    evaluation_basis: str
    scoreable_denominator: int = 0
    diagnosis_accuracy: Optional[float] = None
    macro_precision: Optional[float] = None
    macro_recall: Optional[float] = None
    macro_f1: Optional[float] = None
    per_category_metrics: Dict[str, Dict[str, Any]] = {}
    confusion_matrix: Optional[List[List[int]]] = None
    confusion_matrix_labels: Optional[List[str]] = None


class GeminiObservabilityMetricsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_evaluated: int
    scoreable_count: int
    unscoreable_count: int
    scoreable_rate_pct: float
    observable_label_distribution: Dict[str, int] = Field(default_factory=dict)
    unscoreable_reasons_summary: Dict[str, int] = Field(default_factory=dict)


class GeminiGovernanceMetricsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_bypass_attempts_observed: int
    unsupported_action_claims_observed: int
    policy_guard_violations_observed: int
    non_compliant_records_count: int = 0
    safety_compliance_rate_pct: float
    governance_verdict: str


class GeminiCostAccountingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cost_data_status: str
    prompt_tokens_sum: Optional[int] = None
    candidates_tokens_sum: Optional[int] = None
    total_tokens_sum: Optional[int] = None
    estimated_cost_inr: Optional[float] = None
    cost_basis_note: str


class GeminiEvaluationResponse(BaseModel):
    """Response envelope for Phase D Gemini evaluation endpoint."""

    model_config = ConfigDict(extra="forbid")

    available: bool
    status: str
    diagnostic_message: Optional[str] = None
    provenance: str = "PHASE D REAL GEMINI EVALUATION"
    source_artifact: str = "docs/evidence/phase_d_gemini_evaluation.json"
    metadata: Optional[Dict[str, Any]] = None
    model: Optional[str] = None
    prompt_version: Optional[str] = None
    evidence_version: Optional[str] = None
    phase_version: Optional[str] = None
    operational_metrics: Optional[GeminiOperationalMetricsResponse] = None
    quality_metrics: Optional[GeminiQualityMetricsResponse] = None
    observability_metrics: Optional[GeminiObservabilityMetricsResponse] = None
    governance_metrics: Optional[GeminiGovernanceMetricsResponse] = None
    cost_accounting: Optional[GeminiCostAccountingResponse] = None
    failure_summary: Optional[Dict[str, Any]] = None
    sample_records: Optional[List[Dict[str, Any]]] = None
    demonstration_case: Optional[Dict[str, Any]] = None


class RazorpaySandboxDemoResponse(BaseModel):
    """Response model for Phase 9 Controlled Razorpay Test Mode demonstration artifact."""

    model_config = ConfigDict(extra="forbid")

    available: bool
    status: str  # e.g. "CONTROLLED RAZORPAY TEST MODE — NOT RUN" or "CONTROLLED RAZORPAY TEST MODE — EXECUTED"
    phase_version: str = "9.0.0"
    operation: str = "CREATE_PAYMENT_LINK"
    environment: str = "sandbox"
    execution_status: str  # "NOT_RUN", "DRY_RUN", "EXECUTED", "FAILED"
    payment_status: str = "PENDING"  # Hard invariant: Payment Link Created != Payment Recovered
    payload_id: Optional[str] = None
    provider_reference: Optional[str] = None
    short_url: Optional[str] = None
    webhook_status: str = "PENDING_WEBHOOK"
    outcome_status: str = "NO_OBSERVABLE_OUTCOME"
    attribution_status: str = "UNATTRIBUTED"
    timestamps: Optional[Dict[str, Optional[str]]] = None
    idempotency_result: Optional[str] = None
    policy_decision: Optional[Dict[str, Any]] = None
    failure_reason: Optional[str] = None
    disclosure: str = (
        "Controlled Razorpay Test Mode execution demonstration. "
        "A created Payment Link is an outbound recovery attempt and is NOT recovered revenue. "
        "Financial recovery and attribution strictly require subsequent verified payment evidence."
    )
    source_artifact: str = "docs/evidence/phase9_razorpay_sandbox_demo.json"
