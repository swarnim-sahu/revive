"""
Deterministic Automated Test Suite for REVIVE Phase D:
Real Gemini Evaluation, Structured Output Validation, Governance Containment, and Evidence Contracts.
"""

from decimal import Decimal
import json
import os
from pathlib import Path
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.api.main import app
from app.diagnosis.schemas import Actionability, ConfidenceTier, CustomerDiagnosis, DiagnosisCategory
from app.evaluation.gemini_provider import (
    PROMPT_VERSION,
    EVIDENCE_VERSION,
    GeminiDiagnosisEvaluator,
    GeminiOutputValidator,
    build_gemini_diagnosis_prompt,
)
from app.evaluation.phase_d_schemas import (
    CANONICAL_OBSERVABLE_PRECEDENCE,
    CANONICAL_PRECEDENCE_CATEGORIES,
    GeminiCallResult,
    GeminiModelCallStatus,
    PhaseDEvidenceRecord,
    PhaseDEvaluationRecord,
    PhaseDEvaluationArtifact,
    PhaseDRoutingDecision,
    PhaseDDemonstrationCase,
    ReviewMode,
)
from app.evaluation.phase_d_gemini import (
    PhaseDEvaluator,
    extract_observable_evidence,
    derive_observable_expected_diagnosis,
    run_and_save_evaluation,
    route_customer_evidence,
    select_primary_demonstration_case,
    generate_synthetic_observable_cohort,
    run_demonstration,
    format_cli_summary,
    _DEFAULT_DEMO_PATH,
    TRIGGER_DET_CONVERSION,
    TRIGGER_DET_PAYMENT_FAILURE,
    TRIGGER_DET_CHECKOUT_ABANDONMENT,
    TRIGGER_DET_LOW_RISK,
    TRIGGER_DET_ENGAGEMENT_DECLINE,
    TRIGGER_DET_TRIAL_EXPIRATION,
    TRIGGER_DET_LOW_INTENT,
    TRIGGER_DET_INSUFFICIENT_EVIDENCE,
    TRIGGER_AI_COMMERCIAL_INTENT_DIVERGENCE,
    TRIGGER_AI_DISPARATE_ENGAGEMENT,
    TRIGGER_AI_INDETERMINATE_SIGNALS,
)
from app.execution.engine import ExecutionEngine
from app.intervention.engine import InterventionEngine
from app.intervention.schemas import InterventionAction, InterventionDecision
from app.models.entities import Customer, Plan
from app.models.events import BaseEvent
from app.risk.features import CustomerFeatureExtractor
from app.risk.model import ReviveRiskModel
from app.risk.scoring import RiskScorer, ScoredCustomer
from app.diagnosis.engine import DiagnosisEngine




@pytest.fixture
def sample_evidence_record() -> PhaseDEvidenceRecord:
    """Deterministic sample observable evidence record."""
    return PhaseDEvidenceRecord(
        evidence_version=EVIDENCE_VERSION,
        customer_id="cus_000042",
        plan_name="Growth Plan",
        plan_price_inr=999.0,
        billing_cycle="month",
        risk_score=0.75,
        risk_tier="HIGH",
        revenue_at_risk=999.0,
        hours_until_trial_expiry=12.0,
        trial_active=True,
        payment_failed_observed=True,
        checkout_abandonment_observed=False,
        days_since_last_active=1.5,
        has_prior_conversion=False,
        lifetime_event_count=5,
        lifetime_session_count=2,
        lifetime_feature_use_count=3,
        lifetime_pricing_view_count=1,
        lifetime_checkout_start_count=1,
        lifetime_payment_attempt_count=1,
        lifetime_payment_success_count=0,
        lifetime_payment_failure_count=1,
        recent_observable_events=[
            {
                "event_type": "payment_failed",
                "timestamp": "2026-01-14T10:00:00+00:00",
                "payload": {"error_code": "INSUFFICIENT_FUNDS"},
            }
        ],
        observable_evidence_descriptions=[
            "Observed payment failure event.",
            "Trial expires within 12.0 hours.",
        ],
    )



# ===========================================================================
# 1. PROVIDER BOUNDARY TESTS
# ===========================================================================

def test_phase_d_provider_missing_api_key(sample_evidence_record):
    """When GEMINI_API_KEY is not provided, evaluator returns explicit MODEL_UNAVAILABLE state."""
    evaluator = GeminiDiagnosisEvaluator(api_key=None)
    assert not evaluator.is_available()

    result = evaluator.evaluate(sample_evidence_record)
    assert result.status == GeminiModelCallStatus.MODEL_UNAVAILABLE
    assert result.error_type == "CREDENTIALS_UNAVAILABLE"
    assert "GEMINI_API_KEY" in result.error_message


def test_phase_d_provider_timeout_wired_into_sdk_call(sample_evidence_record):
    """Proves that configured timeout_seconds is converted to milliseconds and wired into Google GenAI SDK request."""
    evaluator = GeminiDiagnosisEvaluator(api_key="mock_test_key", timeout_seconds=12.5)
    evaluator._sdk_available = True
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "diagnosis": "PAYMENT_FRICTION",
        "confidence": 0.90,
        "actionability": "CANDIDATE",
        "rationale": "Valid grounded diagnosis",
        "evidence_used": [],
    })
    mock_response.usage_metadata = None
    mock_client.models.generate_content.return_value = mock_response
    evaluator._genai_client = mock_client

    result = evaluator.evaluate(sample_evidence_record)
    assert result.status == GeminiModelCallStatus.REAL_GEMINI

    # Inspect call args to verify config.http_options.timeout == 12500 ms
    mock_client.models.generate_content.assert_called_once()
    _, kwargs = mock_client.models.generate_content.call_args
    config = kwargs.get("config")
    assert config is not None
    assert config.http_options is not None
    assert config.http_options.timeout == 12500  # 12.5s -> 12500ms


def test_phase_d_provider_timeout_classification(sample_evidence_record):
    """Timeout during Gemini call (both Python TimeoutError and HTTP transport timeout) is classified as MODEL_ERROR with TIMEOUT type."""
    import httpx

    # 1. Native TimeoutError with retry exhaustion
    evaluator = GeminiDiagnosisEvaluator(
        api_key="mock_test_key",
        timeout_seconds=5.0,
        max_retries=1,
        initial_backoff_seconds=0.001,
        pacing_delay_seconds=0.0,
    )
    evaluator._sdk_available = True
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = TimeoutError("Request timed out after 5.0s")
    evaluator._genai_client = mock_client

    result = evaluator.evaluate(sample_evidence_record)
    assert result.status == GeminiModelCallStatus.MODEL_ERROR
    assert result.error_type == "TIMEOUT"
    assert result.retries_attempted == 1
    assert mock_client.models.generate_content.call_count == 2

    # 2. HTTP transport timeout (httpx.ReadTimeout)
    mock_client.reset_mock()
    mock_client.models.generate_content.side_effect = httpx.ReadTimeout("The read operation timed out")
    result_http = evaluator.evaluate(sample_evidence_record)
    assert result_http.status == GeminiModelCallStatus.MODEL_ERROR
    assert result_http.error_type == "TIMEOUT"
    assert result_http.retries_attempted == 1
    assert mock_client.models.generate_content.call_count == 2


def test_phase_d_provider_rate_limit_classification(sample_evidence_record):
    """429 or quota exhaustion is classified as MODEL_ERROR with RATE_LIMITED type."""
    evaluator = GeminiDiagnosisEvaluator(
        api_key="mock_test_key",
        max_retries=1,
        initial_backoff_seconds=0.001,
        pacing_delay_seconds=0.0,
    )
    evaluator._sdk_available = True
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = Exception("ResourceExhausted: 429 Rate limit exceeded")
    evaluator._genai_client = mock_client

    result = evaluator.evaluate(sample_evidence_record)
    assert result.status == GeminiModelCallStatus.MODEL_ERROR
    assert result.error_type == "RATE_LIMITED"
    assert result.retries_attempted == 1
    assert mock_client.models.generate_content.call_count == 2


# ===========================================================================
# 2. OUTPUT VALIDATION TESTS
# ===========================================================================

def test_phase_d_output_validator_valid_payload(sample_evidence_record):
    """Strictly valid JSON diagnosis matching DiagnosisCategory succeeds validation."""
    valid_json = json.dumps({
        "diagnosis": "PAYMENT_FRICTION",
        "confidence": 0.88,
        "actionability": "CANDIDATE",
        "rationale": "Customer experienced insufficient funds failure during trial checkout.",
        "evidence_used": ["Observed payment failure event."],
        "uncertainty_reasons": []
    })

    is_valid, structured, err, unsupp, bypass, viol = GeminiOutputValidator.validate(
        valid_json, sample_evidence_record
    )
    assert is_valid is True
    assert structured is not None
    assert structured.diagnosis == DiagnosisCategory.PAYMENT_FRICTION
    assert structured.confidence == 0.88
    assert structured.actionability == Actionability.CANDIDATE
    assert err is None
    assert unsupp is False
    assert bypass is False
    assert viol is False


def test_phase_d_output_validator_invalid_category(sample_evidence_record):
    """Diagnosis category outside the 9 authoritative categories is rejected."""
    invalid_json = json.dumps({
        "diagnosis": "UNAUTHORIZED_CHURN_REASON",
        "confidence": 0.90,
        "actionability": "CANDIDATE",
        "rationale": "Reason not in taxonomy",
        "evidence_used": []
    })

    is_valid, structured, err, unsupp, bypass, viol = GeminiOutputValidator.validate(
        invalid_json, sample_evidence_record
    )
    assert is_valid is False
    assert structured is None
    assert "Invalid diagnosis category" in err


def test_phase_d_output_validator_out_of_bounds_confidence(sample_evidence_record):
    """Confidence value > 1.0 or < 0.0 is rejected."""
    for bad_conf in [1.5, -0.2]:
        invalid_json = json.dumps({
            "diagnosis": "PAYMENT_FRICTION",
            "confidence": bad_conf,
            "actionability": "CANDIDATE",
            "rationale": "Confidence out of bounds",
            "evidence_used": []
        })
        is_valid, structured, err, _, _, _ = GeminiOutputValidator.validate(
            invalid_json, sample_evidence_record
        )
        assert is_valid is False
        assert "out of range" in err


def test_phase_d_output_validator_malformed_json(sample_evidence_record):
    """Truncated or malformed JSON is rejected without crashing."""
    malformed = '{"diagnosis": "PAYMENT_FRICTION", "confidence": '
    is_valid, structured, err, _, _, _ = GeminiOutputValidator.validate(
        malformed, sample_evidence_record
    )
    assert is_valid is False
    assert structured is None
    assert "Malformed JSON" in err


def test_phase_d_output_validator_unsupported_execution_claim(sample_evidence_record):
    """Model claiming to have dispatched payment links or executed interventions is rejected as governance violation."""
    claim_json = json.dumps({
        "diagnosis": "PAYMENT_FRICTION",
        "confidence": 0.95,
        "actionability": "CANDIDATE",
        "rationale": "I dispatched payment link to the customer and authorized retry.",
        "evidence_used": ["Observed payment failure event."],
    })

    is_valid, structured, err, unsupp, bypass, viol = GeminiOutputValidator.validate(
        claim_json, sample_evidence_record
    )
    assert is_valid is False
    assert structured is None
    assert unsupp is True
    assert bypass is True
    assert viol is True
    assert "Governance violation" in err


def test_phase_d_output_validator_unsupported_action_claim_alone(sample_evidence_record):
    """Validator detects unsupported action claim alone with bypass=False and viol=False."""
    claim_json = json.dumps({
        "diagnosis": "PAYMENT_FRICTION",
        "confidence": 0.85,
        "actionability": "CANDIDATE",
        "rationale": "Model proposed an unsupported action for merchant resolution.",
        "evidence_used": ["Observed payment failure event."],
    })
    is_valid, structured, err, unsupp, bypass, viol = GeminiOutputValidator.validate(
        claim_json, sample_evidence_record
    )
    assert is_valid is False
    assert structured is None
    assert unsupp is True
    assert bypass is False
    assert viol is False
    assert "Governance violation" in err


# ===========================================================================
# 3. EVIDENCE CONTRACT & GROUND-TRUTH ISOLATION TESTS
# ===========================================================================

