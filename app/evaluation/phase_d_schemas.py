"""
Phase D Schemas and Data Models for REVIVE Selective Real Gemini Diagnosis v3.0.0.
Defines canonical observable evidence representation with aggregate metrics,
deterministic AI-review routing decisions, structured diagnosis schema,
governance containment, deterministic policy evaluations, and auditable demonstration artifact envelope.
"""

from enum import Enum
import hashlib
import json
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.diagnosis.schemas import Actionability, DiagnosisCategory


class ReviewMode(str, Enum):
    """Deterministic routing mode for Phase D diagnosis."""

    DETERMINISTIC = "DETERMINISTIC"
    AI_REVIEW = "AI_REVIEW"


class GeminiModelCallStatus(str, Enum):
    """Authoritative terminal model-call status taxonomy."""

    REAL_GEMINI = "REAL_GEMINI"
    SCHEMA_REJECTED = "SCHEMA_REJECTED"
    MODEL_ERROR = "MODEL_ERROR"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    FALLBACK_USED = "FALLBACK_USED"


class PhaseDRoutingDecision(BaseModel):
    """Deterministic AI-review routing decision based exclusively on observable evidence."""

    model_config = ConfigDict(extra="forbid")

    customer_id: str
    review_mode: ReviewMode
    trigger_id: str
    routing_reason: str
    observable_signal_summary: Dict[str, Any] = Field(default_factory=dict)


class PhaseDEvidenceRecord(BaseModel):
    """
    Canonical observable customer evidence representation (v3.0.0).
    CRITICAL: Hidden benchmark ground truth (true_root_cause, natural_conversion,
    recoverable, generation_segment) is STRICTLY FORBIDDEN in this schema.
    All aggregate fields MUST be derived purely from observable pre-snapshot event history.
    """

    model_config = ConfigDict(extra="forbid")

    evidence_version: str = "3.0.0"
    customer_id: str
    plan_name: str
    plan_price_inr: float
    billing_cycle: str
    risk_score: float
    risk_tier: str
    revenue_at_risk: float
    hours_until_trial_expiry: float
    trial_active: bool
    payment_failed_observed: bool
    checkout_abandonment_observed: bool
    days_since_last_active: float
    has_prior_conversion: bool

    # Observable lifetime aggregate metrics (derived strictly from observable events <= snapshot)
    lifetime_event_count: int = 0
    lifetime_session_count: int = 0
    lifetime_feature_use_count: int = 0
    lifetime_pricing_view_count: int = 0
    lifetime_checkout_start_count: int = 0
    lifetime_payment_attempt_count: int = 0
    lifetime_payment_success_count: int = 0
    lifetime_payment_failure_count: int = 0

    recent_observable_events: List[Dict[str, Any]]
    observable_evidence_descriptions: List[str]

    def compute_hash(self) -> str:
        """Compute deterministic SHA-256 hash of canonical evidence payload."""
        payload_bytes = json.dumps(self.model_dump(), sort_keys=True).encode("utf-8")
        return hashlib.sha256(payload_bytes).hexdigest()[:16]


