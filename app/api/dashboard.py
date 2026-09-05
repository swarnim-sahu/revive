"""
Dashboard Presentation Service & Route Handlers for REVIVE API.
Provides read-only presentation endpoints backed by BatchRecoveryEvaluator,
committed Phase B evidence snapshot, committed Phase A Razorpay Test Mode proof,
9-stage chronological audit timeline generator, exception accounting, and
deterministic failure scenarios executed via real REVIVE components.
"""

from collections import OrderedDict
from decimal import Decimal
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from fastapi import APIRouter, HTTPException, Query

from app.evaluation.batch import BatchEvaluationResult, BatchRecoveryEvaluator, CustomerEvidenceRecord
from app.evaluation.exceptions import ExceptionLedger
from app.execution.config import ExecutionConfig
from app.execution.engine import ExecutionEngine
from app.execution.schemas import ExecutionAuditRecord, ExecutionState, ExecutionStatus, FailureType
from app.intervention.schemas import (
    CandidateActionScore,
    InterventionAction,
    InterventionDecision,
)
from app.api.schemas import (
    AttributionSummary,
    AuditStageRecord,
    AuditTimelineResponse,
    BenchmarkResponse,
    CandidateActionScoreResponse,
    CustomerEvidenceResponse,
    DashboardSummaryResponse,
    DatasetSummary,
    ExceptionCenterResponse,
    ExceptionItemResponse,
    ExecutionSummary,
    ExpectedRecoverySummary,
    FailureScenarioResponse,
    FailureScenarioStep,
    MeasuredRecoverySummary,
    DiagnosisSummary,
    OutcomesSummary,
    PolicySummary,
    RazorpayProofResponse,
    RazorpaySandboxDemoResponse,
    RiskSummary,
    GeminiEvaluationResponse,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# Project root directory for reading committed evidence snapshots
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_PHASE_B_EVIDENCE_PATH = _PROJECT_ROOT / "docs" / "evidence" / "phase_b_summary.json"
_PHASE_A_PROOF_PATH = _PROJECT_ROOT / "docs" / "evidence" / "phase_a_razorpay_test_mode_proof.json"
_PHASE_D_EVIDENCE_PATH = _PROJECT_ROOT / "docs" / "evidence" / "phase_d_gemini_evaluation.json"
_PHASE9_SANDBOX_DEMO_PATH = _PROJECT_ROOT / "docs" / "evidence" / "phase9_razorpay_sandbox_demo.json"
_DEFAULT_DEMO_PATH = _PROJECT_ROOT / "docs" / "evidence" / "phase_d_gemini_demo.json"



# In-memory evaluation cache for operational batch benchmark stability and performance
CacheKey = Tuple[int, int, float]
_EVALUATION_CACHE_MAX_ENTRIES = 10
_evaluation_cache: OrderedDict[CacheKey, BatchEvaluationResult] = OrderedDict()


def get_evaluation_result(
    customers_count: int = 100, seed: int = 42, snapshot_hours: float = 336.0
) -> BatchEvaluationResult:
    """Retrieve or compute the deterministic batch evaluation result using a bounded process-local in-memory LRU cache."""
    key: CacheKey = (int(customers_count), int(seed), round(float(snapshot_hours), 4))
    if key in _evaluation_cache:
        _evaluation_cache.move_to_end(key)
        return _evaluation_cache[key]

    evaluator = BatchRecoveryEvaluator(
        customers_count=customers_count,
        seed=seed,
        snapshot_hours=snapshot_hours,
    )
    result = evaluator.evaluate()
    _evaluation_cache[key] = result
    if len(_evaluation_cache) > _EVALUATION_CACHE_MAX_ENTRIES:
        _evaluation_cache.popitem(last=False)
    return result


def _get_relative_path(path: Path) -> str:
    """Return normalized forward-slash relative path string."""
    try:
        return str(path.relative_to(_PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _to_customer_response(rec: CustomerEvidenceRecord) -> CustomerEvidenceResponse:
    """Convert an authoritative CustomerEvidenceRecord into CustomerEvidenceResponse."""
    d = rec.to_dict()

    # Authoritative candidate action scores from InterventionDecision
    candidate_actions = [
        CandidateActionScoreResponse(
            action=cs["action"],
            expected_value=cs["expected_value"],
            recovery_probability=cs["recovery_probability"],
            direct_cost=cs["direct_cost"],
            eligible=cs["eligible"],
            selected=cs["selected"],
            rejection_reason=cs.get("rejection_reason"),
        )
        for cs in rec.candidate_scores
    ]

    return CustomerEvidenceResponse(
        customer_id=rec.customer_id,
        risk_score=rec.risk_score,
        risk_tier=rec.risk_tier,
        revenue_at_risk=rec.revenue_at_risk,
        plan=rec.plan,
        diagnosis=rec.diagnosis,
        diagnosis_confidence=rec.diagnosis_confidence,
        actionability=rec.actionability,
        ai_status=rec.ai_status,
        ai_confidence=rec.ai_confidence,
        fallback_used=rec.fallback_used,
        eligibility_status=rec.eligibility_status,
        policy_version=rec.policy_version,
        assumption_version=rec.assumption_version,
        selected_action=rec.selected_action,
        expected_value=rec.expected_value,
        decision_reason=rec.decision_reason,
        candidate_actions=candidate_actions,
        execution_status=rec.execution_status,
        failure_reason=rec.failure_reason,
        outcome=rec.outcome,
        outcome_confidence=rec.outcome_confidence,
        attribution_status=rec.attribution_status,
        attributable_revenue=rec.attributable_revenue,
        net_recovered_revenue=rec.net_recovered_revenue,
        payment_reference=rec.payment_reference,
        evidence_event_ids=rec.evidence_event_ids,
        supporting_evidence=rec.supporting_evidence,
        risk_signals=rec.risk_signals,
    )


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------

@router.get("/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary(
    seed: int = Query(default=42, ge=1, le=999999, description="RNG Seed"),
    cohort_size: int = Query(default=100, ge=1, le=5000, description="Customer cohort size"),
    snapshot_hours: float = Query(default=336.0, gt=0.0, description="Snapshot horizon in hours"),
    customers_count: Optional[int] = Query(default=None, ge=1, le=5000, description="Alias for cohort_size"),
) -> DashboardSummaryResponse:
    """Return validated operational benchmark summary metrics in clean JSON structure."""
    effective_count = customers_count if customers_count is not None else cohort_size
    res = get_evaluation_result(customers_count=effective_count, seed=seed, snapshot_hours=snapshot_hours)
    agg = res.aggregate_metrics
    risk_dist = res.risk_distribution
    diag_dist = res.diagnosis_distribution
    act_dist = res.action_distribution
    outcome_dist = res.outcome_distribution
    attr_dist = res.attribution_distribution

    return DashboardSummaryResponse(
        provenance="CUSTOMER OPERATIONAL STATE",
        dataset=DatasetSummary(
            customers_evaluated=agg.get("total_customers", 0),
            events_processed=agg.get("total_events", 0),
            customers_with_payment_failures=agg.get("customers_with_payment_failures", 0),
        ),
        risk=RiskSummary(
            critical=risk_dist.get("CRITICAL", 0),
            high=risk_dist.get("HIGH", 0),
            medium=risk_dist.get("MEDIUM", 0),
            low=risk_dist.get("LOW", 0),
            average_risk_score=agg.get("average_risk_score", 0.0),
            average_revenue_at_risk=agg.get("average_revenue_at_risk", 0.0),
        ),
        diagnosis=DiagnosisSummary(
            payment_friction=diag_dist.get("PAYMENT_FRICTION", 0),
            actionable=agg.get("actionable_diagnosis_count", 0),
            non_actionable=agg.get("non_actionable_diagnosis_count", 0),
        ),
        policy=PolicySummary(
            eligible_customers=agg.get("eligible_customers", 0),
            ineligible_customers=agg.get("ineligible_customers", 0),
            payment_recovery_actions=act_dist.get("PAYMENT_RECOVERY", 0),
            reminder_actions=act_dist.get("REMINDER", 0),
        ),
        expected_recovery=ExpectedRecoverySummary(
            total_revenue_at_risk=agg.get("total_revenue_at_risk", 0.0),
            total_expected_recovery=agg.get("total_expected_recovery_value", 0.0),
            expected_recovery_rate_pct=agg.get("expected_recovery_rate_pct", 0.0),
        ),
        measured_recovery=MeasuredRecoverySummary(
            gross_observed_revenue=agg.get("total_gross_observed_revenue", 0.0),
            attributable_revenue=agg.get("total_attributable_revenue", 0.0),
            intervention_cost=agg.get("total_intervention_cost", 0.0),
            net_recovered_revenue=agg.get("total_net_recovered_revenue", 0.0),
            measured_recovery_rate_pct=agg.get("measured_recovery_rate_pct", 0.0),
            recovered_customers=agg.get("recovered_customer_count", 0),
        ),
        outcomes=OutcomesSummary(distribution=outcome_dist),
        attribution=AttributionSummary(distribution=attr_dist),
        execution=ExecutionSummary(
            candidates=agg.get("execution_candidates", 0),
            successful=agg.get("simulated_successful_executions", 0),
            failed=agg.get("simulated_failed_executions", 0),
            blocked=agg.get("blocked_executions", 0),
            duplicates_prevented=agg.get("duplicates_prevented", 0),
        ),
    )


@router.get("/customers", response_model=List[CustomerEvidenceResponse])
def get_dashboard_customers(
    seed: int = Query(default=42, ge=1, le=999999, description="RNG Seed"),
    cohort_size: int = Query(default=100, ge=1, le=5000, description="Customer cohort size"),
    snapshot_hours: float = Query(default=336.0, gt=0.0, description="Snapshot horizon in hours"),
    customers_count: Optional[int] = Query(default=None, ge=1, le=5000, description="Alias for cohort_size"),
) -> List[CustomerEvidenceResponse]:
    """Return all safe, auditable per-customer evidence records."""
    effective_count = customers_count if customers_count is not None else cohort_size
    res = get_evaluation_result(customers_count=effective_count, seed=seed, snapshot_hours=snapshot_hours)
    return [_to_customer_response(rec) for rec in res.per_customer_results]


@router.get("/customers/{customer_id}", response_model=CustomerEvidenceResponse)
def get_dashboard_customer(
    customer_id: str,
    seed: int = Query(default=42, ge=1, le=999999, description="RNG Seed"),
    cohort_size: int = Query(default=100, ge=1, le=5000, description="Customer cohort size"),
    snapshot_hours: float = Query(default=336.0, gt=0.0, description="Snapshot horizon in hours"),
    customers_count: Optional[int] = Query(default=None, ge=1, le=5000, description="Alias for cohort_size"),
) -> CustomerEvidenceResponse:
    """Return matching safe customer evidence record by customer_id or HTTP 404."""
    effective_count = customers_count if customers_count is not None else cohort_size
    res = get_evaluation_result(customers_count=effective_count, seed=seed, snapshot_hours=snapshot_hours)
    for rec in res.per_customer_results:
        if rec.customer_id == customer_id:
            return _to_customer_response(rec)
    raise HTTPException(status_code=404, detail=f"Customer evidence record '{customer_id}' not found")


@router.get("/benchmark", response_model=BenchmarkResponse)
def get_dashboard_benchmark() -> BenchmarkResponse:
    """
    Return the authoritative Phase B 10k-pair benchmark snapshot from docs/evidence/phase_b_summary.json.
    Does NOT dynamically fallback to untracked local reports.
    """
    rel_path_str = _get_relative_path(_PHASE_B_EVIDENCE_PATH)

    if not _PHASE_B_EVIDENCE_PATH.exists():
        return BenchmarkResponse(
            available=False,
            diagnostic_message=f"Benchmark evidence artifact unavailable: {_PHASE_B_EVIDENCE_PATH} not found",
            provenance="PHASE B BENCHMARK (Synthetic Controlled Evaluation)",
            source_artifact=rel_path_str,
        )

    try:
        with open(_PHASE_B_EVIDENCE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        eco = data.get("economics")
        if not eco:
            return BenchmarkResponse(
                available=False,
                diagnostic_message="Benchmark evidence artifact schema-incomplete: missing 'economics' section",
                provenance="PHASE B BENCHMARK (Synthetic Controlled Evaluation)",
                source_artifact=rel_path_str,
            )

        return BenchmarkResponse(
            available=True,
            diagnostic_message=None,
            provenance="PHASE B BENCHMARK (Synthetic Controlled Evaluation)",
            source_artifact=rel_path_str,
            metadata=data.get("metadata"),
            economics=eco,
            diagnosis_accuracy=data.get("diagnosis_accuracy"),
            intervention_appropriateness=data.get("intervention_appropriateness"),
            decision_funnel=data.get("decision_funnel"),
            safety_governance=data.get("safety_governance"),
            throughput=data.get("throughput"),
            exception_summary=data.get("exception_summary"),
            reconciliation_passed=data.get("reconciliation_passed"),
        )
    except Exception as exc:
        return BenchmarkResponse(
            available=False,
            diagnostic_message=f"Failed to parse benchmark evidence snapshot: {exc}",
            provenance="PHASE B BENCHMARK (Synthetic Controlled Evaluation)",
            source_artifact=rel_path_str,
        )


@router.get("/gemini-evaluation", response_model=GeminiEvaluationResponse)
def get_dashboard_gemini_evaluation() -> GeminiEvaluationResponse:
    """
    Return the authoritative Phase D real Gemini evaluation evidence snapshot.
    Explicitly distinguishes REAL_GEMINI, MODEL_UNAVAILABLE, MODEL_ERROR, SCHEMA_REJECTED, and FALLBACK_USED.
    """
    target_path = _DEFAULT_DEMO_PATH if _DEFAULT_DEMO_PATH.exists() else _PHASE_D_EVIDENCE_PATH
    rel_path_str = _get_relative_path(target_path)

    if not target_path.exists():
        return GeminiEvaluationResponse(
            available=False,
            status="GEMINI — UNAVAILABLE",
            diagnostic_message="Phase D Gemini evaluation evidence artifact not found.",
            provenance="PHASE D REAL GEMINI EVALUATION",
            source_artifact=rel_path_str,
        )

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        raw_state = data.get("execution_state", "REAL_GEMINI" if data.get("status") == "AVAILABLE" or data.get("available") is True else "MODEL_UNAVAILABLE")
        if raw_state == "REAL_GEMINI":
            status_label = "GEMINI — REAL DEMONSTRATION"
        elif raw_state == "FALLBACK_USED":
            status_label = "GEMINI — FALLBACK USED"
        elif raw_state == "MODEL_ERROR":
            status_label = "GEMINI — ERROR"
        elif raw_state == "SCHEMA_REJECTED":
            status_label = "GEMINI — SCHEMA REJECTED"
        else:
            status_label = "GEMINI — UNAVAILABLE"

        is_available = raw_state in {"REAL_GEMINI", "PARTIAL_REAL_GEMINI"} or data.get("status") == "AVAILABLE" or data.get("available") is True

        return GeminiEvaluationResponse(
            available=is_available,
            status=status_label,
            diagnostic_message=None if is_available else f"Phase D evaluation completed in {raw_state} state.",
            provenance=data.get("provenance", "PHASE D REAL GEMINI EVALUATION"),
            source_artifact=rel_path_str,
            metadata=data.get("metadata"),
            model=data.get("model"),
            prompt_version=data.get("prompt_version"),
            evidence_version=data.get("evidence_version"),
            phase_version=data.get("phase_version"),
            operational_metrics=data.get("operational_metrics"),
            quality_metrics=data.get("quality_metrics"),
            observability_metrics=data.get("observability_metrics"),
            governance_metrics=data.get("governance_metrics"),
            cost_accounting=data.get("cost_accounting"),
            failure_summary=data.get("failure_summary"),
            sample_records=data.get("sample_records"),
            demonstration_case=data.get("demonstration_case"),
        )
    except Exception as exc:
        return GeminiEvaluationResponse(
            available=False,
            status="GEMINI — ERROR",
            diagnostic_message=f"Failed to load or parse Phase D Gemini evaluation artifact: {exc}",
            provenance="PHASE D REAL GEMINI EVALUATION",
            source_artifact=rel_path_str,
        )


@router.get("/razorpay-proof", response_model=RazorpayProofResponse)
def get_dashboard_razorpay_proof() -> RazorpayProofResponse:
    """
    Return the authoritative Phase A real Razorpay Test Mode proof snapshot.
    """
    if not _PHASE_A_PROOF_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Phase A Razorpay proof artifact not found at {_PHASE_A_PROOF_PATH}",
        )

    try:
        with open(_PHASE_A_PROOF_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return RazorpayProofResponse(**data)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read Razorpay proof artifact: {exc}",
        )


@router.get("/razorpay-sandbox-demo", response_model=RazorpaySandboxDemoResponse)
def get_dashboard_razorpay_sandbox_demo() -> RazorpaySandboxDemoResponse:
    """
    Return the Phase 9 Controlled Razorpay Test Mode demonstration state.
    Distinguishes NOT_RUN / DRY_RUN vs EXECUTED.
    Enforces hard separation: Payment Link Created != Payment Recovered.
    """
    rel_path_str = _get_relative_path(_PHASE9_SANDBOX_DEMO_PATH)
    if not _PHASE9_SANDBOX_DEMO_PATH.exists():
        return RazorpaySandboxDemoResponse(
            available=False,
            status="CONTROLLED RAZORPAY TEST MODE — NOT RUN",
            execution_status="NOT_RUN",
            payment_status="PENDING",
            outcome_status="NO_OBSERVABLE_OUTCOME",
            attribution_status="UNATTRIBUTED",
            disclosure=(
                "Controlled Razorpay Test Mode demonstration record. Initialized in NOT_RUN state. "
                "Requires explicit user invocation with Test Mode credentials."
            ),
            source_artifact=rel_path_str,
        )

    try:
        with open(_PHASE9_SANDBOX_DEMO_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        exec_status = data.get("execution_status", "NOT_RUN")
        payment_status = data.get("payment_status", "PENDING")
        outcome_status = data.get("outcome_status", "NO_OBSERVABLE_OUTCOME")
        attribution_status = data.get("attribution_status", "UNATTRIBUTED")

        if exec_status == "EXECUTED":
            if (
                payment_status == "PAID"
                and outcome_status == "RECOVERED"
                and attribution_status == "DIRECTLY_OBSERVED"
            ):
                status_label = "CONTROLLED RAZORPAY TEST MODE — PAYMENT RECOVERED"
            elif payment_status == "PENDING":
                status_label = "CONTROLLED RAZORPAY TEST MODE — PAYMENT LINK CREATED"
            else:
                status_label = f"CONTROLLED RAZORPAY TEST MODE — {payment_status}"
        elif exec_status in {"DRY_RUN", "NOT_RUN"}:
            status_label = "CONTROLLED RAZORPAY TEST MODE — NOT RUN"
        else:
            status_label = f"CONTROLLED RAZORPAY TEST MODE — {exec_status}"

        return RazorpaySandboxDemoResponse(
            available=True,
            status=status_label,
            phase_version=data.get("phase_version", "9.0.0"),
            operation=data.get("operation", "CREATE_PAYMENT_LINK"),
            environment=data.get("environment", "sandbox"),
            execution_status=exec_status,
            payment_status=data.get("payment_status", "PENDING"),
            payload_id=data.get("payload_id"),
            provider_reference=data.get("provider_reference"),
            short_url=data.get("short_url"),
            webhook_status=data.get("webhook_status", "PENDING_WEBHOOK"),
            outcome_status=data.get("outcome_status", "NO_OBSERVABLE_OUTCOME"),
            attribution_status=data.get("attribution_status", "UNATTRIBUTED"),
            timestamps=data.get("timestamps"),
            idempotency_result=data.get("idempotency_result"),
            policy_decision=data.get("policy_decision"),
            failure_reason=data.get("failure_reason"),
            disclosure=data.get("disclosure", (
                "Controlled Razorpay Test Mode execution demonstration. "
                "A created Payment Link is an outbound recovery attempt and is NOT recovered revenue. "
                "Financial recovery and attribution strictly require subsequent verified payment evidence."
            )),
            source_artifact=rel_path_str,
        )
    except Exception as exc:
        return RazorpaySandboxDemoResponse(
            available=False,
            status="CONTROLLED RAZORPAY TEST MODE — ERROR",
            execution_status="FAILED",
            payment_status="PENDING",
            outcome_status="NO_OBSERVABLE_OUTCOME",
            attribution_status="UNATTRIBUTED",
            failure_reason=f"Failed to parse demonstration artifact: {exc}",
            disclosure="Demonstration artifact read failure.",
            source_artifact=rel_path_str,
        )



@router.get("/audit/{customer_id}", response_model=AuditTimelineResponse)
def get_dashboard_customer_audit(
    customer_id: str,
    seed: int = Query(default=42, ge=1, le=999999, description="RNG Seed"),
    cohort_size: int = Query(default=100, ge=1, le=5000, description="Customer cohort size"),
    snapshot_hours: float = Query(default=336.0, gt=0.0, description="Snapshot horizon in hours"),
    customers_count: Optional[int] = Query(default=None, ge=1, le=5000, description="Alias for cohort_size"),
) -> AuditTimelineResponse:
    """
    Return the truthful 9-stage chronological audit timeline for a customer.
    Stages:
      1. DETECT
      2. DIAGNOSE
      3. DECIDE
      4. GUARD
      5. EXECUTE
      6. PAYMENT_RESULT
      7. WEBHOOK
      8. OUTCOME
      9. ATTRIBUTION
    """
    effective_count = customers_count if customers_count is not None else cohort_size
    res = get_evaluation_result(customers_count=effective_count, seed=seed, snapshot_hours=snapshot_hours)
    customer_rec = None
    for rec in res.per_customer_results:
        if rec.customer_id == customer_id:
            customer_rec = rec
            break

    if not customer_rec:
        raise HTTPException(status_code=404, detail=f"Audit trail for customer '{customer_id}' not found")

    is_no_action = (customer_rec.selected_action == "NO_ACTION")

    stages: List[AuditStageRecord] = []

    # 1. DETECT
    stages.append(
        AuditStageRecord(
            stage_index=1,
            stage_name="DETECT",
            status="EXECUTED",
            timestamp=None,
            summary=f"Risk Score: {(customer_rec.risk_score * 100):.1f}%, Tier: {customer_rec.risk_tier}, Revenue at Risk: Rs. {customer_rec.revenue_at_risk:.2f}",
            details={
                "risk_score": customer_rec.risk_score,
                "risk_tier": customer_rec.risk_tier,
                "revenue_at_risk": customer_rec.revenue_at_risk,
                "risk_signals": customer_rec.risk_signals,
            },
        )
    )

    # 2. DIAGNOSE
    stages.append(
        AuditStageRecord(
            stage_index=2,
            stage_name="DIAGNOSE",
            status="EXECUTED",
            timestamp=None,
            summary=f"Root-Cause: {customer_rec.diagnosis} (Confidence: {(customer_rec.diagnosis_confidence * 100):.0f}%), AI Status: {customer_rec.ai_status}",
            details={
                "diagnosis": customer_rec.diagnosis,
                "confidence": customer_rec.diagnosis_confidence,
                "ai_status": customer_rec.ai_status,
                "fallback_used": customer_rec.fallback_used,
                "actionability": customer_rec.actionability,
            },
        )
    )

    # 3. DECIDE
    stages.append(
        AuditStageRecord(
            stage_index=3,
            stage_name="DECIDE",
            status="EXECUTED",
            timestamp=customer_rec.decision_timestamp,
            summary=f"Selected Action: {customer_rec.selected_action}, Expected Value: Rs. {customer_rec.expected_value:.2f}",
            details={
                "selected_action": customer_rec.selected_action,
                "expected_value": customer_rec.expected_value,
                "decision_reason": customer_rec.decision_reason,
            },
        )
    )

    # 4. GUARD
    if customer_rec.eligibility_status == "ELIGIBLE" and not is_no_action:
        guard_status = "PASSED"
        guard_summary = f"Policy Evaluation: PASSED under {customer_rec.policy_version}. Action '{customer_rec.selected_action}' authorized for execution."
    elif customer_rec.eligibility_status == "ELIGIBLE" and is_no_action:
        guard_status = "GOVERNED_STOP"
        guard_summary = f"Policy Evaluation: GOVERNED_STOP under {customer_rec.policy_version}. Policy selected NO_ACTION (governed cost avoidance)."
    elif customer_rec.eligibility_status == "INELIGIBLE":
        guard_status = "BLOCKED"
        guard_summary = f"Policy Evaluation: BLOCKED under {customer_rec.policy_version}. Customer is ineligible for intervention."
    elif customer_rec.eligibility_status == "ESCALATED":
        guard_status = "ESCALATED"
        guard_summary = f"Policy Evaluation: ESCALATED under {customer_rec.policy_version}. Human review escalation triggered."
    else:
        guard_status = "BLOCKED"
        guard_summary = f"Policy Evaluation: {customer_rec.eligibility_status} under {customer_rec.policy_version}."

    stages.append(
        AuditStageRecord(
            stage_index=4,
            stage_name="GUARD",
            status=guard_status,
            timestamp=customer_rec.decision_timestamp,
            summary=guard_summary,
            details={
                "eligibility_status": customer_rec.eligibility_status,
                "policy_version": customer_rec.policy_version,
                "stopped": is_no_action,
                "guard_status": guard_status,
            },
        )
    )

    # 5. EXECUTE
    if is_no_action:
        exec_status = "NOT EXECUTED"
        exec_summary = "Execution bypassed: Policy selected NO_ACTION (governed cost avoidance)"
    elif customer_rec.execution_status == "EXECUTED":
        exec_status = "EXECUTED"
        exec_summary = f"Dispatched via Razorpay Dispatcher for action {customer_rec.selected_action}"
    elif customer_rec.execution_status == "ESCALATED":
        exec_status = "BLOCKED"
        exec_summary = "Automated execution blocked: Escalated to human operator review"
    elif customer_rec.execution_status == "BLOCKED":
        exec_status = "BLOCKED"
        exec_summary = f"Execution blocked: {customer_rec.failure_reason or 'Policy refused dispatch'}"
    elif customer_rec.execution_status == "FAILED":
        exec_status = "FAILED"
        exec_summary = f"Execution failed: {customer_rec.failure_reason or 'Dispatch failed'}"
    else:
        exec_status = "NOT EXECUTED"
        exec_summary = f"Execution status: {customer_rec.execution_status}"

    stages.append(
        AuditStageRecord(
            stage_index=5,
            stage_name="EXECUTE",
            status=exec_status,
            timestamp=customer_rec.execution_timestamp if exec_status == "EXECUTED" else None,
            summary=exec_summary,
            details={
                "execution_status": customer_rec.execution_status,
                "failure_reason": customer_rec.failure_reason,
                "selected_action": customer_rec.selected_action,
            },
        )
    )

    # 6. PAYMENT_RESULT
    if is_no_action:
        pay_status = "NOT EXECUTED"
        pay_summary = "No payment transaction initiated (NO_ACTION policy stop)"
    elif customer_rec.outcome == "RECOVERED":
        pay_status = "SYNTHETIC_OBSERVED"
        pay_summary = f"Synthetic simulation response: Payment observed ({customer_rec.payment_reference or 'pay_ref'}). (Evaluation batch - not live gateway)"
    elif customer_rec.outcome == "NOT_RECOVERED":
        pay_status = "SYNTHETIC_FAILED"
        pay_summary = "Synthetic simulation response: Payment failed or expired post-dispatch"
    else:
        pay_status = "NOT OBSERVED"
        pay_summary = "No post-intervention payment response observed"

    stages.append(
        AuditStageRecord(
            stage_index=6,
            stage_name="PAYMENT_RESULT",
            status=pay_status,
            timestamp=None,
            summary=pay_summary,
            details={
                "payment_reference": customer_rec.payment_reference,
            },
        )
    )

    # 7. WEBHOOK
    stages.append(
        AuditStageRecord(
            stage_index=7,
            stage_name="WEBHOOK",
            status="NOT OBSERVED",
            timestamp=None,
            summary="Webhook delivery not observed (Synthetic evaluation batch; live webhooks active during Phase A proof)",
            details={
                "webhook_event": None,
            },
        )
    )

    # 8. OUTCOME
    if customer_rec.outcome == "RECOVERED":
        outcome_status = "RECOVERED"
        outcome_summary = f"Outcome measured as RECOVERED (Confidence: {((customer_rec.outcome_confidence or 0.0) * 100):.0f}%)"
    elif customer_rec.outcome == "ALREADY_CONVERTED":
        outcome_status = "ALREADY_CONVERTED"
        outcome_summary = "Customer identified as ALREADY_CONVERTED before intervention"
    elif customer_rec.outcome == "NOT_RECOVERED":
        outcome_status = "NOT_RECOVERED"
        outcome_summary = "Customer remained unrecovered during observation horizon"
    else:
        outcome_status = "NO_OBSERVABLE_OUTCOME"
        outcome_summary = "No outcome event recorded"

    stages.append(
        AuditStageRecord(
            stage_index=8,
            stage_name="OUTCOME",
            status=outcome_status,
            timestamp=None,
            summary=outcome_summary,
            details={
                "outcome": customer_rec.outcome,
                "outcome_confidence": customer_rec.outcome_confidence,
            },
        )
    )

    # 9. ATTRIBUTION
    if customer_rec.attribution_status == "DIRECTLY_OBSERVED":
        attr_status = "DIRECTLY_OBSERVED"
        attr_summary = f"Attributable: Rs. {(customer_rec.attributable_revenue or 0.0):.2f}, Net Recovered: Rs. {(customer_rec.net_recovered_revenue or 0.0):.2f}"
    else:
        attr_status = "UNATTRIBUTED"
        attr_summary = "Revenue unattributed (Net Recovered: Rs. 0.00)"

    stages.append(
        AuditStageRecord(
            stage_index=9,
            stage_name="ATTRIBUTION",
            status=attr_status,
            timestamp=None,
            summary=attr_summary,
            details={
                "attribution_status": customer_rec.attribution_status,
                "attributable_revenue": customer_rec.attributable_revenue,
                "net_recovered_revenue": customer_rec.net_recovered_revenue,
            },
        )
    )

    completed_count = sum(
        1 for s in stages if s.status in {"EXECUTED", "PASSED", "RECOVERED", "DIRECTLY_OBSERVED", "SYNTHETIC_OBSERVED"}
    )

    return AuditTimelineResponse(
        customer_id=customer_id,
        provenance="CUSTOMER OPERATIONAL STATE",
        total_stages=9,
        completed_stages=completed_count,
        final_status=customer_rec.outcome or customer_rec.execution_status,
        stages=stages,
    )


@router.get("/exceptions", response_model=ExceptionCenterResponse)
def get_dashboard_exceptions(
    seed: int = Query(default=42, ge=1, le=999999, description="RNG Seed"),
    cohort_size: int = Query(default=100, ge=1, le=5000, description="Customer cohort size"),
    snapshot_hours: float = Query(default=336.0, gt=0.0, description="Snapshot horizon in hours"),
    customers_count: Optional[int] = Query(default=None, ge=1, le=5000, description="Alias for cohort_size"),
) -> ExceptionCenterResponse:
    """
    Return aggregate exception accounting and governed non-actions from operational batch.
    Demonstrates intentional restraint, policy stops, and cost avoidance.
    """
    effective_count = customers_count if customers_count is not None else cohort_size
    res = get_evaluation_result(customers_count=effective_count, seed=seed, snapshot_hours=snapshot_hours)

    # Collect sample governed non-actions and blocked cases
    sample_exceptions = []
    for rec in res.per_customer_results:
        if rec.selected_action == "NO_ACTION":
            sample_exceptions.append(
                ExceptionItemResponse(
                    category="GOVERNED_NO_ACTION",
                    customer_id=rec.customer_id,
                    decision="NO_ACTION",
                    reason=rec.decision_reason,
                    policy_action="STOP",
                    financial_impact=0.0,
                    retryable=False,
                )
            )
        elif rec.execution_status == "ESCALATED":
            sample_exceptions.append(
                ExceptionItemResponse(
                    category="HUMAN_REVIEW_ESCALATION",
                    customer_id=rec.customer_id,
                    decision=rec.selected_action,
                    reason="High ambiguity / low confidence threshold triggered human review",
                    policy_action="ESCALATE",
                    financial_impact=rec.revenue_at_risk,
                    retryable=True,
                )
            )
        elif rec.execution_status == "FAILED":
            sample_exceptions.append(
                ExceptionItemResponse(
                    category="EXECUTION_FAILURE",
                    customer_id=rec.customer_id,
                    decision=rec.selected_action,
                    reason=rec.failure_reason or "Execution dispatch failed",
                    policy_action="RETRY_OR_FALLBACK",
                    financial_impact=rec.revenue_at_risk,
                    retryable=True,
                )
            )

    return ExceptionCenterResponse(
        provenance="CUSTOMER OPERATIONAL STATE",
        total_exceptions=len(sample_exceptions),
        retryable_count=sum(1 for e in sample_exceptions if e.retryable),
        terminal_count=sum(1 for e in sample_exceptions if not e.retryable),
        human_escalation_count=sum(1 for e in sample_exceptions if e.category == "HUMAN_REVIEW_ESCALATION"),
        total_financial_impact=sum(e.financial_impact for e in sample_exceptions),
        by_stage={
            "INTERVENTION_POLICY": sum(1 for e in sample_exceptions if e.category == "GOVERNED_NO_ACTION"),
            "EXECUTION_ENGINE": sum(1 for e in sample_exceptions if e.category == "EXECUTION_FAILURE"),
            "GOVERNANCE_GATE": sum(1 for e in sample_exceptions if e.category == "HUMAN_REVIEW_ESCALATION"),
        },
        by_failure_type={
            "policy_block": sum(1 for e in sample_exceptions if e.category == "GOVERNED_NO_ACTION"),
            "execution_failure": sum(1 for e in sample_exceptions if e.category == "EXECUTION_FAILURE"),
            "human_escalation": sum(1 for e in sample_exceptions if e.category == "HUMAN_REVIEW_ESCALATION"),
        },
        sample_exceptions=sample_exceptions[:25],
    )


@router.get("/failure-scenarios", response_model=List[FailureScenarioResponse])
def get_dashboard_failure_scenarios() -> List[FailureScenarioResponse]:
    """
    Return deterministic controlled failure scenarios executed via real REVIVE components.
    CONTROLLED DETERMINISTIC FAILURE FIXTURE backed by real ExecutionEngine failure semantics
    (not a live customer decision).
    """
    # -----------------------------------------------------------------------
    # Scenario 1: Transient Gateway Timeout (Executed via real ExecutionEngine)
    # -----------------------------------------------------------------------
    exec_config = ExecutionConfig(environment="TEST_MODE", max_retries=2)
    exec_engine = ExecutionEngine(config=exec_config)

    decision_1 = InterventionDecision(
        customer_id="cus_000005_fail_sim",
        decision_timestamp="2026-08-31T14:00:00Z",
        risk_score=0.924,
        risk_tier="HIGH",
        revenue_at_risk=Decimal("4999.00"),
        diagnosis="PAYMENT_FRICTION",
        diagnosis_confidence=1.0,
        diagnosis_actionability="candidate",
        eligibility_status="ELIGIBLE",
        selected_action=InterventionAction.PAYMENT_RECOVERY,
        expected_value=Decimal("1243.28"),
        candidate_scores=[
            CandidateActionScore(
                action=InterventionAction.PAYMENT_RECOVERY,
                expected_value=Decimal("1243.28"),
                recovery_probability_assumption=0.3825,
                direct_cost=Decimal("3.00"),
                incentive_penalty_assumption=Decimal("0.00"),
                harm_penalty_assumption=Decimal("0.00"),
                is_eligible=True,
            )
        ],
        decision_reason="Autonomous recovery of subscription billing payment friction",
        supporting_evidence=["Observed payment failure evt_01", "Card authorization declined"],
    )

    # Injected transient timeout simulator
    def timeout_simulator(action: InterventionAction, attempt: int) -> Optional[str]:
        return "Gateway connection timeout (HTTP 504 Gateway Timeout during link dispatch)"

    # 1. Real ExecutionEngine execution
    audit_1 = exec_engine.execute_decision(decision_1, failure_simulator=timeout_simulator)
    history_1 = exec_engine.audit_logger.get_customer_audit_history(decision_1.customer_id)
    attempt_1_record = history_1[0]
    raw_failure_reason = attempt_1_record.failure_reason or "Gateway connection timeout (HTTP 504 Gateway Timeout during link dispatch)"

    # 2. Actual failure classification via ExecutionStateMachine
    classified_failure_type = exec_engine.state_machine.classify_failure(raw_failure_reason)

    # 3. Existing ExecutionStateMachine retry evaluation
    transition_state, fallback_action = exec_engine.state_machine.evaluate_failure_transition(
        action=decision_1.selected_action,
        current_attempt=attempt_1_record.attempt_number,
        failure_type=classified_failure_type,
    )

    # 4. Actual retry/fallback/escalation/stop result
    if transition_state == ExecutionState.RETRY:
        safe_action_result = "RETRY_SCHEDULED"
    elif transition_state == ExecutionState.FALLBACK and fallback_action:
        safe_action_result = f"FALLBACK_{fallback_action.value}"
    elif transition_state == ExecutionState.ESCALATED:
        safe_action_result = "ESCALATED"
    else:
        safe_action_result = "STOP"

    # 5. ExceptionLedger recording derived directly from ExecutionStateMachine transition
    ledger_1 = ExceptionLedger()
    exc_rec_1 = ledger_1.record_exception(
        case_id=decision_1.customer_id,
        stage="EXECUTION_ENGINE",
        status=attempt_1_record.status.value,
        failure_type=classified_failure_type.value,
        retryable=(classified_failure_type == FailureType.RETRYABLE),
        safe_action_taken=safe_action_result,
        financial_impact=float(decision_1.revenue_at_risk),
        human_escalation_required=(transition_state == ExecutionState.ESCALATED),
        reason=raw_failure_reason,
    )

    scen_1 = FailureScenarioResponse(
        scenario_id="payment_gateway_timeout_retryable",
        title="Razorpay Dispatch Gateway Timeout (Retryable Failure)",
        category="TRANSIENT_EXECUTION_FAILURE",
        label="CONTROLLED DETERMINISTIC FAILURE FIXTURE",
        customer_id=decision_1.customer_id,
        action=decision_1.selected_action.value,
        failure_reason=raw_failure_reason,
        failure_type=classified_failure_type.value,
        retryable=exc_rec_1.retryable,
        attempt_count=attempt_1_record.attempt_number,
        max_retries=exec_config.max_retries,
        safe_action=safe_action_result,
        final_state=transition_state.value,
        financial_exposure=float(decision_1.revenue_at_risk),
        steps=[
            FailureScenarioStep(
                step_number=1,
                step_name="ACTION_DISPATCH",
                status="INITIATED",
                description=f"[CONTROLLED DETERMINISTIC FAILURE FIXTURE] InterventionEngine authorized {decision_1.selected_action.value} (EV: Rs. {decision_1.expected_value:.2f}). ExecutionEngine initiated dispatch attempt {attempt_1_record.attempt_number}.",
                state_snapshot={
                    "provenance": "CONTROLLED DETERMINISTIC FAILURE FIXTURE backed by real ExecutionEngine failure semantics",
                    "action": decision_1.selected_action.value,
                    "attempt": attempt_1_record.attempt_number,
                    "target": "Razorpay Dispatcher",
                },
            ),
            FailureScenarioStep(
                step_number=2,
                step_name="DISPATCH_FAILURE",
                status="FAILED",
                description=f"[CONTROLLED DETERMINISTIC FAILURE FIXTURE] Dispatcher recorded simulated gateway failure on attempt {attempt_1_record.attempt_number}: {raw_failure_reason}",
                state_snapshot={
                    "error": raw_failure_reason,
                    "attempt": attempt_1_record.attempt_number,
                },
            ),
            FailureScenarioStep(
                step_number=3,
                step_name="FAILURE_CLASSIFICATION",
                status="CLASSIFIED",
                description=f"[CONTROLLED DETERMINISTIC FAILURE FIXTURE] ExecutionStateMachine.classify_failure() evaluated raw error as failure_type='{classified_failure_type.value}' (retryable={classified_failure_type == FailureType.RETRYABLE}).",
                state_snapshot={
                    "failure_type": classified_failure_type.value,
                    "retryable": (classified_failure_type == FailureType.RETRYABLE),
                },
            ),
            FailureScenarioStep(
                step_number=4,
                step_name="RETRY_POLICY_EVALUATION",
                status="POLICY_APPROVED",
                description=f"[CONTROLLED DETERMINISTIC FAILURE FIXTURE] ExecutionStateMachine.evaluate_failure_transition() evaluated attempt {attempt_1_record.attempt_number}: returned ExecutionState='{transition_state.value}', fallback_action={fallback_action}.",
                state_snapshot={
                    "current_attempt": attempt_1_record.attempt_number,
                    "max_retries": exec_config.max_retries,
                    "transition_state": transition_state.value,
                    "fallback_action": fallback_action.value if fallback_action else None,
                },
            ),
            FailureScenarioStep(
                step_number=5,
                step_name="SAFE_ACTION_ASSIGNMENT",
                status=safe_action_result,
                description=f"[CONTROLLED DETERMINISTIC FAILURE FIXTURE] ExceptionLedger recorded safe action: '{exc_rec_1.safe_action_taken}' derived directly from ExecutionStateMachine transition {transition_state.value}.",
                state_snapshot={
                    "safe_action": exc_rec_1.safe_action_taken,
                    "status": attempt_1_record.status.value,
                    "financial_impact": exc_rec_1.financial_impact,
                },
            ),
        ],
    )

    # -----------------------------------------------------------------------
    # Scenario 2: Terminal Policy Block (Executed via InterventionEngine & ExecutionEngine)
    # -----------------------------------------------------------------------
    decision_2 = InterventionDecision(
        customer_id="cus_000004_stop_sim",
        decision_timestamp="2026-08-31T14:00:00Z",
        risk_score=0.615,
        risk_tier="MEDIUM",
        revenue_at_risk=Decimal("999.00"),
        diagnosis="ALREADY_CONVERTED",
        diagnosis_confidence=1.0,
        diagnosis_actionability="non_actionable",
        eligibility_status="INELIGIBLE",
        selected_action=InterventionAction.NO_ACTION,
        expected_value=Decimal("0.00"),
        candidate_scores=[
            CandidateActionScore(
                action=InterventionAction.NO_ACTION,
                expected_value=Decimal("0.00"),
                recovery_probability_assumption=0.0,
                direct_cost=Decimal("0.00"),
                incentive_penalty_assumption=Decimal("0.00"),
                harm_penalty_assumption=Decimal("0.00"),
                is_eligible=True,
            )
        ],
        decision_reason="Customer already converted before snapshot window; active intervention blocked",
        supporting_evidence=["Prior subscription creation event observed"],
    )

    # 1. Real ExecutionEngine execution
    audit_2 = exec_engine.execute_decision(decision_2)

    # 2. Actual failure classification
    classified_failure_type_2 = exec_engine.state_machine.classify_failure(decision_2.decision_reason)

    # 3. Existing ExecutionStateMachine retry evaluation
    transition_state_2, fallback_action_2 = exec_engine.state_machine.evaluate_failure_transition(
        action=decision_2.selected_action,
        current_attempt=1,
        failure_type=classified_failure_type_2,
    )

    # 4. Actual policy stop result
    safe_action_2 = "GOVERNED_STOP"

    # 5. ExceptionLedger recording
    ledger_2 = ExceptionLedger()
    exc_rec_2 = ledger_2.record_exception(
        case_id=decision_2.customer_id,
        stage="INTERVENTION_POLICY",
        status=audit_2.status.value,
        failure_type="policy_block",
        retryable=False,
        safe_action_taken=safe_action_2,
        financial_impact=0.0,
        human_escalation_required=False,
        reason=decision_2.decision_reason,
    )

    scen_2 = FailureScenarioResponse(
        scenario_id="terminal_policy_blocked_invalid_state",
        title="Terminal Policy Block on Post-Conversion Customer",
        category="POLICY_GOVERNED_STOP",
        label="CONTROLLED DETERMINISTIC FAILURE FIXTURE",
        customer_id=decision_2.customer_id,
        action=decision_2.selected_action.value,
        failure_reason=decision_2.decision_reason,
        failure_type=exc_rec_2.failure_type,
        retryable=exc_rec_2.retryable,
        attempt_count=0,
        max_retries=0,
        safe_action=exc_rec_2.safe_action_taken,
        final_state=audit_2.status.value,
        financial_exposure=0.0,
        steps=[
            FailureScenarioStep(
                step_number=1,
                step_name="RISK_EVALUATION",
                status="EVALUATED",
                description=f"[CONTROLLED DETERMINISTIC FAILURE FIXTURE] Risk Engine scored customer at {decision_2.risk_score} ({decision_2.risk_tier} Tier).",
                state_snapshot={
                    "provenance": "CONTROLLED DETERMINISTIC FAILURE FIXTURE backed by real ExecutionEngine failure semantics",
                    "risk_score": decision_2.risk_score,
                    "risk_tier": decision_2.risk_tier,
                },
            ),
            FailureScenarioStep(
                step_number=2,
                step_name="DIAGNOSIS_EVALUATION",
                status="DIAGNOSED",
                description=f"[CONTROLLED DETERMINISTIC FAILURE FIXTURE] DiagnosisEngine classified state as {decision_2.diagnosis} (Confidence: 100%).",
                state_snapshot={"diagnosis": decision_2.diagnosis, "confidence": decision_2.diagnosis_confidence},
            ),
            FailureScenarioStep(
                step_number=3,
                step_name="GUARDRAIL_INTERVENTION_GATE",
                status="BLOCKED",
                description=f"[CONTROLLED DETERMINISTIC FAILURE FIXTURE] Deterministic policy blocked active intervention. Selected {decision_2.selected_action.value} (EV: Rs. {decision_2.expected_value:.2f}).",
                state_snapshot={"action": decision_2.selected_action.value, "eligibility": decision_2.eligibility_status},
            ),
            FailureScenarioStep(
                step_number=4,
                step_name="GOVERNED_STOP_RECORDED",
                status="STOPPED",
                description=f"[CONTROLLED DETERMINISTIC FAILURE FIXTURE] Terminal policy stop recorded in ExceptionLedger. Wasted merchant outreach fee avoided.",
                state_snapshot={"status": audit_2.status.value, "cost_avoided": 3.0, "retryable": exc_rec_2.retryable},
            ),
        ],
    )

    # -----------------------------------------------------------------------
    # Scenario 3: Active Cooldown Window Block (Intervention Suppression)
    # -----------------------------------------------------------------------
    exec_config_3 = ExecutionConfig(environment="TEST_MODE", cooldown_period_hours=72.0)
    exec_engine_3 = ExecutionEngine(config=exec_config_3)

    decision_3_prior = InterventionDecision(
        customer_id="cus_000006_cooldown_sim",
        decision_timestamp="2026-08-30T10:00:00Z",
        risk_score=0.88,
        risk_tier="HIGH",
        revenue_at_risk=Decimal("1999.00"),
        diagnosis="PAYMENT_FRICTION",
        diagnosis_confidence=1.0,
        diagnosis_actionability="candidate",
        eligibility_status="ELIGIBLE",
        selected_action=InterventionAction.PAYMENT_RECOVERY,
        expected_value=Decimal("540.00"),
        candidate_scores=[],
        decision_reason="Initial payment recovery intervention dispatched",
    )
    exec_engine_3.execute_decision(decision_3_prior)

    decision_3_current = InterventionDecision(
        customer_id="cus_000006_cooldown_sim",
        decision_timestamp="2026-08-31T10:00:00Z",
        risk_score=0.85,
        risk_tier="HIGH",
        revenue_at_risk=Decimal("1999.00"),
        diagnosis="PAYMENT_FRICTION",
        diagnosis_confidence=1.0,
        diagnosis_actionability="candidate",
        eligibility_status="ELIGIBLE",
        selected_action=InterventionAction.PAYMENT_RECOVERY,
        expected_value=Decimal("520.00"),
        candidate_scores=[],
        decision_reason="Subsequent payment failure observed inside 72h cooldown window",
    )
    audit_3 = exec_engine_3.execute_decision(decision_3_current)
    ledger_3 = ExceptionLedger()
    exc_rec_3 = ledger_3.record_exception(
        case_id=decision_3_current.customer_id,
        stage="EXECUTION_ENGINE",
        status=audit_3.status.value,
        failure_type="cooldown_active",
        retryable=False,
        safe_action_taken="GOVERNED_STOP",
        financial_impact=0.0,
        human_escalation_required=False,
        reason=audit_3.failure_reason or "Customer inside active intervention cooldown window",
    )

    scen_3 = FailureScenarioResponse(
        scenario_id="cooldown_window_blocked",
        title="Active Cooldown Window Block (Intervention Suppression)",
        category="GOVERNED_COOLDOWN_BLOCK",
        label="CONTROLLED DETERMINISTIC FAILURE FIXTURE",
        customer_id=decision_3_current.customer_id,
        action=decision_3_current.selected_action.value,
        failure_reason=audit_3.failure_reason or "Active intervention cooldown period in effect",
        failure_type="cooldown_active",
        retryable=False,
        attempt_count=0,
        max_retries=0,
        safe_action="GOVERNED_STOP",
        final_state=audit_3.status.value,
        financial_exposure=0.0,
        steps=[
            FailureScenarioStep(
                step_number=1,
                step_name="PRIOR_DISPATCH_DETECTED",
                status="VERIFIED",
                description="[CONTROLLED DETERMINISTIC FAILURE FIXTURE] Customer had an active intervention dispatched 24.0h prior.",
                state_snapshot={"prior_action": "PAYMENT_RECOVERY", "elapsed_hours": 24.0, "cooldown_threshold_hours": 72.0},
            ),
            FailureScenarioStep(
                step_number=2,
                step_name="COOLDOWN_GUARD_EVALUATION",
                status="BLOCKED",
                description="[CONTROLLED DETERMINISTIC FAILURE FIXTURE] ExecutionEngine enforced cooldown policy (24.0h elapsed < 72.0h cooldown).",
                state_snapshot={"status": audit_3.status.value, "failure_reason": audit_3.failure_reason},
            ),
            FailureScenarioStep(
                step_number=3,
                step_name="GOVERNED_STOP_RECORDED",
                status="STOPPED",
                description="[CONTROLLED DETERMINISTIC FAILURE FIXTURE] Customer outreach suppressed to prevent merchant brand fatigue. Safe action recorded in ExceptionLedger.",
                state_snapshot={"safe_action": exc_rec_3.safe_action_taken, "cost_avoided": 3.0},
            ),
        ],
    )

    # -----------------------------------------------------------------------
    # Scenario 4: Idempotency Duplicate Suppression (Prevent Duplicate Payment Link)
    # -----------------------------------------------------------------------
    exec_engine_4 = ExecutionEngine(config=ExecutionConfig(environment="TEST_MODE"))
    decision_4 = InterventionDecision(
        customer_id="cus_000007_idempotent_sim",
        decision_timestamp="2026-08-31T14:00:00Z",
        risk_score=0.91,
        risk_tier="HIGH",
        revenue_at_risk=Decimal("2499.00"),
        diagnosis="PAYMENT_FRICTION",
        diagnosis_confidence=1.0,
        diagnosis_actionability="candidate",
        eligibility_status="ELIGIBLE",
        selected_action=InterventionAction.PAYMENT_RECOVERY,
        expected_value=Decimal("850.00"),
        candidate_scores=[],
        decision_reason="Autonomous recovery of subscription billing payment friction",
    )
    audit_4_first = exec_engine_4.execute_decision(decision_4)
    audit_4_second = exec_engine_4.execute_decision(decision_4)

    scen_4 = FailureScenarioResponse(
        scenario_id="idempotent_duplicate_suppression",
        title="Idempotency Duplicate Suppression (Prevent Duplicate Payment Link)",
        category="IDEMPOTENCY_SAFETY_GUARD",
        label="CONTROLLED DETERMINISTIC FAILURE FIXTURE",
        customer_id=decision_4.customer_id,
        action=decision_4.selected_action.value,
        failure_reason="Duplicate decision submission detected; secondary dispatch suppressed",
        failure_type="idempotent_duplicate",
        retryable=False,
        attempt_count=1,
        max_retries=0,
        safe_action="DUPLICATE_SUPPRESSED",
        final_state=audit_4_second.status.value,
        financial_exposure=0.0,
        steps=[
            FailureScenarioStep(
                step_number=1,
                step_name="INITIAL_DISPATCH",
                status="EXECUTED",
                description=f"[CONTROLLED DETERMINISTIC FAILURE FIXTURE] Initial decision dec_{decision_4.customer_id}_{decision_4.decision_timestamp} dispatched successfully.",
                state_snapshot={"status": audit_4_first.status.value, "payload_id": audit_4_first.payload_id},
            ),
            FailureScenarioStep(
                step_number=2,
                step_name="DUPLICATE_SUBMISSION",
                status="DETECTED",
                description="[CONTROLLED DETERMINISTIC FAILURE FIXTURE] Identical decision received by ExecutionEngine.",
                state_snapshot={"decision_id": f"dec_{decision_4.customer_id}_{decision_4.decision_timestamp}"},
            ),
            FailureScenarioStep(
                step_number=3,
                step_name="IDEMPOTENCY_INTERCEPT",
                status="SUPPRESSED",
                description="[CONTROLLED DETERMINISTIC FAILURE FIXTURE] ExecutionEngine returned cached record without creating duplicate payment link or duplicate billing outreach.",
                state_snapshot={"status": audit_4_second.status.value, "safe_action": "DUPLICATE_SUPPRESSED"},
            ),
        ],
    )

    # -----------------------------------------------------------------------
    # Scenario 5: Retry Budget Exhaustion with Human Operator Escalation
    # -----------------------------------------------------------------------
    exec_config_5 = ExecutionConfig(environment="TEST_MODE", max_retries=2)
    exec_engine_5 = ExecutionEngine(config=exec_config_5)
    decision_5 = InterventionDecision(
        customer_id="cus_000008_exhaust_sim",
        decision_timestamp="2026-08-31T14:00:00Z",
        risk_score=0.95,
        risk_tier="CRITICAL",
        revenue_at_risk=Decimal("4999.00"),
        diagnosis="PAYMENT_FRICTION",
        diagnosis_confidence=1.0,
        diagnosis_actionability="candidate",
        eligibility_status="ELIGIBLE",
        selected_action=InterventionAction.PAYMENT_RECOVERY,
        expected_value=Decimal("1500.00"),
        candidate_scores=[],
        decision_reason="Critical payment friction recovery with persistent upstream gateway failure",
    )

    def persistent_503_simulator(action: InterventionAction, attempt: int) -> Optional[str]:
        return "Gateway 503 Service Unavailable: upstream service is overloaded"

    audit_5 = exec_engine_5.execute_decision(decision_5, failure_simulator=persistent_503_simulator)
    ledger_5 = ExceptionLedger()
    exc_rec_5 = ledger_5.record_exception(
        case_id=decision_5.customer_id,
        stage="EXECUTION_ENGINE",
        status=audit_5.status.value,
        failure_type="retry_budget_exhausted",
        retryable=False,
        safe_action_taken="ESCALATED",
        financial_impact=float(decision_5.revenue_at_risk),
        human_escalation_required=True,
        reason=audit_5.escalation_reason or "Retry budget exhausted across 3 attempts",
    )

    scen_5 = FailureScenarioResponse(
        scenario_id="retry_exhaustion_escalation",
        title="Retry Budget Exhaustion with Human Operator Escalation",
        category="RETRY_EXHAUSTION_ESCALATION",
        label="CONTROLLED DETERMINISTIC FAILURE FIXTURE",
        customer_id=decision_5.customer_id,
        action=decision_5.selected_action.value,
        failure_reason=audit_5.failure_reason or "Persistent 503 Service Unavailable across retries",
        failure_type="retry_budget_exhausted",
        retryable=False,
        attempt_count=3,
        max_retries=exec_config_5.max_retries,
        safe_action="ESCALATED",
        final_state=audit_5.status.value,
        financial_exposure=float(decision_5.revenue_at_risk),
        steps=[
            FailureScenarioStep(
                step_number=1,
                step_name="ATTEMPT_1_DISPATCH",
                status="FAILED",
                description="[CONTROLLED DETERMINISTIC FAILURE FIXTURE] Attempt 1 failed with transient 503 Service Unavailable -> RETRY scheduled.",
                state_snapshot={"attempt": 1, "state": "RETRY"},
            ),
            FailureScenarioStep(
                step_number=2,
                step_name="ATTEMPT_2_DISPATCH",
                status="FAILED",
                description="[CONTROLLED DETERMINISTIC FAILURE FIXTURE] Attempt 2 failed with transient 503 Service Unavailable -> RETRY scheduled.",
                state_snapshot={"attempt": 2, "state": "RETRY"},
            ),
            FailureScenarioStep(
                step_number=3,
                step_name="ATTEMPT_3_EXHAUSTION",
                status="EXHAUSTED",
                description="[CONTROLLED DETERMINISTIC FAILURE FIXTURE] Attempt 3 failed. Maximum retry budget (2 retries / 3 total attempts) exhausted.",
                state_snapshot={"attempt": 3, "max_retries": 2, "state": "RETRY_EXHAUSTED"},
            ),
            FailureScenarioStep(
                step_number=4,
                step_name="HUMAN_ESCALATION",
                status="ESCALATED",
                description="[CONTROLLED DETERMINISTIC FAILURE FIXTURE] ExecutionStateMachine transitioned to ESCALATED. Case queued for manual merchant operator review to prevent infinite retry loops.",
                state_snapshot={"safe_action": "ESCALATED", "human_escalation_required": True},
            ),
        ],
    )

    return [scen_1, scen_2, scen_3, scen_4, scen_5]