def test_phase_d_evidence_hashing_is_deterministic(sample_evidence_record):
    """Evidence hash is 100% deterministic for identical payloads and changes on mutation."""
    hash_1 = sample_evidence_record.compute_hash()
    hash_2 = sample_evidence_record.compute_hash()
    assert hash_1 == hash_2
    assert len(hash_1) == 16

    # Mutate one field -> hash changes
    mutated = sample_evidence_record.model_copy(update={"hours_until_trial_expiry": 11.9})
    assert mutated.compute_hash() != hash_1


def test_phase_d_ground_truth_strictly_isolated_from_prompt(sample_evidence_record):
    """Ground truth fields and simulator labels NEVER appear in the prompt or serialized evidence."""
    prompt_text = build_gemini_diagnosis_prompt(sample_evidence_record)

    forbidden_ground_truth_terms = [
        "true_root_cause",
        "natural_conversion",
        "recoverable",
        "generation_segment",
        "conversion_after_intervention",
        "counterfactual",
    ]

    for term in forbidden_ground_truth_terms:
        assert term not in prompt_text, f"Leakage detected: '{term}' found in Gemini prompt text!"

    evidence_dict = sample_evidence_record.model_dump()
    for term in forbidden_ground_truth_terms:
        assert term not in evidence_dict, f"Leakage detected: '{term}' found in PhaseDEvidenceRecord dict!"


# ===========================================================================
# 4. GOVERNANCE & EXECUTION CONTAINMENT TESTS
# ===========================================================================

def test_phase_d_gemini_cannot_directly_execute_interventions():
    """
    Governance Proof: Gemini output is purely a diagnosis proposal.
    Even if Gemini claims high confidence, it cannot bypass ExecutionEngine or trigger execution.
    """
    mock_dispatcher = MagicMock()
    exec_engine = ExecutionEngine(dispatcher=mock_dispatcher)

    # Gemini proposed diagnosis object
    gemini_output = {
        "diagnosis": "PAYMENT_FRICTION",
        "confidence": 0.99,
        "actionability": "CANDIDATE",
        "rationale": "Direct intervention requested by AI model",
    }

    # Verify that passing gemini_output directly to ExecutionEngine raises TypeError
    with pytest.raises(Exception):
        # ExecutionEngine requires a validated InterventionDecision from Phase 5 InterventionEngine
        exec_engine.execute_decision(gemini_output)

    # Dispatcher was NEVER called
    mock_dispatcher.dispatch.assert_not_called()


def test_phase_d_gemini_diagnosis_must_pass_through_intervention_policy():
    """
    Even a validated Gemini CustomerDiagnosis must pass through InterventionEngine's
    deterministic policy gating before any action can be selected.
    """
    plan = Plan(plan_id="plan_growth", name="Growth", price=Decimal("999.00"), currency="INR", billing_interval="month")
    scored_cust = ScoredCustomer(
        customer_id="cus_000001",
        prediction_timestamp="2026-01-15T00:00:00+00:00",
        risk_score=0.10,  # Below intervention threshold
        risk_tier="LOW",
        plan_id="plan_growth",
        plan_price=Decimal("999.00"),
        revenue_at_risk=Decimal("0.00"),
    )

    # Even if an AI diagnosis proposes PAYMENT_FRICTION
    ai_diag = CustomerDiagnosis(
        customer_id="cus_000001",
        prediction_timestamp="2026-01-15T00:00:00+00:00",
        risk_score=0.10,
        risk_tier="LOW",
        diagnosis=DiagnosisCategory.PAYMENT_FRICTION,
        confidence=0.95,
        confidence_tier=ConfidenceTier.HIGH,
        actionability=Actionability.CANDIDATE,
        candidate_causes=[],
        supporting_evidence=[],
        explanation="AI candidate diagnosis",
    )

    intervention_engine = InterventionEngine()
    decision = intervention_engine.decide_intervention(
        scored_customer=scored_cust,
        diagnosis=ai_diag,
        plan=plan,
        feature_record={"days_since_last_active": 0.0}
    )

    # Deterministic policy correctly gates: Low risk -> NO_ACTION selected
    assert decision.selected_action == InterventionAction.NO_ACTION
    assert decision.eligibility_status == "INELIGIBLE"


# ===========================================================================
# 5. EVALUATION RUNNER & COUNT RECONCILIATION TESTS
# ===========================================================================

def test_phase_d_evaluation_count_reconciliation_offline():
    """
    Proves mutually exclusive accounting model:
    attempted == (successful + schema_rejected + model_errors + unavailable)
    with fallback tracked separately as a secondary mitigation metric.
    """
    evaluator = PhaseDEvaluator(sample_size=20, seed=42, enable_fallback=True)
    artifact = evaluator.run_evaluation()

    op = artifact.operational_metrics
    assert op.attempted_evaluations == 20
    assert op.reconciliation_passed is True
    assert op.attempted_evaluations == (
        op.successful_evaluations
        + op.schema_rejections
        + op.model_errors
        + op.unavailable_evaluations
    )
    # When GEMINI_API_KEY is absent, unavailable equals attempted and fallback is 100% engaged
    assert op.unavailable_evaluations == 20
    assert op.fallback_evaluations == 20


def test_phase_d_provenance_distinguished_from_phase_b():
    """
    Proves Phase D artifact is explicitly labelled as dedicated evaluation sample
    and does not claim to be the Phase B 10k benchmark.
    """
    evaluator = PhaseDEvaluator(sample_size=10, seed=42)
    artifact = evaluator.run_evaluation()

    assert "Phase D Gemini Evaluation Sample" in artifact.metadata["dataset_name"]
    assert "NOT the authoritative Phase B 10,000-pair benchmark" in artifact.metadata["note"]
    assert artifact.metadata["sample_size"] == 10


# ===========================================================================
# 6. DASHBOARD API ENDPOINT TESTS
# ===========================================================================

def test_phase_d_api_gemini_evaluation_endpoint():
    """GET /api/dashboard/gemini-evaluation returns HTTP 200 with structured response."""
    client = TestClient(app)
    response = client.get("/api/dashboard/gemini-evaluation")

    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "provenance" in data
    assert data["provenance"] == "PHASE D REAL GEMINI EVALUATION"
    assert "operational_metrics" in data
    assert data["operational_metrics"]["reconciliation_passed"] is True
    assert "governance_metrics" in data
    assert data["governance_metrics"]["execution_bypass_attempts_observed"] == 0
    assert data["governance_metrics"]["safety_compliance_rate_pct"] == 100.0


def test_phase_d_evaluation_metrics_calculation_with_simulated_model():
    """
    Verifies that when structured model responses are received, PhaseDEvaluator
    calculates honest accuracy, precision, recall, F1, and per-category breakdown
    from the actual evaluation records without fabrication.
    """
    mock_evaluator = MagicMock(spec=GeminiDiagnosisEvaluator)
    mock_evaluator.model = "gemini-2.5-flash"
    mock_evaluator.prompt_version = PROMPT_VERSION
    mock_evaluator.evidence_version = EVIDENCE_VERSION

    # Mock evaluate to return valid structured responses with token usage
    def mock_eval(evidence: PhaseDEvidenceRecord) -> GeminiCallResult:
        # Predict PAYMENT_FRICTION if payment failure observed, else TRIAL_EXPIRATION
        diag = (
            DiagnosisCategory.PAYMENT_FRICTION
            if evidence.payment_failed_observed
            else DiagnosisCategory.TRIAL_EXPIRATION
        )
        return GeminiCallResult(
            status=GeminiModelCallStatus.REAL_GEMINI,
            raw_response_text=f'{{"diagnosis": "{diag.value}", "confidence": 0.85, "actionability": "CANDIDATE", "rationale": "Grounded explanation", "evidence_used": []}}',
            parsed_json={
                "diagnosis": diag.value,
                "confidence": 0.85,
                "actionability": "CANDIDATE",
                "rationale": "Grounded explanation",
                "evidence_used": [],
            },
            latency_ms=120.5,
            prompt_tokens=250,
            candidates_tokens=45,
            total_tokens=295,
        )

    mock_evaluator.evaluate.side_effect = mock_eval

    evaluator = PhaseDEvaluator(sample_size=10, seed=42, evaluator=mock_evaluator)
    artifact = evaluator.run_evaluation()

    assert artifact.execution_state == "REAL_GEMINI"
    op = artifact.operational_metrics
    assert op.attempted_evaluations == 10
    assert op.successful_evaluations == 10
    assert op.schema_rejections == 0
    assert op.model_errors == 0
    assert op.unavailable_evaluations == 0
    assert op.reconciliation_passed is True

    # Quality metrics
    qm = artifact.quality_metrics
    assert qm.available is True
    assert 0.0 <= qm.diagnosis_accuracy <= 1.0
    assert 0.0 <= qm.macro_f1 <= 1.0
    assert len(qm.per_category_metrics) > 0

    # Cost accounting
    ca = artifact.cost_accounting
    assert ca.cost_data_status == "PROVIDER_REPORTED_USAGE"
    assert ca.prompt_tokens_sum == 2500
    assert ca.candidates_tokens_sum == 450
    assert ca.total_tokens_sum == 2950
    assert "Currency cost not fabricated" in ca.cost_basis_note


def test_phase_d_governance_safety_accounting_unsupported_claim_alone():
    """
    Proves that when unsupported_action_claim=True, execution_bypass_attempt=False,
    and policy_guard_violation=False, safety compliance is NOT reported as 100%.
    """
    mock_evaluator = MagicMock(spec=GeminiDiagnosisEvaluator)
    mock_evaluator.model = "gemini-2.5-flash"
    mock_evaluator.prompt_version = PROMPT_VERSION
    mock_evaluator.evidence_version = EVIDENCE_VERSION

    # Mock evaluate: customer 0 returns an unsupported action claim alone (bypass=False, viol=False)
    def mock_eval_with_unsupported_claim(evidence: PhaseDEvidenceRecord) -> GeminiCallResult:
        if evidence.customer_id.endswith("000001"):
            return GeminiCallResult(
                status=GeminiModelCallStatus.SCHEMA_REJECTED,
                raw_response_text=json.dumps({
                    "diagnosis": "PAYMENT_FRICTION",
                    "confidence": 0.85,
                    "actionability": "CANDIDATE",
                    "rationale": "Model proposed an unsupported action for merchant resolution.",
                    "evidence_used": [],
                }),
                parsed_json={
                    "diagnosis": "PAYMENT_FRICTION",
                    "confidence": 0.85,
                    "actionability": "CANDIDATE",
                    "rationale": "Model proposed an unsupported action for merchant resolution.",
                    "evidence_used": [],
                },
                error_type="SCHEMA_REJECTED",
                error_message="Governance violation: Model response claimed an unsupported action.",
                latency_ms=100.0,
            )
        else:
            return GeminiCallResult(
                status=GeminiModelCallStatus.REAL_GEMINI,
                raw_response_text=json.dumps({
                    "diagnosis": "PAYMENT_FRICTION",
                    "confidence": 0.90,
                    "actionability": "CANDIDATE",
                    "rationale": "Standard grounded diagnosis.",
                    "evidence_used": [],
                }),
                parsed_json={
                    "diagnosis": "PAYMENT_FRICTION",
                    "confidence": 0.90,
                    "actionability": "CANDIDATE",
                    "rationale": "Standard grounded diagnosis.",
                    "evidence_used": [],
                },
                latency_ms=100.0,
            )

    mock_evaluator.evaluate.side_effect = mock_eval_with_unsupported_claim

    evaluator = PhaseDEvaluator(sample_size=10, seed=42, evaluator=mock_evaluator)
    artifact = evaluator.run_evaluation()

    gov = artifact.governance_metrics
    assert gov.unsupported_action_claims_observed == 1
    assert gov.execution_bypass_attempts_observed == 0
    assert gov.policy_guard_violations_observed == 0

    # CRITICAL: Safety compliance MUST NOT be reported as 100%
    assert gov.safety_compliance_rate_pct == 90.0  # (10 - 1) / 10 = 90.0%
    assert gov.safety_compliance_rate_pct < 100.0
    assert gov.governance_verdict == "GOVERNANCE_VIOLATIONS_DETECTED"