class GeminiStructuredDiagnosis(BaseModel):
    """Structured diagnosis contract expected from Google Gemini."""

    model_config = ConfigDict(extra="forbid")

    diagnosis: DiagnosisCategory
    confidence: float
    actionability: Actionability
    rationale: str
    evidence_used: List[str]
    uncertainty_reasons: List[str] = Field(default_factory=list)

    @field_validator("confidence")
    @classmethod
    def validate_confidence_range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError("confidence must be between 0.0 and 1.0")
        return round(float(v), 4)

    @field_validator("rationale")
    @classmethod
    def validate_rationale_non_empty(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("rationale must not be empty")
        return s


class GeminiCallResult(BaseModel):
    """Low-level execution envelope returned by Gemini provider client."""

    model_config = ConfigDict(extra="forbid")

    status: GeminiModelCallStatus
    raw_response_text: Optional[str] = None
    parsed_json: Optional[Dict[str, Any]] = None
    latency_ms: float = 0.0
    prompt_tokens: Optional[int] = None
    candidates_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    retries_attempted: int = 0
    error_type: Optional[str] = None
    error_message: Optional[str] = None


CANONICAL_OBSERVABLE_PRECEDENCE: List[Dict[str, Any]] = [
    {
        "precedence": 1,
        "category": "ALREADY_CONVERTED",
        "actionability": "NONE",
        "title": "CONVERTED / ACTIVE SUBSCRIPTION",
        "description": "Customer has active paid subscription or prior successful payment detected. Overrides all other states.",
        "criteria": "has_prior_conversion == True OR lifetime_payment_success_count > 0",
    },
    {
        "precedence": 2,
        "category": "PAYMENT_FRICTION",
        "actionability": "CANDIDATE",
        "title": "PAYMENT FAILURE",
        "description": "Observed payment failure, card decline, or gateway error (takes precedence over trial expiration or checkout abandonment).",
        "criteria": "payment_failed_observed == True OR lifetime_payment_failure_count > 0",
    },
    {
        "precedence": 3,
        "category": "CHECKOUT_ABANDONMENT",
        "actionability": "CANDIDATE",
        "title": "CHECKOUT ABANDONMENT",
        "description": "Customer initiated checkout and explicitly abandoned without completing payment (takes precedence over passive trial expiration). Note: checkout_started alone is NOT abandonment.",
        "criteria": "checkout_abandonment_observed == True",
    },
    {
        "precedence": 4,
        "category": "NO_MEANINGFUL_RISK",
        "actionability": "NONE",
        "title": "LOW RISK / NO FRICTION",
        "description": "Customer has low churn risk score (risk_score < 0.30) with no higher-precedence observable conversion or payment/checkout friction.",
        "criteria": "risk_score < 0.30 (evaluated after P1-P3 exclusion)",
    },
    {
        "precedence": 5,
        "category": "ENGAGEMENT_DECLINE",
        "actionability": "CANDIDATE",
        "title": "ENGAGEMENT DECLINE",
        "description": "Customer was previously active but usage recency dropped significantly.",
        "criteria": "(lifetime_session_count >= 3 OR lifetime_feature_use_count >= 3) AND days_since_last_active >= 5.0",
    },
    {
        "precedence": 6,
        "category": "MIXED_SIGNALS",
        "actionability": "REQUIRES_REVIEW",
        "title": "CONFLICTING SIGNALS",
        "description": "Competing contradictory recovery signals of comparable weight.",
        "criteria": "(lifetime_pricing_view_count >= 3 AND lifetime_checkout_start_count == 0 AND lifetime_session_count >= 5) OR (lifetime_session_count >= 12 AND lifetime_feature_use_count <= 3)",
    },
    {
        "precedence": 7,
        "category": "LOW_INTENT",
        "actionability": "NONE or CANDIDATE",
        "title": "LOW INTENT",
        "description": "Persistently minimal engagement throughout trial. Distinguished by genuinely low lifetime activity volume.",
        "criteria": "lifetime_session_count <= 4 AND lifetime_feature_use_count <= 5 AND lifetime_pricing_view_count <= 1 AND lifetime_checkout_start_count == 0",
    },
    {
        "precedence": 8,
        "category": "TRIAL_EXPIRATION",
        "actionability": "CANDIDATE",
        "title": "EXPIRING TRIAL",
        "description": "Trial period expiring soon (0 < hours_until_trial_expiry <= 48h) or reached expiry with active product usage (sessions > 4 or feature_uses > 5), without payment failure or checkout abandonment.",
        "criteria": "(hours_until_trial_expiry > 0 AND hours_until_trial_expiry <= 48.0) OR ((hours_until_trial_expiry <= 0 OR trial_active == False) AND (lifetime_session_count > 4 OR lifetime_feature_use_count > 5))",
    },
    {
        "precedence": 9,
        "category": "INSUFFICIENT_EVIDENCE",
        "actionability": "NONE",
        "title": "INSUFFICIENT EVIDENCE",
        "description": "Not enough distinctive journey signals to form a confident diagnosis (unscoreable).",
        "criteria": "No distinctive observable pattern matched",
    },
]

CANONICAL_PRECEDENCE_CATEGORIES: List[str] = [
    item["category"] for item in CANONICAL_OBSERVABLE_PRECEDENCE
]


class PhaseDEvaluationRecord(BaseModel):
    """Per-customer evaluation/demonstration record capturing routing, evidence, model output, and policy decisions."""

    model_config = ConfigDict(extra="forbid")

    customer_id: str
    evidence_version: str
    evidence_hash: str
    prompt_version: str
    model_call_status: GeminiModelCallStatus
    validated_diagnosis: Optional[str] = None
    confidence: Optional[float] = None
    actionability: Optional[str] = None
    rationale: Optional[str] = None
    evidence_used: List[str] = Field(default_factory=list)
    uncertainty_reasons: List[str] = Field(default_factory=list)
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    validation_error: Optional[str] = None

    unsupported_action_claim_detected: bool = False
    execution_bypass_attempt_detected: bool = False
    policy_guard_violation_detected: bool = False
    latency_ms: float = 0.0
    retries_attempted: int = 0
    tokens: Optional[Dict[str, int]] = None

    # Routing metadata (v3.0.0)
    routing_mode: Optional[ReviewMode] = None
    trigger_id: Optional[str] = None
    routing_reason: Optional[str] = None
    observable_signal_summary: Optional[Dict[str, Any]] = None

    # Deterministic policy outcome & governance containment
    policy_result: Optional[Dict[str, Any]] = None
    execution_authority_result: Optional[Dict[str, Any]] = None
    governance_result: Optional[Dict[str, Any]] = None

    # Observable expected diagnosis contract — zero hidden simulator truth
    observable_expected_diagnosis: str = "INSUFFICIENT_EVIDENCE"
    is_scoreable: bool = True
    unscoreable_reason: Optional[str] = None

    is_correct: Optional[bool] = None
    fallback_used: bool = False
    fallback_diagnosis: Optional[str] = None


class PhaseDObservabilityMetrics(BaseModel):
    """Observability and scoreability metrics for evaluation cohort."""

    model_config = ConfigDict(extra="forbid")

    total_evaluated: int
    scoreable_count: int
    unscoreable_count: int
    scoreable_rate_pct: float
    observable_label_distribution: Dict[str, int] = Field(default_factory=dict)
    unscoreable_reasons_summary: Dict[str, int] = Field(default_factory=dict)


class PhaseDQualityMetrics(BaseModel):
    """Model diagnosis quality metrics evaluated against observable expected diagnosis."""

    model_config = ConfigDict(extra="forbid")

    available: bool
    evaluation_basis: str
    scoreable_denominator: int = 0
    diagnosis_accuracy: Optional[float] = None
    macro_precision: Optional[float] = None
    macro_recall: Optional[float] = None
    macro_f1: Optional[float] = None
    per_category_metrics: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    confusion_matrix: Optional[List[List[int]]] = None
    confusion_matrix_labels: Optional[List[str]] = None


class PhaseDOperationalMetrics(BaseModel):
    """Operational reliability, execution timing, and retry metrics."""

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


class PhaseDGovernanceMetrics(BaseModel):
    """Governance and execution containment metrics."""

    model_config = ConfigDict(extra="forbid")

    execution_bypass_attempts_observed: int
    unsupported_action_claims_observed: int
    policy_guard_violations_observed: int
    non_compliant_records_count: int
    safety_compliance_rate_pct: float
    governance_verdict: str


class PhaseDCostAccounting(BaseModel):
    """Token usage tracking and cost accounting."""

    model_config = ConfigDict(extra="forbid")

    cost_data_status: str
    prompt_tokens_sum: Optional[int] = None
    candidates_tokens_sum: Optional[int] = None
    total_tokens_sum: Optional[int] = None
    estimated_cost_inr: Optional[float] = None
    cost_basis_note: str


class PhaseDObservableSignalSummary(BaseModel):
    """Observable signal summary for Phase D demonstration case."""

    model_config = ConfigDict(extra="forbid")

    risk_score: float
    risk_tier: str
    plan: str
    lifetime_events: int
    sessions: int
    feature_uses: int
    pricing_page_views: int
    checkout_starts: int
    payment_failures: int
    days_since_last_active: Optional[float] = None
    observable_signals: List[str] = Field(default_factory=list)
    recent_events: List[Dict[str, Any]] = Field(default_factory=list)


class PhaseDGeminiResponseSummary(BaseModel):
    """Gemini response summary for Phase D demonstration case."""

    model_config = ConfigDict(extra="forbid")

    model: str
    status: str
    diagnosis: Optional[str] = None
    confidence: Optional[float] = None
    actionability: Optional[str] = None
    rationale: Optional[str] = None
    evidence_used: List[str] = Field(default_factory=list)
    uncertainty_notes: Optional[str] = None
    unsupported_claims: List[str] = Field(default_factory=list)
    execution_bypass_attempted: bool = False
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    validation_error: Optional[str] = None
    latency_ms: float = 0.0



class PhaseDGovernanceSummary(BaseModel):
    """Governance verification summary for Phase D demonstration case."""

    model_config = ConfigDict(extra="forbid")

    execution_authority: str
    policy_gating_applied: bool
    execution_bypass_detected: bool
    unsupported_action_claim_detected: bool
    policy_guard_violation_detected: bool
    governance_verdict: str


class PhaseDPolicySummary(BaseModel):
    """Deterministic policy decision summary for Phase D demonstration case."""

    model_config = ConfigDict(extra="forbid")

    eligibility_status: str
    selected_action: str
    expected_value: float
    policy_version: str
    governed_decision_summary: str


class PhaseDExecutionAuthoritySummary(BaseModel):
    """Execution authority isolation summary for Phase D demonstration case."""

    model_config = ConfigDict(extra="forbid")

    authority_held_by: str
    gemini_has_execution_power: bool
    guarded_execution_status: str


class PhaseDDemonstrationCase(BaseModel):
    """Structured demonstration case for Phase D v3 selective AI review."""

    model_config = ConfigDict(extra="forbid")

    customer_id: str
    routing_mode: str
    trigger_id: str
    routing_reason: str
    observable_signal_summary: PhaseDObservableSignalSummary
    gemini_response: PhaseDGeminiResponseSummary
    governance_result: PhaseDGovernanceSummary
    policy_result: PhaseDPolicySummary
    execution_authority_result: PhaseDExecutionAuthoritySummary
    cost_accounting: Optional[Dict[str, Any]] = None


class PhaseDEvaluationArtifact(BaseModel):
    """Complete machine-readable Phase D evidence artifact envelope (v3.0.0)."""

    model_config = ConfigDict(extra="forbid")

    metadata: Dict[str, Any]
    phase_version: str = "3.0.0"
    model: str
    prompt_version: str
    evidence_version: str
    execution_state: str
    demonstration_case: Optional[PhaseDDemonstrationCase] = None
    operational_metrics: PhaseDOperationalMetrics
    governance_metrics: PhaseDGovernanceMetrics
    cost_accounting: PhaseDCostAccounting
    failure_summary: Dict[str, Any]
    quality_metrics: Optional[PhaseDQualityMetrics] = None
    observability_metrics: Optional[PhaseDObservabilityMetrics] = None
    evaluation_records: List[Dict[str, Any]] = Field(default_factory=list)
    sample_records: List[Dict[str, Any]] = Field(default_factory=list)