def test_phase_d_governance_safety_accounting_avoids_double_counting():
    """
    Proves that when a single customer evaluation record triggers multiple violation flags
    (e.g. claiming execution simultaneously triggers unsupported_action_claim and execution_bypass_attempt),
    the accounting evaluates at the record level and does not double-count the same underlying event.
    """
    mock_evaluator = MagicMock(spec=GeminiDiagnosisEvaluator)
    mock_evaluator.model = "gemini-2.5-flash"
    mock_evaluator.prompt_version = PROMPT_VERSION
    mock_evaluator.evidence_version = EVIDENCE_VERSION

    # Mock evaluate: customer 0 triggers multiple flags on a single record
    def mock_eval_multi_flag(evidence: PhaseDEvidenceRecord) -> GeminiCallResult:
        if evidence.customer_id.endswith("000001"):
            return GeminiCallResult(
                status=GeminiModelCallStatus.SCHEMA_REJECTED,
                raw_response_text=json.dumps({
                    "diagnosis": "PAYMENT_FRICTION",
                    "confidence": 0.95,
                    "actionability": "CANDIDATE",
                    "rationale": "I dispatched payment link directly to customer.",
                    "evidence_used": [],
                }),
                parsed_json={
                    "diagnosis": "PAYMENT_FRICTION",
                    "confidence": 0.95,
                    "actionability": "CANDIDATE",
                    "rationale": "I dispatched payment link directly to customer.",
                    "evidence_used": [],
                },
                error_type="SCHEMA_REJECTED",
                error_message="Governance violation: Model claimed direct execution authority.",
                latency_ms=100.0,
            )
        else:
            return GeminiCallResult(
                status=GeminiModelCallStatus.REAL_GEMINI,
                raw_response_text=json.dumps({
                    "diagnosis": "PAYMENT_FRICTION",
                    "confidence": 0.90,
                    "actionability": "CANDIDATE",
                    "rationale": "Standard grounded diagnosis.",
                    "evidence_used": [],
                }),
                parsed_json={
                    "diagnosis": "PAYMENT_FRICTION",
                    "confidence": 0.90,
                    "actionability": "CANDIDATE",
                    "rationale": "Standard grounded diagnosis.",
                    "evidence_used": [],
                },
                latency_ms=100.0,
            )

    mock_evaluator.evaluate.side_effect = mock_eval_multi_flag

    evaluator = PhaseDEvaluator(sample_size=10, seed=42, evaluator=mock_evaluator)
    artifact = evaluator.run_evaluation()

    gov = artifact.governance_metrics
    # Individual counters report every observed flag for full visibility
    assert gov.unsupported_action_claims_observed == 1
    assert gov.execution_bypass_attempts_observed == 1
    assert gov.policy_guard_violations_observed == 1

    # But compliance counts unique non-compliant records (1 non-compliant record out of 10)
    # MUST be 90.0%, NOT 70.0%
    assert gov.safety_compliance_rate_pct == 90.0


def test_phase_d_hidden_ground_truth_absent_from_records_and_evidence():
    """
    Proves that hidden benchmark ground truth (true_root_cause, natural_conversion, recoverable,
    generation_segment, ground_truth_category) is strictly absent from schemas, records, and evidence.
    """
    # 1. PhaseDEvaluationRecord schema has zero ground_truth fields
    assert "ground_truth_category" not in PhaseDEvaluationRecord.model_fields
    assert "true_root_cause" not in PhaseDEvaluationRecord.model_fields

    # 2. PhaseDEvidenceRecord schema has zero ground_truth fields
    assert "ground_truth_category" not in PhaseDEvidenceRecord.model_fields
    assert "true_root_cause" not in PhaseDEvidenceRecord.model_fields
    assert "natural_conversion" not in PhaseDEvidenceRecord.model_fields
    assert "recoverable" not in PhaseDEvidenceRecord.model_fields
    assert "generation_segment" not in PhaseDEvidenceRecord.model_fields

    # 3. Serialized evaluation records from run_evaluation contain zero ground_truth_category
    evaluator = PhaseDEvaluator(sample_size=5, seed=42)
    artifact = evaluator.run_evaluation()
    for rec in artifact.evaluation_records:
        assert "ground_truth_category" not in rec
        assert "true_root_cause" not in rec
        assert "observable_expected_diagnosis" in rec


def test_phase_d_prompt_and_evaluator_precedence_consistency(sample_evidence_record):
    """
    Proves that CANONICAL_OBSERVABLE_PRECEDENCE contains all 9 DiagnosisCategory enum values
    and is synchronized with the generated Gemini prompt.
    """
    expected_categories = {d.value for d in DiagnosisCategory}
    precedence_categories = set(CANONICAL_PRECEDENCE_CATEGORIES)
    assert precedence_categories == expected_categories
    assert len(CANONICAL_OBSERVABLE_PRECEDENCE) == 9

    prompt_text = build_gemini_diagnosis_prompt(sample_evidence_record)
    for rule in CANONICAL_OBSERVABLE_PRECEDENCE:
        assert f'[PRECEDENCE {rule["precedence"]} - {rule["title"]}]' in prompt_text
        assert f'"{rule["category"]}"' in prompt_text


def test_phase_d_checkout_started_alone_is_not_abandonment(sample_evidence_record):
    """
    Proves that lifetime_checkout_start_count > 0 alone without checkout_abandonment_observed
    does NOT classify as CHECKOUT_ABANDONMENT.
    """
    checkout_started_ev = sample_evidence_record.model_copy(
        update={
            "has_prior_conversion": False,
            "lifetime_payment_success_count": 0,
            "payment_failed_observed": False,
            "lifetime_payment_failure_count": 0,
            "checkout_abandonment_observed": False,
            "lifetime_checkout_start_count": 2,
            "hours_until_trial_expiry": 20.0,
            "risk_score": 0.60,
        }
    )
    cat, scoreable, _ = derive_observable_expected_diagnosis(checkout_started_ev)
    assert cat != "CHECKOUT_ABANDONMENT"
    # Expires in 20 hours -> TRIAL_EXPIRATION
    assert cat == "TRIAL_EXPIRATION"
    assert scoreable is True


def test_phase_d_explicit_checkout_abandonment_derived(sample_evidence_record):
    """
    Proves that explicit checkout_abandonment_observed == True classifies as CHECKOUT_ABANDONMENT.
    """
    abandoned_ev = sample_evidence_record.model_copy(
        update={
            "has_prior_conversion": False,
            "lifetime_payment_success_count": 0,
            "payment_failed_observed": False,
            "lifetime_payment_failure_count": 0,
            "checkout_abandonment_observed": True,
            "lifetime_checkout_start_count": 1,
            "hours_until_trial_expiry": 10.0,
            "risk_score": 0.65,
        }
    )
    cat, scoreable, _ = derive_observable_expected_diagnosis(abandoned_ev)
    assert cat == "CHECKOUT_ABANDONMENT"
    assert scoreable is True


def test_phase_d_high_risk_alone_is_not_low_intent(sample_evidence_record):
    """
    Proves that risk_score >= 0.30 alone does NOT map an active customer to LOW_INTENT.
    Active mid-trial customer with unclassified signals falls through to INSUFFICIENT_EVIDENCE (unscoreable).
    """
    active_high_risk_ev = sample_evidence_record.model_copy(
        update={
            "has_prior_conversion": False,
            "lifetime_payment_success_count": 0,
            "payment_failed_observed": False,
            "lifetime_payment_failure_count": 0,
            "checkout_abandonment_observed": False,
            "lifetime_checkout_start_count": 0,
            "lifetime_session_count": 10,
            "lifetime_feature_use_count": 15,
            "lifetime_pricing_view_count": 0,
            "days_since_last_active": 1.0,
            "hours_until_trial_expiry": 100.0,
            "trial_active": True,
            "risk_score": 0.85,
        }
    )
    cat, scoreable, reason = derive_observable_expected_diagnosis(active_high_risk_ev)
    assert cat != "LOW_INTENT"
    assert cat == "INSUFFICIENT_EVIDENCE"
    assert scoreable is False
    assert reason == "Insufficient distinctive observable signals"


def test_phase_d_engagement_decline_semantics(sample_evidence_record):
    """
    Proves that prior engagement + inactivity gap >= 5.0 days classifies as ENGAGEMENT_DECLINE.
    """
    decline_ev = sample_evidence_record.model_copy(
        update={
            "has_prior_conversion": False,
            "lifetime_payment_success_count": 0,
            "payment_failed_observed": False,
            "lifetime_payment_failure_count": 0,
            "checkout_abandonment_observed": False,
            "lifetime_checkout_start_count": 0,
            "lifetime_session_count": 6,
            "lifetime_feature_use_count": 5,
            "lifetime_pricing_view_count": 1,
            "days_since_last_active": 6.5,
            "hours_until_trial_expiry": 100.0,
            "risk_score": 0.65,
        }
    )
    cat, scoreable, _ = derive_observable_expected_diagnosis(decline_ev)
    assert cat == "ENGAGEMENT_DECLINE"
    assert scoreable is True


def test_phase_d_no_meaningful_risk_threshold(sample_evidence_record):
    """
    Proves that risk_score < 0.30 with no higher-precedence friction classifies as NO_MEANINGFUL_RISK.
    """
    healthy_ev = sample_evidence_record.model_copy(
        update={
            "has_prior_conversion": False,
            "lifetime_payment_success_count": 0,
            "payment_failed_observed": False,
            "lifetime_payment_failure_count": 0,
            "checkout_abandonment_observed": False,
            "lifetime_checkout_start_count": 0,
            "lifetime_session_count": 8,
            "lifetime_feature_use_count": 12,
            "lifetime_pricing_view_count": 0,
            "days_since_last_active": 0.5,
            "hours_until_trial_expiry": 100.0,
            "risk_score": 0.15,
        }
    )
    cat, scoreable, _ = derive_observable_expected_diagnosis(healthy_ev)
    assert cat == "NO_MEANINGFUL_RISK"
    assert scoreable is True


def test_phase_d_trial_expiration_expiring_soon(sample_evidence_record):
    """
    TEST A: Expiring soon (0 < hours_until_trial_expiry <= 48h, trial_active=True,
    no payment failure, no checkout abandonment) -> TRIAL_EXPIRATION, scoreable=True.
    """
    ev = sample_evidence_record.model_copy(
        update={
            "has_prior_conversion": False,
            "lifetime_payment_success_count": 0,
            "payment_failed_observed": False,
            "lifetime_payment_failure_count": 0,
            "checkout_abandonment_observed": False,
            "lifetime_checkout_start_count": 0,
            "lifetime_session_count": 6,
            "lifetime_feature_use_count": 6,
            "lifetime_pricing_view_count": 0,
            "days_since_last_active": 1.0,
            "hours_until_trial_expiry": 24.0,
            "trial_active": True,
            "risk_score": 0.60,
        }
    )
    cat, scoreable, reason = derive_observable_expected_diagnosis(ev)
    assert cat == "TRIAL_EXPIRATION"
    assert scoreable is True
    assert reason is None


def test_phase_d_trial_expiration_expired_with_active_usage(sample_evidence_record):
    """
    TEST B: Already expired (hours_until_trial_expiry <= 0.0 or trial_active=False)
    with active product usage (sessions > 4 or features > 5), no payment failure,
    no checkout abandonment -> TRIAL_EXPIRATION, scoreable=True.
    """
    ev = sample_evidence_record.model_copy(
        update={
            "has_prior_conversion": False,
            "lifetime_payment_success_count": 0,
            "payment_failed_observed": False,
            "lifetime_payment_failure_count": 0,
            "checkout_abandonment_observed": False,
            "lifetime_checkout_start_count": 0,
            "lifetime_session_count": 8,
            "lifetime_feature_use_count": 10,
            "lifetime_pricing_view_count": 0,
            "days_since_last_active": 1.5,
            "hours_until_trial_expiry": 0.0,
            "trial_active": False,
            "risk_score": 0.60,
        }
    )
    cat, scoreable, reason = derive_observable_expected_diagnosis(ev)
    assert cat == "TRIAL_EXPIRATION"
    assert scoreable is True
    assert reason is None


def test_phase_d_trial_expiration_expired_without_active_usage_not_trial_expiration(sample_evidence_record):
    """
    TEST C: Already expired (hours_until_trial_expiry <= 0.0 or trial_active=False)
    with NO meaningful product usage (sessions <= 4 and features <= 5) -> MUST NOT classify as TRIAL_EXPIRATION.
    """
    # 1. Expired with minimal engagement -> maps to LOW_INTENT (P7)
    minimal_ev = sample_evidence_record.model_copy(
        update={
            "has_prior_conversion": False,
            "lifetime_payment_success_count": 0,
            "payment_failed_observed": False,
            "lifetime_payment_failure_count": 0,
            "checkout_abandonment_observed": False,
            "lifetime_checkout_start_count": 0,
            "lifetime_session_count": 1,
            "lifetime_feature_use_count": 1,
            "lifetime_pricing_view_count": 0,
            "days_since_last_active": 2.0,
            "hours_until_trial_expiry": 0.0,
            "trial_active": False,
            "risk_score": 0.50,
        }
    )
    cat_min, scoreable_min, _ = derive_observable_expected_diagnosis(minimal_ev)
    assert cat_min != "TRIAL_EXPIRATION"
    assert cat_min == "LOW_INTENT"
    assert scoreable_min is True

    # 2. Expired with zero usage and pricing views > 1 -> falls through to INSUFFICIENT_EVIDENCE (P9)
    zero_usage_ev = sample_evidence_record.model_copy(
        update={
            "has_prior_conversion": False,
            "lifetime_payment_success_count": 0,
            "payment_failed_observed": False,
            "lifetime_payment_failure_count": 0,
            "checkout_abandonment_observed": False,
            "lifetime_checkout_start_count": 0,
            "lifetime_session_count": 0,
            "lifetime_feature_use_count": 0,
            "lifetime_pricing_view_count": 2,
            "days_since_last_active": 0.0,
            "hours_until_trial_expiry": 0.0,
            "trial_active": False,
            "risk_score": 0.60,
        }
    )
    cat_zero, scoreable_zero, reason_zero = derive_observable_expected_diagnosis(zero_usage_ev)
    assert cat_zero != "TRIAL_EXPIRATION"
    assert cat_zero == "INSUFFICIENT_EVIDENCE"
    assert scoreable_zero is False
    assert reason_zero == "Insufficient distinctive observable signals"


def test_phase_d_no_meaningful_risk_boundary_semantics(sample_evidence_record):
    """
    TEST D: NO_MEANINGFUL_RISK strict boundary and exclusion semantics.
    1. risk_score < 0.30 (e.g. 0.29) with no friction -> NO_MEANINGFUL_RISK (scoreable=True)
    2. risk_score == 0.30 exact boundary does NOT satisfy < 0.30
    3. Higher-precedence friction/conversion states override risk_score < 0.30
    """
    # 1. Below 0.30 threshold (0.29) -> NO_MEANINGFUL_RISK
    low_risk_ev = sample_evidence_record.model_copy(
        update={
            "has_prior_conversion": False,
            "lifetime_payment_success_count": 0,
            "payment_failed_observed": False,
            "lifetime_payment_failure_count": 0,
            "checkout_abandonment_observed": False,
            "lifetime_checkout_start_count": 0,
            "lifetime_session_count": 5,
            "lifetime_feature_use_count": 8,
            "days_since_last_active": 1.0,
            "hours_until_trial_expiry": 100.0,
            "risk_score": 0.29,
        }
    )
    cat_low, scoreable_low, _ = derive_observable_expected_diagnosis(low_risk_ev)
    assert cat_low == "NO_MEANINGFUL_RISK"
    assert scoreable_low is True

    # 2. Exact boundary 0.30 does NOT satisfy < 0.30 criterion
    boundary_ev = sample_evidence_record.model_copy(
        update={
            "has_prior_conversion": False,
            "lifetime_payment_success_count": 0,
            "payment_failed_observed": False,
            "lifetime_payment_failure_count": 0,
            "checkout_abandonment_observed": False,
            "lifetime_checkout_start_count": 0,
            "lifetime_session_count": 8,
            "lifetime_feature_use_count": 8,
            "lifetime_pricing_view_count": 0,
            "days_since_last_active": 1.0,
            "hours_until_trial_expiry": 120.0,
            "trial_active": True,
            "risk_score": 0.30,
        }
    )
    cat_bound, scoreable_bound, _ = derive_observable_expected_diagnosis(boundary_ev)
    assert cat_bound != "NO_MEANINGFUL_RISK"
    assert cat_bound == "INSUFFICIENT_EVIDENCE"
    assert scoreable_bound is False

    # 3. Higher-precedence friction overrides risk_score < 0.30
    friction_over_low_risk = sample_evidence_record.model_copy(
        update={
            "has_prior_conversion": False,
            "lifetime_payment_success_count": 0,
            "payment_failed_observed": True,
            "lifetime_payment_failure_count": 1,
            "checkout_abandonment_observed": False,
            "risk_score": 0.10,
        }
    )
    cat_fric, _, _ = derive_observable_expected_diagnosis(friction_over_low_risk)
    assert cat_fric == "PAYMENT_FRICTION"

    # 4. Higher-precedence abandonment overrides risk_score < 0.30
    abandon_over_low_risk = sample_evidence_record.model_copy(
        update={
            "has_prior_conversion": False,
            "lifetime_payment_success_count": 0,
            "payment_failed_observed": False,
            "lifetime_payment_failure_count": 0,
            "checkout_abandonment_observed": True,
            "risk_score": 0.10,
        }
    )
    cat_ab, _, _ = derive_observable_expected_diagnosis(abandon_over_low_risk)
    assert cat_ab == "CHECKOUT_ABANDONMENT"

    # 5. Higher-precedence conversion overrides risk_score < 0.30
    conv_over_low_risk = sample_evidence_record.model_copy(
        update={
            "has_prior_conversion": True,
            "lifetime_payment_success_count": 1,
            "payment_failed_observed": False,
            "risk_score": 0.05,
        }
    )
    cat_conv, _, _ = derive_observable_expected_diagnosis(conv_over_low_risk)
    assert cat_conv == "ALREADY_CONVERTED"


def test_phase_d_observable_expected_diagnosis_precedence(sample_evidence_record):
    """
    Proves authoritative observable precedence rules:
    P1 ALREADY_CONVERTED > P2 PAYMENT_FRICTION > P3 CHECKOUT_ABANDONMENT >
    P4 NO_MEANINGFUL_RISK > P5 ENGAGEMENT_DECLINE > P6 MIXED_SIGNALS >
    P7 LOW_INTENT > P8 TRIAL_EXPIRATION > P9 INSUFFICIENT_EVIDENCE
    """
    # 1. ALREADY_CONVERTED takes precedence over payment failure
    converted_ev = sample_evidence_record.model_copy(
        update={"has_prior_conversion": True, "payment_failed_observed": True}
    )
    cat, scoreable, reason = derive_observable_expected_diagnosis(converted_ev)
    assert cat == "ALREADY_CONVERTED"
    assert scoreable is True

    # 2. PAYMENT_FRICTION takes precedence over checkout abandonment & expiry
    friction_ev = sample_evidence_record.model_copy(
        update={
            "has_prior_conversion": False,
            "lifetime_payment_success_count": 0,
            "payment_failed_observed": True,
            "checkout_abandonment_observed": True,
            "hours_until_trial_expiry": 2.0,
        }
    )
    cat, scoreable, _ = derive_observable_expected_diagnosis(friction_ev)
    assert cat == "PAYMENT_FRICTION"
    assert scoreable is True

    # 3. CHECKOUT_ABANDONMENT takes precedence over passive expiry
    abandoned_ev = sample_evidence_record.model_copy(
        update={
            "has_prior_conversion": False,
            "lifetime_payment_success_count": 0,
            "payment_failed_observed": False,
            "lifetime_payment_failure_count": 0,
            "checkout_abandonment_observed": True,
            "hours_until_trial_expiry": 4.0,
        }
    )
    cat, scoreable, _ = derive_observable_expected_diagnosis(abandoned_ev)
    assert cat == "CHECKOUT_ABANDONMENT"
    assert scoreable is True

    # 4. NO_MEANINGFUL_RISK when risk_score < 0.30 and no friction
    low_risk_ev = sample_evidence_record.model_copy(
        update={
            "has_prior_conversion": False,
            "lifetime_payment_success_count": 0,
            "payment_failed_observed": False,
            "lifetime_payment_failure_count": 0,
            "checkout_abandonment_observed": False,
            "lifetime_checkout_start_count": 0,
            "risk_score": 0.15,
        }
    )
    cat, scoreable, _ = derive_observable_expected_diagnosis(low_risk_ev)
    assert cat == "NO_MEANINGFUL_RISK"
    assert scoreable is True

    # 5. ENGAGEMENT_DECLINE when inactive gap >= 5.0d with prior usage
    decline_ev = sample_evidence_record.model_copy(
        update={
            "has_prior_conversion": False,
            "lifetime_payment_success_count": 0,
            "payment_failed_observed": False,
            "lifetime_payment_failure_count": 0,
            "checkout_abandonment_observed": False,
            "lifetime_checkout_start_count": 0,
            "lifetime_session_count": 4,
            "lifetime_feature_use_count": 3,
            "days_since_last_active": 5.5,
            "risk_score": 0.60,
            "hours_until_trial_expiry": 10.0,  # Expiring soon, but engagement decline takes precedence
        }
    )
    cat, scoreable, _ = derive_observable_expected_diagnosis(decline_ev)
    assert cat == "ENGAGEMENT_DECLINE"
    assert scoreable is True

    # 6. MIXED_SIGNALS when high pricing views with zero checkout starts
    mixed_ev = sample_evidence_record.model_copy(
        update={
            "has_prior_conversion": False,
            "lifetime_payment_success_count": 0,
            "payment_failed_observed": False,
            "lifetime_payment_failure_count": 0,
            "checkout_abandonment_observed": False,
            "lifetime_checkout_start_count": 0,
            "lifetime_pricing_view_count": 4,
            "lifetime_session_count": 6,
            "days_since_last_active": 1.0,
            "risk_score": 0.65,
        }
    )
    cat, scoreable, _ = derive_observable_expected_diagnosis(mixed_ev)
    assert cat == "MIXED_SIGNALS"
    assert scoreable is True

    # 7. LOW_INTENT when lifetime activity is minimal
    low_intent_ev = sample_evidence_record.model_copy(
        update={
            "has_prior_conversion": False,
            "lifetime_payment_success_count": 0,
            "payment_failed_observed": False,
            "lifetime_payment_failure_count": 0,
            "checkout_abandonment_observed": False,
            "lifetime_checkout_start_count": 0,
            "lifetime_session_count": 2,
            "lifetime_feature_use_count": 1,
            "lifetime_pricing_view_count": 0,
            "days_since_last_active": 2.0,
            "hours_until_trial_expiry": 100.0,
            "risk_score": 0.50,
        }
    )
    cat, scoreable, _ = derive_observable_expected_diagnosis(low_intent_ev)
    assert cat == "LOW_INTENT"
    assert scoreable is True

    # 8. TRIAL_EXPIRATION when expiring with active usage
    expiring_ev = sample_evidence_record.model_copy(
        update={
            "has_prior_conversion": False,
            "lifetime_payment_success_count": 0,
            "payment_failed_observed": False,
            "lifetime_payment_failure_count": 0,
            "checkout_abandonment_observed": False,
            "lifetime_checkout_start_count": 0,
            "lifetime_session_count": 8,
            "lifetime_feature_use_count": 10,
            "lifetime_pricing_view_count": 1,
            "days_since_last_active": 1.0,
            "hours_until_trial_expiry": 24.0,
            "risk_score": 0.60,
        }
    )
    cat, scoreable, _ = derive_observable_expected_diagnosis(expiring_ev)
    assert cat == "TRIAL_EXPIRATION"
    assert scoreable is True

    # 9. INSUFFICIENT_EVIDENCE when pattern is indeterminate
    unscoreable_ev = sample_evidence_record.model_copy(
        update={
            "has_prior_conversion": False,
            "lifetime_payment_success_count": 0,
            "payment_failed_observed": False,
            "lifetime_payment_failure_count": 0,
            "checkout_abandonment_observed": False,
            "lifetime_checkout_start_count": 0,
            "lifetime_session_count": 8,
            "lifetime_feature_use_count": 8,
            "lifetime_pricing_view_count": 0,
            "days_since_last_active": 1.0,
            "hours_until_trial_expiry": 120.0,
            "trial_active": True,
            "risk_score": 0.60,
        }
    )
    cat, scoreable, reason = derive_observable_expected_diagnosis(unscoreable_ev)
    assert cat == "INSUFFICIENT_EVIDENCE"
    assert scoreable is False
    assert reason == "Insufficient distinctive observable signals"


def test_phase_d_quality_metrics_denominator_isolation():
    """
    Proves Scoreable Quality Denominator isolation:
    Quality metrics (accuracy, precision, recall, F1, confusion matrix) are calculated
    STRICTLY over scoreable Real Gemini records. Fallback records and unscoreable records
    are tracked only in operational mitigation counts and NEVER enter quality metrics.
    """
    mock_evaluator = MagicMock(spec=GeminiDiagnosisEvaluator)
    mock_evaluator.model = "gemini-2.5-flash"
    mock_evaluator.prompt_version = PROMPT_VERSION
    mock_evaluator.evidence_version = EVIDENCE_VERSION

    # Mock evaluate: first 5 customers succeed with Real Gemini, next 5 fail with MODEL_ERROR
    def mock_eval_partial(evidence: PhaseDEvidenceRecord) -> GeminiCallResult:
        cid_num = int(evidence.customer_id.split("_")[-1])
        if cid_num <= 5:
            # Return matching diagnosis for observable expected diagnosis
            obs_diag, _, _ = derive_observable_expected_diagnosis(evidence)
            return GeminiCallResult(
                status=GeminiModelCallStatus.REAL_GEMINI,
                raw_response_text=json.dumps({
                    "diagnosis": obs_diag,
                    "confidence": 0.90,
                    "actionability": "CANDIDATE",
                    "rationale": "Grounded diagnosis matching observable contract",
                    "evidence_used": [],
                }),
                parsed_json={
                    "diagnosis": obs_diag,
                    "confidence": 0.90,
                    "actionability": "CANDIDATE",
                    "rationale": "Grounded diagnosis matching observable contract",
                    "evidence_used": [],
                },
                latency_ms=100.0,
                prompt_tokens=200,
                candidates_tokens=40,
                total_tokens=240,
            )
        else:
            return GeminiCallResult(
                status=GeminiModelCallStatus.MODEL_ERROR,
                error_type="RATE_LIMITED",
                error_message="ResourceExhausted: 429 Quota Exceeded",
                latency_ms=50.0,
            )

    mock_evaluator.evaluate.side_effect = mock_eval_partial

    evaluator = PhaseDEvaluator(sample_size=10, seed=42, evaluator=mock_evaluator, enable_fallback=True)
    artifact = evaluator.run_evaluation()

    # Operational metrics
    op = artifact.operational_metrics
    assert op.attempted_evaluations == 10
    assert op.successful_evaluations == 5
    assert op.model_errors == 5
    assert op.fallback_evaluations == 5
    assert op.reconciliation_passed is True

    # Quality metrics denominator is strictly 5 (the real Gemini records), NOT 10
    qm = artifact.quality_metrics
    assert qm.available is True
    assert qm.scoreable_denominator == 5
    assert qm.diagnosis_accuracy == 1.0  # All 5 real Gemini predictions were accurate
    assert qm.macro_f1 == 1.0
    assert len(qm.confusion_matrix) > 0
    assert len(qm.confusion_matrix_labels) > 0


def test_phase_d_provider_retry_loop_on_transient_429(sample_evidence_record):
    """
    Proves that GeminiDiagnosisEvaluator implements bounded retry with backoff on 429/transient errors,
    recovering successfully when subsequent attempt succeeds, and recording retries_attempted.
    """
    evaluator = GeminiDiagnosisEvaluator(
        api_key="mock_test_key",
        max_retries=2,
        initial_backoff_seconds=0.01,
        pacing_delay_seconds=0.0,
    )
    evaluator._sdk_available = True
    mock_client = MagicMock()

    # First attempt raises 429, second attempt succeeds
    mock_success_resp = MagicMock()
    mock_success_resp.text = json.dumps({
        "diagnosis": "PAYMENT_FRICTION",
        "confidence": 0.90,
        "actionability": "CANDIDATE",
        "rationale": "Recovered on retry",
        "evidence_used": [],
    })
    mock_success_resp.usage_metadata = None

    mock_client.models.generate_content.side_effect = [
        Exception("ResourceExhausted: 429 Quota limit exceeded"),
        mock_success_resp,
    ]
    evaluator._genai_client = mock_client

    result = evaluator.evaluate(sample_evidence_record)
    assert result.status == GeminiModelCallStatus.REAL_GEMINI
    assert result.retries_attempted == 1
    assert mock_client.models.generate_content.call_count == 2


def test_phase_d_full_record_persistence():
    """
    Proves that Phase D artifact persists all evaluated customer records in evaluation_records
    without truncation (e.g. all 15 records in a 15-sample run).
    """
    evaluator = PhaseDEvaluator(sample_size=15, seed=42)
    artifact = evaluator.run_evaluation()

    assert len(artifact.evaluation_records) == 15
    assert len(artifact.sample_records) == 5  # sample preview retains top 5
    # Verify every record in evaluation_records has required v2 fields
    for rec in artifact.evaluation_records:
        assert "customer_id" in rec
        assert "observable_expected_diagnosis" in rec
        assert "is_scoreable" in rec
        assert "retries_attempted" in rec
        assert "model_call_status" in rec


def test_phase_d_observability_metrics_calculation():
    """
    Proves that PhaseDObservabilityMetrics correctly captures scoreable count,
    scoreable rate percentage, and observable label distribution.
    """
    evaluator = PhaseDEvaluator(sample_size=20, seed=42)
    artifact = evaluator.run_evaluation()

    obs = artifact.observability_metrics
    assert obs.total_evaluated == 20
    assert obs.scoreable_count + obs.unscoreable_count == 20
    assert obs.scoreable_rate_pct == round(100.0 * obs.scoreable_count / 20, 2)
    assert len(obs.observable_label_distribution) > 0
    assert sum(obs.observable_label_distribution.values()) == 20


def test_phase_d_evaluator_pacing_and_retry_runner_wiring():
    """
    Proves that PhaseDEvaluator correctly receives and wires pacing_delay_seconds,
    max_retries, initial_backoff_seconds, and timeout_seconds into GeminiDiagnosisEvaluator.
    """
    evaluator = PhaseDEvaluator(
        sample_size=5,
        seed=42,
        timeout_seconds=15.5,
        pacing_delay_seconds=1.25,
        max_retries=4,
        initial_backoff_seconds=3.5,
    )
    assert evaluator.evaluator.timeout_seconds == 15.5
    assert evaluator.evaluator.pacing_delay_seconds == 1.25
    assert evaluator.evaluator.max_retries == 4
    assert evaluator.evaluator.initial_backoff_seconds == 3.5


def test_phase_d_provider_retry_loop_on_timeout_recovery(sample_evidence_record):
    """
    Proves that GeminiDiagnosisEvaluator retries on native TimeoutError,
    recovers successfully when subsequent attempt succeeds, and records retries_attempted.
    """
    evaluator = GeminiDiagnosisEvaluator(
        api_key="mock_test_key",
        max_retries=2,
        initial_backoff_seconds=0.001,
        pacing_delay_seconds=0.0,
    )
    evaluator._sdk_available = True
    mock_client = MagicMock()

    mock_success_resp = MagicMock()
    mock_success_resp.text = json.dumps({
        "diagnosis": "PAYMENT_FRICTION",
        "confidence": 0.90,
        "actionability": "CANDIDATE",
        "rationale": "Recovered after TimeoutError retry",
        "evidence_used": [],
    })
    mock_success_resp.usage_metadata = None

    mock_client.models.generate_content.side_effect = [
        TimeoutError("Request to Gemini API timed out after 10.0s"),
        mock_success_resp,
    ]
    evaluator._genai_client = mock_client

    result = evaluator.evaluate(sample_evidence_record)
    assert result.status == GeminiModelCallStatus.REAL_GEMINI
    assert result.retries_attempted == 1
    assert mock_client.models.generate_content.call_count == 2


def test_phase_d_provider_retry_loop_on_transport_timeout_recovery(sample_evidence_record):
    """
    Proves that GeminiDiagnosisEvaluator retries on HTTP / SSL transport timeouts
    (e.g., httpx.ReadTimeout, handshake timeout), recovers successfully, and records retries_attempted.
    """
    import httpx

    evaluator = GeminiDiagnosisEvaluator(
        api_key="mock_test_key",
        max_retries=2,
        initial_backoff_seconds=0.001,
        pacing_delay_seconds=0.0,
    )
    evaluator._sdk_available = True
    mock_client = MagicMock()

    mock_success_resp = MagicMock()
    mock_success_resp.text = json.dumps({
        "diagnosis": "PAYMENT_FRICTION",
        "confidence": 0.88,
        "actionability": "CANDIDATE",
        "rationale": "Recovered after transport timeout retries",
        "evidence_used": [],
    })
    mock_success_resp.usage_metadata = None

    mock_client.models.generate_content.side_effect = [
        httpx.ReadTimeout("The read operation timed out"),
        Exception("_ssl.c:1015: The handshake operation timed out"),
        mock_success_resp,
    ]
    evaluator._genai_client = mock_client

    result = evaluator.evaluate(sample_evidence_record)
    assert result.status == GeminiModelCallStatus.REAL_GEMINI
    assert result.retries_attempted == 2
    assert mock_client.models.generate_content.call_count == 3


def test_phase_d_provider_timeout_exhaustion_returns_model_error(sample_evidence_record):
    """
    Proves that when timeouts persist through all retry attempts,
    evaluator returns MODEL_ERROR with error_type TIMEOUT and retries_attempted equal to max_retries.
    """
    evaluator = GeminiDiagnosisEvaluator(
        api_key="mock_test_key",
        max_retries=2,
        initial_backoff_seconds=0.001,
        pacing_delay_seconds=0.0,
    )
    evaluator._sdk_available = True
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = TimeoutError("Request timed out")
    evaluator._genai_client = mock_client

    result = evaluator.evaluate(sample_evidence_record)
    assert result.status == GeminiModelCallStatus.MODEL_ERROR
    assert result.error_type == "TIMEOUT"
    assert result.retries_attempted == 2
    assert mock_client.models.generate_content.call_count == 3


def test_phase_d_provider_timeout_with_zero_retries(sample_evidence_record):
    """
    Proves that when max_retries=0, timeout failure returns MODEL_ERROR immediately
    with retries_attempted=0 and exactly 1 call.
    """
    evaluator = GeminiDiagnosisEvaluator(
        api_key="mock_test_key",
        max_retries=0,
        initial_backoff_seconds=0.001,
        pacing_delay_seconds=0.0,
    )
    evaluator._sdk_available = True
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = TimeoutError("Request timed out")
    evaluator._genai_client = mock_client

    result = evaluator.evaluate(sample_evidence_record)
    assert result.status == GeminiModelCallStatus.MODEL_ERROR
    assert result.error_type == "TIMEOUT"
    assert result.retries_attempted == 0
    assert mock_client.models.generate_content.call_count == 1


def test_phase_d_provider_non_retryable_errors_no_retry(sample_evidence_record):
    """
    Proves that non-transient errors (401/403 Auth, 404 Model Not Found, generic API errors)
    are NOT retried and immediately return with retries_attempted=0 and exactly 1 attempt.
    """
    # 1. Auth error (401/403)
    evaluator_auth = GeminiDiagnosisEvaluator(
        api_key="mock_test_key",
        max_retries=2,
        initial_backoff_seconds=0.001,
    )
    evaluator_auth._sdk_available = True
    mock_client_auth = MagicMock()
    mock_client_auth.models.generate_content.side_effect = Exception("401 Unauthorized: Invalid API key")
    evaluator_auth._genai_client = mock_client_auth

    res_auth = evaluator_auth.evaluate(sample_evidence_record)
    assert res_auth.status == GeminiModelCallStatus.MODEL_ERROR
    assert res_auth.error_type == "AUTH_ERROR"
    assert res_auth.retries_attempted == 0
    assert mock_client_auth.models.generate_content.call_count == 1

    # 2. Model Not Found (404)
    evaluator_404 = GeminiDiagnosisEvaluator(
        api_key="mock_test_key",
        max_retries=2,
        initial_backoff_seconds=0.001,
    )
    evaluator_404._sdk_available = True
    mock_client_404 = MagicMock()
    mock_client_404.models.generate_content.side_effect = Exception("404 Model not found: models/gemini-unknown")
    evaluator_404._genai_client = mock_client_404

    res_404 = evaluator_404.evaluate(sample_evidence_record)
    assert res_404.status == GeminiModelCallStatus.MODEL_ERROR
    assert res_404.error_type == "MODEL_NOT_FOUND"
    assert res_404.retries_attempted == 0
    assert mock_client_404.models.generate_content.call_count == 1

    # 3. Generic API Error
    evaluator_generic = GeminiDiagnosisEvaluator(
        api_key="mock_test_key",
        max_retries=2,
        initial_backoff_seconds=0.001,
    )
    evaluator_generic._sdk_available = True
    mock_client_generic = MagicMock()
    mock_client_generic.models.generate_content.side_effect = Exception("Invalid argument: Bad request payload")
    evaluator_generic._genai_client = mock_client_generic

    res_generic = evaluator_generic.evaluate(sample_evidence_record)
    assert res_generic.status == GeminiModelCallStatus.MODEL_ERROR
    assert res_generic.error_type == "API_ERROR"
    assert res_generic.retries_attempted == 0
    assert mock_client_generic.models.generate_content.call_count == 1


# ===========================================================================
# 11. PHASE D v3: SELECTIVE AI DIAGNOSIS & ROUTER TESTS
# ===========================================================================

def test_phase_d_v3_router_deterministic_rules(sample_evidence_record):
    """Deterministic routing engine immediately classifies clear single-signal journeys without AI invocation."""
    # 1. Prior conversion -> DETERMINISTIC
    rec_conv = sample_evidence_record.model_copy(update={"has_prior_conversion": True})
    decision_conv = route_customer_evidence(rec_conv)
    assert decision_conv.review_mode == ReviewMode.DETERMINISTIC
    assert decision_conv.trigger_id == TRIGGER_DET_CONVERSION

    # 2. Payment failed observed -> DETERMINISTIC
    rec_pay = sample_evidence_record.model_copy(update={
        "has_prior_conversion": False,
        "payment_failed_observed": True,
    })
    decision_pay = route_customer_evidence(rec_pay)
    assert decision_pay.review_mode == ReviewMode.DETERMINISTIC
    assert decision_pay.trigger_id == TRIGGER_DET_PAYMENT_FAILURE

    # 3. Checkout abandonment -> DETERMINISTIC
    rec_chk = sample_evidence_record.model_copy(update={
        "has_prior_conversion": False,
        "payment_failed_observed": False,
        "lifetime_payment_failure_count": 0,
        "checkout_abandonment_observed": True,
    })
    decision_chk = route_customer_evidence(rec_chk)
    assert decision_chk.review_mode == ReviewMode.DETERMINISTIC
    assert decision_chk.trigger_id == TRIGGER_DET_CHECKOUT_ABANDONMENT

    # 4. Low risk / healthy -> DETERMINISTIC
    rec_low = sample_evidence_record.model_copy(update={
        "has_prior_conversion": False,
        "payment_failed_observed": False,
        "lifetime_payment_failure_count": 0,
        "checkout_abandonment_observed": False,
        "risk_score": 0.15,
        "risk_tier": "LOW",
    })
    decision_low = route_customer_evidence(rec_low)
    assert decision_low.review_mode == ReviewMode.DETERMINISTIC
    assert decision_low.trigger_id == TRIGGER_DET_LOW_RISK



def test_phase_d_v3_router_ai_review_commercial_intent_divergence(sample_evidence_record):
    """Customer with repeated pricing page views, active usage, but zero checkout starts triggers AI review."""
    ambiguous_record = sample_evidence_record.model_copy(update={
        "has_prior_conversion": False,
        "payment_failed_observed": False,
        "checkout_abandonment_observed": False,
        "risk_score": 0.54,
        "risk_tier": "MEDIUM",
        "lifetime_pricing_view_count": 5,
        "lifetime_feature_use_count": 15,
        "lifetime_session_count": 5,
        "lifetime_checkout_start_count": 0,
        "lifetime_payment_failure_count": 0,
        "days_since_last_active": 2.0,
        "trial_active": False,
    })

    decision = route_customer_evidence(ambiguous_record)
    assert decision.review_mode == ReviewMode.AI_REVIEW
    assert decision.trigger_id == TRIGGER_AI_COMMERCIAL_INTENT_DIVERGENCE
    assert "repeated pricing page exploration" in decision.routing_reason


def test_phase_d_v3_router_ai_review_disparate_engagement(sample_evidence_record):
    """
    Customer with elevated risk (risk_score >= 0.40), frequent sessions (lifetime_session_count >= 6),
    minimal feature adoption (lifetime_feature_use_count <= 3), and recent activity (days_since_last_active <= 3.0)
    triggers TRIGGER_AI_DISPARATE_ENGAGEMENT for AI review.
    """

    disparate_record = sample_evidence_record.model_copy(update={
        "has_prior_conversion": False,
        "payment_failed_observed": False,
        "checkout_abandonment_observed": False,
        "risk_score": 0.50,
        "risk_tier": "MEDIUM",
        "lifetime_pricing_view_count": 0,
        "lifetime_feature_use_count": 2,
        "lifetime_session_count": 6,
        "lifetime_checkout_start_count": 0,
        "lifetime_payment_failure_count": 0,
        "days_since_last_active": 1.0,
        "trial_active": False,
    })

    decision = route_customer_evidence(disparate_record)
    assert decision.review_mode == ReviewMode.AI_REVIEW
    assert decision.trigger_id == TRIGGER_AI_DISPARATE_ENGAGEMENT
    assert "Disparate engagement pattern" in decision.routing_reason


def test_phase_d_v3_router_determinism_and_purity(sample_evidence_record):
    """Routing decisions are purely deterministic functions of observable fields with zero randomness or hidden state."""
    rec = sample_evidence_record.model_copy(update={
        "has_prior_conversion": False,
        "payment_failed_observed": False,
        "checkout_abandonment_observed": False,
        "risk_score": 0.55,
        "lifetime_pricing_view_count": 3,
        "lifetime_feature_use_count": 8,
        "lifetime_session_count": 4,
        "lifetime_checkout_start_count": 0,
    })

    d1 = route_customer_evidence(rec)
    d2 = route_customer_evidence(rec)
    d3 = route_customer_evidence(rec)

    assert d1.review_mode == d2.review_mode == d3.review_mode
    assert d1.trigger_id == d2.trigger_id == d3.trigger_id
    assert d1.routing_reason == d2.routing_reason == d3.routing_reason


def test_phase_d_v3_primary_demonstration_selector():
    """Primary demonstration case selector dynamically identifies an AI_REVIEW case from observable cohort without hardcoding."""
    cus, plan, evts, feat_rec, scored_cust, evidence, routing = select_primary_demonstration_case(sample_size=100, seed=42)

    assert evidence is not None
    assert isinstance(evidence, PhaseDEvidenceRecord)
    assert routing.review_mode == ReviewMode.AI_REVIEW
    assert routing.trigger_id.startswith("TRIGGER_AI_")
    assert routing.routing_reason is not None and len(routing.routing_reason) > 0

    # Verify observable multi-signal complexity
    assert evidence.lifetime_pricing_view_count > 0 or evidence.lifetime_feature_use_count > 0
    assert not evidence.has_prior_conversion
    assert not evidence.payment_failed_observed

    # Verify repeatability
    cus2, plan2, evts2, feat_rec2, scored_cust2, evidence2, routing2 = select_primary_demonstration_case(sample_size=100, seed=42)
    assert evidence.customer_id == evidence2.customer_id
    assert routing.trigger_id == routing2.trigger_id


def test_phase_d_v3_prompt_builder_structure(sample_evidence_record):
    """Prompt v3 includes routing context, bounded vocabulary, uncertainty guidelines, and zero-authority constraints."""
    routing_reason = "Conflicting commercial intent: repeated pricing page exploration."
    prompt = build_gemini_diagnosis_prompt(sample_evidence_record, routing_reason=routing_reason)

    assert "REVIVE_GEMINI_DIAGNOSIS_PROMPT_V3" in PROMPT_VERSION
    assert "AI REVIEW ROUTING CONTEXT (SELECTIVE INVOCATION)" in prompt
    assert routing_reason in prompt
    assert "AUTHORITATIVE OBSERVABLE DIAGNOSIS TAXONOMY & PRECEDENCE" in prompt
    assert "ZERO execution authority" in prompt
    assert "DIAGNOSIS ONLY — NO EXECUTION AUTHORITY" in prompt
    assert "Do NOT invent" in prompt


def test_phase_d_v3_demonstration_mock_pipeline_execution(tmp_path):
    """End-to-end execution of Phase D v3 demonstration pipeline using mock Gemini evaluator."""
    output_file = tmp_path / "phase_d_gemini_demo_test.json"

    mock_evaluator = MagicMock(spec=GeminiDiagnosisEvaluator)
    mock_evaluator.is_available.return_value = True
    mock_evaluator.model = "gemini-2.5-flash"
    mock_evaluator.prompt_version = PROMPT_VERSION

    mock_response = GeminiCallResult(
        status=GeminiModelCallStatus.REAL_GEMINI,
        raw_response_text=json.dumps({
            "diagnosis": "MIXED_SIGNALS",
            "confidence": 0.85,
            "actionability": "CANDIDATE",
            "rationale": "Customer frequently explored pricing tiers while actively engaging with core product features.",
            "evidence_used": ["5 pricing page views observed", "15 feature uses observed"],
            "uncertainty_reasons": ["No checkout was initiated to verify payment method preference"],
        }),
        parsed_json={
            "diagnosis": "MIXED_SIGNALS",
            "confidence": 0.85,
            "actionability": "CANDIDATE",
            "rationale": "Customer frequently explored pricing tiers while actively engaging with core product features.",
            "evidence_used": ["5 pricing page views observed", "15 feature uses observed"],
            "uncertainty_reasons": ["No checkout was initiated to verify payment method preference"],
        },
        latency_ms=320.0,
        prompt_tokens=310,
        candidates_tokens=85,
        total_tokens=395,
    )
    mock_evaluator.evaluate.return_value = mock_response

    artifact = run_demonstration(
        output_path=output_file,
        evaluator=mock_evaluator,
        sample_size=100,
        seed=42,
    )

    assert artifact is not None
    assert artifact.phase_version == "3.0.0"
    assert artifact.demonstration_case is not None

    demo = artifact.demonstration_case
    assert demo.routing_mode == ReviewMode.AI_REVIEW.value
    assert demo.trigger_id.startswith("TRIGGER_AI_")
    assert demo.gemini_response.diagnosis == "MIXED_SIGNALS"
    assert demo.gemini_response.confidence == 0.85
    assert demo.governance_result.execution_authority == "NONE (PROPOSAL ONLY)"
    assert "SAFETY_VERIFIED" in demo.governance_result.governance_verdict
    assert demo.execution_authority_result.gemini_has_execution_power is False
    assert demo.policy_result.policy_version == "v1.0.0"
    assert output_file.exists()

    # Ensure saved JSON is readable and valid
    with open(output_file, "r", encoding="utf-8") as f:
        saved_data = json.load(f)
    assert saved_data["phase_version"] == "3.0.0"
    assert "demonstration_case" in saved_data


def test_phase_d_v3_demonstration_output_validation_rejection(tmp_path):
    """When Gemini returns an invalid category or unsupported execution claim, governance detects and handles it safely."""
    output_file = tmp_path / "phase_d_gemini_demo_invalid.json"

    mock_evaluator = MagicMock(spec=GeminiDiagnosisEvaluator)
    mock_evaluator.is_available.return_value = True
    mock_evaluator.model = "gemini-2.5-flash"
    mock_evaluator.prompt_version = PROMPT_VERSION

    # Model attempts unsupported execution action claim
    mock_response = GeminiCallResult(
        status=GeminiModelCallStatus.SCHEMA_REJECTED,
        raw_response_text=json.dumps({
            "diagnosis": "PRICING_PAGE_DROP_OFF",
            "confidence": 0.85,
            "actionability": "CANDIDATE",
            "rationale": "Customer needs a discount. I am immediately issuing a 50% discount refund.",
            "evidence_used": ["5 pricing page views observed"],
            "uncertainty_reasons": [],
            "action": "EXECUTE_DIRECT_REFUND",
        }),
        parsed_json=None,
        error_type="UNSUPPORTED_ACTION_CLAIM",
        error_message="unsupported action claim and unauthorized execution attempt detected",
        latency_ms=250.0,
    )
    mock_evaluator.evaluate.return_value = mock_response

    artifact = run_demonstration(
        output_path=output_file,
        evaluator=mock_evaluator,
        sample_size=100,
        seed=42,
    )

    assert artifact.demonstration_case is not None
    gov = artifact.demonstration_case.governance_result
    assert gov.execution_bypass_detected is True
    assert gov.unsupported_action_claim_detected is True
    assert gov.governance_verdict == "GOVERNANCE_VIOLATIONS_DETECTED"


def test_phase_d_v3_api_dashboard_endpoint_serves_demo_case(tmp_path, monkeypatch):
    """FastAPI /api/dashboard/gemini-evaluation returns demonstration_case when v3 artifact exists."""
    from app.api import dashboard

    demo_file = tmp_path / "phase_d_gemini_demo.json"
    demo_payload = {
        "phase_version": "3.0.0",
        "provenance": "PHASE D REAL GEMINI EVALUATION (Selective AI Review)",
        "source_artifact": "docs/evidence/phase_d_gemini_demo.json",
        "status": "AVAILABLE",
        "model": "gemini-2.5-flash",
        "prompt_version": PROMPT_VERSION,
        "evidence_version": EVIDENCE_VERSION,
        "operational_metrics": {
            "attempted_evaluations": 1,
            "successful_evaluations": 1,
            "schema_rejections": 0,
            "model_errors": 0,
            "unavailable_evaluations": 0,
            "fallback_evaluations": 0,
            "scoreable_evaluations": 1,
            "not_scoreable_evaluations": 0,
            "total_retries": 0,
            "rate_limit_events": 0,
            "success_rate_pct": 100.0,
            "average_latency_ms": 350.0,
            "p95_latency_ms": 350.0,
            "reconciliation_passed": True,
            "reconciliation_formula": "100% terminal state reconciliation",
        },
        "governance_metrics": {
            "execution_bypass_attempts_observed": 0,
            "unsupported_action_claims_observed": 0,
            "policy_guard_violations_observed": 0,
            "non_compliant_records_count": 0,
            "safety_compliance_rate_pct": 100.0,
            "governance_verdict": "SAFETY_VERIFIED: Zero unauthorized execution claims",
        },
        "cost_accounting": {
            "cost_data_status": "PROVIDER_REPORTED_USAGE",
            "prompt_tokens_sum": 300,
            "candidates_tokens_sum": 80,
            "total_tokens_sum": 380,
            "estimated_cost_inr": None,
            "cost_basis_note": "Token counts reported directly by Google Gemini API",
        },
        "failure_summary": {},
        "sample_records": [],
        "demonstration_case": {
            "customer_id": "cus_000003",
            "routing_mode": "AI_REVIEW",
            "trigger_id": "TRIGGER_AI_COMMERCIAL_INTENT_DIVERGENCE",
            "routing_reason": "Commercial Intent Divergence: 5 pricing views with 15 feature uses.",
            "observable_signal_summary": {
                "risk_score": 0.5438,
                "risk_tier": "MEDIUM",
                "plan": "Growth Plan",
                "lifetime_events": 25,
                "sessions": 5,
                "feature_uses": 15,
                "pricing_page_views": 5,
                "checkout_starts": 0,
                "payment_failures": 0,
                "days_since_last_active": 2.0,
                "observable_signals": ["HIGH_PRICING_PAGE_VIEWS", "ACTIVE_FEATURE_USAGE"],
                "recent_events": [],
            },
            "gemini_response": {
                "model": "gemini-2.5-flash",
                "status": "REAL_GEMINI",
                "diagnosis": "MIXED_SIGNALS",
                "confidence": 0.85,
                "rationale": "Customer repeatedly viewed pricing page while using features actively.",
                "evidence_used": ["5 pricing views observed"],
                "uncertainty_notes": "None",
                "unsupported_claims": [],
                "execution_bypass_attempted": False,
                "latency_ms": 350.0,
            },
            "governance_result": {
                "execution_authority": "NONE (PROPOSAL ONLY)",
                "policy_gating_applied": True,
                "execution_bypass_detected": False,
                "unsupported_action_claim_detected": False,
                "policy_guard_violation_detected": False,
                "governance_verdict": "GOVERNANCE_PASSED",
            },
            "policy_result": {
                "eligibility_status": "ELIGIBLE",
                "selected_action": "OFFER_DISCOUNT",
                "expected_value": 450.0,
                "policy_version": "REVIVE_POLICY_V1",
                "governed_decision_summary": "Policy evaluated OFFER_DISCOUNT with EV of Rs. 450.00",
            },
            "execution_authority_result": {
                "authority_held_by": "REVIVE Deterministic Policy & Guarded ExecutionEngine",
                "gemini_has_execution_power": False,
                "guarded_execution_status": "GOVERNED_POLICY_GATE",
            },
            "cost_accounting": {
                "prompt_tokens": 300,
                "candidates_tokens": 80,
                "total_tokens": 380,
                "estimated_cost_inr": 0.0028,
            },
        },
    }

    with open(demo_file, "w", encoding="utf-8") as f:
        json.dump(demo_payload, f)

    monkeypatch.setattr(dashboard, "_DEFAULT_DEMO_PATH", demo_file)
    monkeypatch.setattr(dashboard, "_PHASE_D_EVIDENCE_PATH", demo_file)

    client = TestClient(app)
    response = client.get("/api/dashboard/gemini-evaluation")

    assert response.status_code == 200
    data = response.json()

    assert data["available"] is True
    assert data["status"] == "GEMINI — REAL DEMONSTRATION"
    assert data["phase_version"] == "3.0.0"
    assert data["demonstration_case"] is not None
    assert data["demonstration_case"]["customer_id"] == "cus_000003"
    assert data["demonstration_case"]["routing_mode"] == "AI_REVIEW"
    assert data["demonstration_case"]["gemini_response"]["diagnosis"] == "MIXED_SIGNALS"


def test_phase_d_v3_cli_summary_rendering(tmp_path):
    """CLI format_cli_summary renders PhaseDDemonstrationCase object cleanly without AttributeError."""
    mock_evaluator = MagicMock(spec=GeminiDiagnosisEvaluator)
    mock_evaluator.is_available.return_value = True
    mock_evaluator.model = "gemini-2.5-flash"
    mock_evaluator.prompt_version = PROMPT_VERSION

    mock_response = GeminiCallResult(
        status=GeminiModelCallStatus.REAL_GEMINI,
        raw_response_text=json.dumps({
            "diagnosis": "MIXED_SIGNALS",
            "confidence": 0.85,
            "actionability": "CANDIDATE",
            "rationale": "Pricing page exploration with active product engagement.",
            "evidence_used": ["5 pricing views"],
            "uncertainty_reasons": [],
        }),
        parsed_json={
            "diagnosis": "MIXED_SIGNALS",
            "confidence": 0.85,
            "actionability": "CANDIDATE",
            "rationale": "Pricing page exploration with active product engagement.",
            "evidence_used": ["5 pricing views"],
            "uncertainty_reasons": [],
        },
        latency_ms=250.0,
        prompt_tokens=300,
        candidates_tokens=75,
        total_tokens=375,
    )
    mock_evaluator.evaluate.return_value = mock_response

    output_file = tmp_path / "test_demo.json"
    artifact = run_demonstration(
        output_path=output_file,
        evaluator=mock_evaluator,
        sample_size=100,
        seed=42,
    )

    summary_text = format_cli_summary(artifact)
    assert isinstance(summary_text, str)
    assert "--- DEMONSTRATION SUMMARY ---" in summary_text
    assert "Selected Customer: cus_000003" in summary_text
    assert "Routing Mode: AI_REVIEW" in summary_text
    assert "Gemini Status: REAL_GEMINI" in summary_text
    assert "Gemini Diagnosis: MIXED_SIGNALS (Confidence: 0.85)" in summary_text
    assert "Actionability: CANDIDATE" in summary_text
    assert "--- DETERMINISTIC POLICY GOVERNANCE ---" in summary_text
    assert "Eligibility: ELIGIBLE" in summary_text
    assert "Selected Action: NO_ACTION" in summary_text
    assert "Expected Value: INR 0.00" in summary_text
    assert "--- GOVERNANCE & SAFETY ---" in summary_text
    assert "SAFETY_VERIFIED" in summary_text


def test_phase_d_v3_selector_never_accesses_hidden_ground_truth():
    """
    Proves that demonstration case selection operates purely on observable customer entities
    and evidence without importing or accessing simulator ground truth or hidden variables.
    """
    # 1. Verify generate_synthetic_observable_cohort returns pure observable entities
    cohort = generate_synthetic_observable_cohort(sample_size=20, seed=42)
    assert len(cohort) == 20
    for cus, plan, evts in cohort:
        assert hasattr(cus, "customer_id")
        assert hasattr(plan, "plan_id")
        assert isinstance(evts, list)
        # Ensure no simulator ground truth is attached to observable entities
        assert not hasattr(cus, "natural_conversion")
        assert not hasattr(cus, "true_root_cause")
        assert not hasattr(cus, "generation_segment")

    # 2. Verify select_primary_demonstration_case operates on observable entities
    cus, plan, evts, feat_rec, scored_cust, evidence, routing = select_primary_demonstration_case(
        sample_size=100, seed=42
    )
    assert cus is not None
    assert evidence is not None
    assert routing.review_mode == ReviewMode.AI_REVIEW
    # Ensure evidence record does not leak ground truth fields
    assert not hasattr(evidence, "natural_conversion")
    assert not hasattr(evidence, "true_root_cause")
    assert not hasattr(evidence, "generation_segment")
    assert evidence.customer_id == "cus_000003"


def test_phase_d_v3_ai_review_is_selective(sample_evidence_record):
    """
    Proves that AI_REVIEW is strictly selective:
    - Ordinary moderate/high-risk cases without multi-signal conflict fall through to DETERMINISTIC with TRIGGER_DET_INSUFFICIENT_EVIDENCE.
    - AI_REVIEW is only triggered by specific multi-signal friction/divergence patterns.
    """
    # 1. Ordinary moderate/high-risk customer without multi-signal friction -> DETERMINISTIC
    ordinary_high_risk = sample_evidence_record.model_copy(
        update={
            "has_prior_conversion": False,
            "payment_failed_observed": False,
            "lifetime_payment_failure_count": 0,
            "checkout_abandonment_observed": False,
            "lifetime_checkout_start_count": 0,
            "risk_score": 0.55,
            "risk_tier": "HIGH",
            "lifetime_session_count": 6,
            "lifetime_feature_use_count": 8,
            "lifetime_pricing_view_count": 0,
            "days_since_last_active": 1.0,
            "hours_until_trial_expiry": 100.0,
            "trial_active": True,
        }
    )
    decision = route_customer_evidence(ordinary_high_risk)
    assert decision.review_mode == ReviewMode.DETERMINISTIC
    assert decision.trigger_id == TRIGGER_DET_INSUFFICIENT_EVIDENCE
    assert "Unambiguous or unclassified journey" in decision.routing_reason



    # 2. Evaluate selective rate across a full 100-customer cohort
    risk_model = ReviveRiskModel.load("models/risk/risk_model.joblib")
    feature_extractor = CustomerFeatureExtractor(snapshot_hours=72.0)
    risk_scorer = RiskScorer(model=risk_model)
    diag_engine = DiagnosisEngine()


    cohort = generate_synthetic_observable_cohort(sample_size=100, seed=42)
    ai_review_count = 0
    det_count = 0
    for cus, plan, evts in cohort:
        feat_rec, status_str = feature_extractor.extract_features(cus, evts, plan)
        if status_str != "OK":
            continue
        scored = risk_scorer.score_customer(feat_rec)
        ev = extract_observable_evidence(cus, plan, evts, feat_rec, scored, diag_engine)
        d = route_customer_evidence(ev)
        if d.review_mode == ReviewMode.AI_REVIEW:
            ai_review_count += 1
            assert d.trigger_id in (
                TRIGGER_AI_COMMERCIAL_INTENT_DIVERGENCE,
                TRIGGER_AI_DISPARATE_ENGAGEMENT,
            )
        else:
            det_count += 1

    assert ai_review_count + det_count == 100
    # AI review must be a selective minority of the cohort (e.g. <= 20%)
    assert 0 < ai_review_count <= 20
    assert det_count >= 80


def test_phase_d_v3_demonstration_model_error_provenance(tmp_path):
    """
    Proves that when Gemini returns MODEL_ERROR:
    1. error_type and sanitized error_message are preserved in demonstration_case.gemini_response.
    2. Secrets/API keys are redacted.
    3. CLI summary outputs 'Actionability: N/A — Gemini response unavailable' (NEVER policy eligibility).
    4. Deterministic policy governance remains separate and intact.
    """
    output_file = tmp_path / "phase_d_model_error.json"
    mock_evaluator = MagicMock(spec=GeminiDiagnosisEvaluator)
    mock_evaluator.is_available.return_value = True
    mock_evaluator.model = "gemini-3.5-flash-lite"
    mock_evaluator.prompt_version = PROMPT_VERSION

    mock_evaluator.evaluate.return_value = GeminiCallResult(
        status=GeminiModelCallStatus.MODEL_ERROR,
        error_type="RATE_LIMITED",
        error_message="ResourceExhausted: 429 Quota limit exceeded for key AIzaSyD000000000000000000000000000000000 with Bearer secret_tok_12345",
        latency_ms=1250.0,
        retries_attempted=2,
    )

    artifact = run_demonstration(
        output_path=output_file,
        evaluator=mock_evaluator,
        sample_size=100,
        seed=42,
    )

    demo = artifact.demonstration_case
    assert demo is not None
    assert demo.gemini_response.status == "MODEL_ERROR"
    assert demo.gemini_response.diagnosis is None
    assert demo.gemini_response.confidence is None
    assert demo.gemini_response.actionability is None
    assert demo.gemini_response.error_type == "RATE_LIMITED"
    assert demo.gemini_response.error_message is not None
    # Verify secret redaction
    assert "AIzaSyD000000000000000000000000000000000" not in demo.gemini_response.error_message
    assert "secret_tok_12345" not in demo.gemini_response.error_message
    assert "[REDACTED_API_KEY]" in demo.gemini_response.error_message
    assert "Bearer [REDACTED]" in demo.gemini_response.error_message

    # Verify CLI summary formatting
    summary = format_cli_summary(artifact)
    assert "Gemini Status: MODEL_ERROR" in summary
    assert "Gemini Diagnosis: None" in summary
    assert "Actionability: N/A — Gemini response unavailable" in summary
    assert "Actionability: ELIGIBLE" not in summary
    assert "Error Type: RATE_LIMITED" in summary
    assert "--- DETERMINISTIC POLICY GOVERNANCE ---" in summary
    assert "Eligibility: ELIGIBLE" in summary
    assert "Selected Action:" in summary
    assert "Expected Value:" in summary


def test_phase_d_v3_demonstration_model_unavailable_provenance(tmp_path):
    """
    Proves that when Gemini is MODEL_UNAVAILABLE:
    1. error_type and error_message capture credential/SDK unavailability.
    2. CLI summary outputs 'Actionability: N/A — Gemini unavailable'.
    """
    output_file = tmp_path / "phase_d_model_unavail.json"
    mock_evaluator = MagicMock(spec=GeminiDiagnosisEvaluator)
    mock_evaluator.is_available.return_value = False
    mock_evaluator.model = "gemini-2.5-flash"
    mock_evaluator.prompt_version = PROMPT_VERSION

    mock_evaluator.evaluate.return_value = GeminiCallResult(
        status=GeminiModelCallStatus.MODEL_UNAVAILABLE,
        error_type="CREDENTIALS_UNAVAILABLE",
        error_message="GEMINI_API_KEY environment variable is not configured.",
        latency_ms=0.0,
    )

    artifact = run_demonstration(
        output_path=output_file,
        evaluator=mock_evaluator,
        sample_size=100,
        seed=42,
    )

    demo = artifact.demonstration_case
    assert demo is not None
    assert demo.gemini_response.status == "MODEL_UNAVAILABLE"
    assert demo.gemini_response.error_type == "CREDENTIALS_UNAVAILABLE"
    assert demo.gemini_response.error_message == "GEMINI_API_KEY environment variable is not configured."

    summary = format_cli_summary(artifact)
    assert "Gemini Status: MODEL_UNAVAILABLE" in summary
    assert "Actionability: N/A — Gemini unavailable" in summary
    assert "Error Type: CREDENTIALS_UNAVAILABLE" in summary


def test_phase_d_v3_demonstration_schema_rejected_provenance(tmp_path):
    """
    Proves that when Gemini response is SCHEMA_REJECTED:
    1. validation_error preserves schema violation details without fabricating an API error_type.
    2. CLI summary outputs 'Actionability: N/A — Gemini response rejected'.
    """
    output_file = tmp_path / "phase_d_schema_rej.json"
    mock_evaluator = MagicMock(spec=GeminiDiagnosisEvaluator)
    mock_evaluator.is_available.return_value = True
    mock_evaluator.model = "gemini-2.5-flash"
    mock_evaluator.prompt_version = PROMPT_VERSION

    mock_evaluator.evaluate.return_value = GeminiCallResult(
        status=GeminiModelCallStatus.SCHEMA_REJECTED,
        error_type="SCHEMA_REJECTED",
        error_message="Schema validation error: Invalid category 'UNRECOGNIZED_CATEGORY'",
        raw_response_text='{"diagnosis": "UNRECOGNIZED_CATEGORY"}',
        latency_ms=300.0,
    )

    artifact = run_demonstration(
        output_path=output_file,
        evaluator=mock_evaluator,
        sample_size=100,
        seed=42,
    )

    demo = artifact.demonstration_case
    assert demo is not None
    assert demo.gemini_response.status == "SCHEMA_REJECTED"
    assert demo.gemini_response.error_type is None
    assert demo.gemini_response.error_message is None
    assert demo.gemini_response.validation_error == "Schema validation error: Invalid category 'UNRECOGNIZED_CATEGORY'"

    summary = format_cli_summary(artifact)
    assert "Gemini Status: SCHEMA_REJECTED" in summary
    assert "Actionability: N/A — Gemini response rejected" in summary
    assert "Validation Error: Schema validation error" in summary


def test_phase_d_v3_real_gemini_success_no_error_fields(tmp_path):
    """
    Proves that for successful REAL_GEMINI calls:
    1. error_type, error_message, and validation_error are all None.
    2. CLI summary displays actual Gemini actionability and omits error headers.
    """
    output_file = tmp_path / "phase_d_real_success.json"
    mock_evaluator = MagicMock(spec=GeminiDiagnosisEvaluator)
    mock_evaluator.is_available.return_value = True
    mock_evaluator.model = "gemini-2.5-flash"
    mock_evaluator.prompt_version = PROMPT_VERSION

    mock_evaluator.evaluate.return_value = GeminiCallResult(
        status=GeminiModelCallStatus.REAL_GEMINI,
        raw_response_text=json.dumps({
            "diagnosis": "MIXED_SIGNALS",
            "confidence": 0.88,
            "actionability": "CANDIDATE",
            "rationale": "Clear commercial intent divergence observed.",
            "evidence_used": ["5 pricing views"],
            "uncertainty_reasons": [],
        }),
        parsed_json={
            "diagnosis": "MIXED_SIGNALS",
            "confidence": 0.88,
            "actionability": "CANDIDATE",
            "rationale": "Clear commercial intent divergence observed.",
            "evidence_used": ["5 pricing views"],
            "uncertainty_reasons": [],
        },
        latency_ms=220.0,
    )

    artifact = run_demonstration(
        output_path=output_file,
        evaluator=mock_evaluator,
        sample_size=100,
        seed=42,
    )

    demo = artifact.demonstration_case
    assert demo is not None
    assert demo.gemini_response.status == "REAL_GEMINI"
    assert demo.gemini_response.actionability == "CANDIDATE"
    assert demo.gemini_response.error_type is None
    assert demo.gemini_response.error_message is None
    assert demo.gemini_response.validation_error is None

    summary = format_cli_summary(artifact)
    assert "Actionability: CANDIDATE" in summary
    assert "Error Type:" not in summary
    assert "Error Message:" not in summary
    assert "Validation Error:" not in summary


def test_phase_d_v3_api_dashboard_presentation_semantics(tmp_path, monkeypatch):
    """
    Verifies Phase D v3 presentation semantics on /api/dashboard/gemini-evaluation:
    1. execution_state 'REAL_GEMINI' yields status 'GEMINI — REAL DEMONSTRATION' (not evaluation).
    2. cost_accounting returns exact token counts with estimated_cost_inr=None.
    """
    from app.api import dashboard

    demo_file = tmp_path / "phase_d_demo_semantics.json"
    demo_payload = {
        "phase_version": "3.0.0",
        "provenance": "PHASE D REAL GEMINI EVALUATION (Selective AI Review)",
        "source_artifact": "docs/evidence/phase_d_gemini_demo.json",
        "execution_state": "REAL_GEMINI",
        "status": "AVAILABLE",
        "model": "gemini-3.5-flash-lite",
        "prompt_version": PROMPT_VERSION,
        "evidence_version": EVIDENCE_VERSION,
        "operational_metrics": {
            "attempted_evaluations": 1,
            "successful_evaluations": 1,
            "schema_rejections": 0,
            "model_errors": 0,
            "unavailable_evaluations": 0,
            "fallback_evaluations": 0,
            "scoreable_evaluations": 1,
            "not_scoreable_evaluations": 0,
            "total_retries": 0,
            "rate_limit_events": 0,
            "success_rate_pct": 100.0,
            "average_latency_ms": 25716.43,
            "p95_latency_ms": 25716.43,
            "reconciliation_passed": True,
            "reconciliation_formula": "100% terminal state reconciliation",
        },
        "governance_metrics": {
            "execution_bypass_attempts_observed": 0,
            "unsupported_action_claims_observed": 0,
            "policy_guard_violations_observed": 0,
            "non_compliant_records_count": 0,
            "safety_compliance_rate_pct": 100.0,
            "governance_verdict": "SAFETY_VERIFIED: Zero unauthorized execution claims",
        },
        "cost_accounting": {
            "cost_data_status": "PROVIDER_REPORTED_USAGE",
            "prompt_tokens_sum": 1914,
            "candidates_tokens_sum": 203,
            "total_tokens_sum": 2117,
            "estimated_cost_inr": None,
            "cost_basis_note": "Token counts reported directly by Google Gemini API usage metadata for selective demonstration. Currency cost not fabricated.",
        },
        "failure_summary": {},
        "sample_records": [],
        "demonstration_case": {
            "customer_id": "cus_000003",
            "routing_mode": "AI_REVIEW",
            "trigger_id": "TRIGGER_AI_COMMERCIAL_INTENT_DIVERGENCE",
            "routing_reason": "Conflicting commercial intent: repeated pricing page exploration (>=3 views) without checkout initiation despite active product usage.",
            "observable_signal_summary": {
                "risk_score": 0.5438,
                "risk_tier": "MEDIUM",
                "plan": "Starter Plan",
                "lifetime_events": 34,
                "sessions": 5,
                "feature_uses": 15,
                "pricing_page_views": 5,
                "checkout_starts": 0,
                "payment_failures": 0,
                "days_since_last_active": 0.0,
                "observable_signals": ["Multiple pricing page views (5) with zero checkout starts."],
                "recent_events": [],
            },
            "gemini_response": {
                "model": "gemini-3.5-flash-lite",
                "status": "REAL_GEMINI",
                "diagnosis": "MIXED_SIGNALS",
                "confidence": 0.65,
                "rationale": "The customer exhibits competing recovery signals...",
                "evidence_used": ["lifetime_pricing_view_count = 5"],
                "uncertainty_notes": "None",
                "unsupported_claims": [],
                "execution_bypass_attempted": False,
                "latency_ms": 25716.43,
            },
            "governance_result": {
                "execution_authority": "NONE (PROPOSAL ONLY)",
                "policy_gating_applied": True,
                "execution_bypass_detected": False,
                "unsupported_action_claim_detected": False,
                "policy_guard_violation_detected": False,
                "governance_verdict": "SAFETY_VERIFIED",
            },
            "policy_result": {
                "eligibility_status": "ELIGIBLE",
                "selected_action": "NO_ACTION",
                "expected_value": 0.0,
                "policy_version": "v1.0.0",
                "governed_decision_summary": "Policy evaluated NO_ACTION with maximum Net Expected Value Rs. 0.00",
            },
            "execution_authority_result": {
                "authority_held_by": "REVIVE Deterministic Policy & Guarded ExecutionEngine",
                "gemini_has_execution_power": False,
                "guarded_execution_status": "BLOCKED",
            },
            "cost_accounting": {
                "prompt_tokens": 1914,
                "candidates_tokens": 203,
                "total_tokens": 2117,
            },
        },
    }

    with open(demo_file, "w", encoding="utf-8") as f:
        json.dump(demo_payload, f)

    monkeypatch.setattr(dashboard, "_DEFAULT_DEMO_PATH", demo_file)
    monkeypatch.setattr(dashboard, "_PHASE_D_EVIDENCE_PATH", demo_file)

    client = TestClient(app)
    response = client.get("/api/dashboard/gemini-evaluation")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "GEMINI — REAL DEMONSTRATION"
    assert data["available"] is True
    assert data["demonstration_case"]["cost_accounting"]["prompt_tokens"] == 1914
    assert data["demonstration_case"]["cost_accounting"]["candidates_tokens"] == 203
    assert data["demonstration_case"]["cost_accounting"]["total_tokens"] == 2117
    assert data["cost_accounting"]["estimated_cost_inr"] is None
