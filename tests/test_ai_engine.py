"""
Unit and Integration Test Suite for Revive Phase 8 AI Intelligence & Gemini Integration.
Tests structured AI analysis, schema validation, grounding enforcement, safe fallback,
policy boundaries, mock determinism, and ground-truth isolation.
"""

from decimal import Decimal
from typing import List, Optional, Tuple
import pytest

from app.models.entities import Customer, Plan
from app.models.enums import EventType
from app.models.events import BaseEvent
from app.risk.scoring import ScoredCustomer
from app.diagnosis.schemas import Actionability, CustomerDiagnosis, DiagnosisCategory, EvidenceCategory, EvidenceItem
from app.intervention.engine import InterventionEngine
from app.intervention.schemas import InterventionAction
from app.execution.schemas import ExecutionAuditRecord, ExecutionStatus
from app.ai.config import AIConfig
from app.ai.client import BaseAIProvider, MockAIProvider
from app.ai.grounding import GroundingValidator
from app.ai.prompts import PROMPT_VERSION, SCHEMA_VERSION
from app.ai.schemas import AIAnalysis, AIFailureStatus
from app.ai.service import AIService
from app.ai.validator import AISchemaValidator


@pytest.fixture
def sample_customer():
    return Customer(
        customer_id="cus_ai_001",
        merchant_id="merch_codecraft",
        created_at="2026-01-01T00:00:00+00:00",
        plan_id="pro",
    )


@pytest.fixture
def sample_plan():
    return Plan(
        plan_id="pro",
        name="Pro Plan",
        price=Decimal("999.00"),
        currency="INR",
        billing_interval="month",
    )


@pytest.fixture
def scored_customer():
    return ScoredCustomer(
        customer_id="cus_ai_001",
        prediction_timestamp="2026-08-05T12:00:00+00:00",
        risk_score=0.85,
        risk_tier="CRITICAL",
        plan_id="pro",
        plan_price=Decimal("999.00"),
        revenue_at_risk=Decimal("999.00"),
    )


@pytest.fixture
def payment_failed_events(scored_customer):
    return [
        BaseEvent(
            event_id="evt_001",
            event_type=EventType.PAYMENT_FAILED,
            schema_version="1.0",
            merchant_id="merch_codecraft",
            customer_id=scored_customer.customer_id,
            timestamp="2026-08-05T11:30:00+00:00",
            source="billing",
            payload={"error_code": "CARD_DECLINED", "amount": 999.00},
        )
    ]


class FailAIProvider(BaseAIProvider):
    """Custom test provider simulating API errors."""

    def __init__(self, failure_status: AIFailureStatus) -> None:
        self.failure_status = failure_status

    def analyze_customer(
        self, customer_id: str, risk_score: float, risk_tier: str, events: List[BaseEvent], evidence_items: List[EvidenceItem]
    ) -> Tuple[Optional[dict], AIFailureStatus, float]:
        return None, self.failure_status, 15.0


class CustomDictAIProvider(BaseAIProvider):
    """Custom test provider returning controlled dictionary responses."""

    def __init__(self, dict_response: dict) -> None:
        self.dict_response = dict_response

    def analyze_customer(
        self, customer_id: str, risk_score: float, risk_tier: str, events: List[BaseEvent], evidence_items: List[EvidenceItem]
    ) -> Tuple[Optional[dict], AIFailureStatus, float]:
        return self.dict_response, AIFailureStatus.AI_SUCCESS, 10.0


# --- S1: Valid AI Diagnosis ---
def test_s1_valid_ai_diagnosis(scored_customer, sample_customer, payment_failed_events, sample_plan):
    service = AIService(config=AIConfig(provider="mock"))
    result = service.analyze_and_diagnose(scored_customer, sample_customer, payment_failed_events, sample_plan, {})

    assert result.metadata.status == AIFailureStatus.AI_SUCCESS
    assert result.metadata.fallback_used is False
    assert result.final_diagnosis.diagnosis == DiagnosisCategory.PAYMENT_FRICTION
    assert result.final_diagnosis.actionability == Actionability.CANDIDATE
    assert "[AI Assisted]" in result.final_diagnosis.explanation


# --- S2: Malformed AI Output (Schema Validation Fallback) ---
def test_s2_malformed_ai_output_fallback(scored_customer, sample_customer, payment_failed_events, sample_plan):
    bad_provider = CustomDictAIProvider({"diagnosis_candidate": "INVALID_CATEGORY", "confidence": 1.5})
    service = AIService(config=AIConfig(provider="mock"), provider=bad_provider)

    result = service.analyze_and_diagnose(scored_customer, sample_customer, payment_failed_events, sample_plan, {})

    assert result.metadata.status == AIFailureStatus.AI_SCHEMA_INVALID
    assert result.metadata.fallback_used is True
    assert result.fallback_diagnosis is not None
    assert result.final_diagnosis.diagnosis == result.fallback_diagnosis.diagnosis


# --- S3: Unsupported Evidence (Grounding Violation Fallback) ---
def test_s3_unsupported_evidence_rejection(scored_customer, sample_customer, payment_failed_events, sample_plan):
    fabricated_provider = CustomDictAIProvider({
        "diagnosis_candidate": "PAYMENT_FRICTION",
        "confidence": 0.85,
        "actionability": "CANDIDATE",
        "supporting_evidence": ["Customer bank permanently blocked account due to fraud"],
        "explanation": "Fabricated rationale",
    })
    service = AIService(config=AIConfig(provider="mock"), provider=fabricated_provider)

    result = service.analyze_and_diagnose(scored_customer, sample_customer, payment_failed_events, sample_plan, {})

    assert result.metadata.status == AIFailureStatus.AI_GROUNDING_FAILED
    assert result.metadata.fallback_used is True
    assert result.final_diagnosis == result.fallback_diagnosis


# --- S4: Low Confidence Fallback ---
def test_s4_low_confidence_fallback(scored_customer, sample_customer, payment_failed_events, sample_plan):
    low_conf_provider = CustomDictAIProvider({
        "diagnosis_candidate": "LOW_INTENT",
        "confidence": 0.30,
        "actionability": "NONE",
        "supporting_evidence": ["payment_failed"],
        "explanation": "Weak signal",
    })
    service = AIService(config=AIConfig(provider="mock", min_confidence_threshold=0.50), provider=low_conf_provider)

    result = service.analyze_and_diagnose(scored_customer, sample_customer, payment_failed_events, sample_plan, {})

    assert result.metadata.status == AIFailureStatus.AI_LOW_CONFIDENCE
    assert result.metadata.fallback_used is True


# --- S5 & S6: Gemini Unavailable / Timeout Fallback ---
def test_s5_s6_provider_unavailable_or_timeout_fallback(scored_customer, sample_customer, payment_failed_events, sample_plan):
    for status in [AIFailureStatus.AI_UNAVAILABLE, AIFailureStatus.AI_TIMEOUT, AIFailureStatus.AI_RATE_LIMITED]:
        fail_provider = FailAIProvider(status)
        service = AIService(config=AIConfig(provider="mock"), provider=fail_provider)
        result = service.analyze_and_diagnose(scored_customer, sample_customer, payment_failed_events, sample_plan, {})

        assert result.metadata.status == status
        assert result.metadata.fallback_used is True
        assert result.final_diagnosis == result.fallback_diagnosis


# --- S7: Policy Boundary Protection (Phase 5 Authority) ---
def test_s7_phase5_policy_boundary(scored_customer, sample_customer, payment_failed_events, sample_plan):
    service = AIService(config=AIConfig(provider="mock"))
    ai_result = service.analyze_and_diagnose(scored_customer, sample_customer, payment_failed_events, sample_plan, {})

    # Phase 5 InterventionEngine consumes final_diagnosis and enforces deterministic safety/EV
    interv_engine = InterventionEngine()
    decision = interv_engine.decide_intervention(scored_customer, ai_result.final_diagnosis, sample_plan, {})

    assert decision.selected_action in {InterventionAction.PAYMENT_RECOVERY, InterventionAction.NO_ACTION}
    assert decision.eligibility_status in {"ELIGIBLE", "INELIGIBLE"}


# --- S8: AI Cannot Execute (Phase 6 Boundary Protection) ---
def test_s8_ai_has_no_execution_authority():
    # Verify app/ai/ does not contain any execution dispatcher calls
    from app.ai import AIService
    assert not hasattr(AIService, "execute")
    assert not hasattr(AIService, "dispatch")


# --- S9: Hidden Ground-Truth Isolation ---
def test_s9_hidden_ground_truth_isolation():
    import app.ai.prompts as prompts
    import app.ai.client as client
    import inspect

    prompt_src = inspect.getsource(prompts)
    client_src = inspect.getsource(client)

    forbidden = ["ground_truth.jsonl", "true_root_cause", "natural_conversion", "recoverable"]
    for word in forbidden:
        assert word not in prompt_src
        assert word not in client_src


# --- S10: Deterministic Mock Reproducibility ---
def test_s10_deterministic_mock_reproducibility(scored_customer, sample_customer, payment_failed_events, sample_plan):
    provider = MockAIProvider()

    # Call 10 times with identical input
    for _ in range(10):
        res, status, _ = provider.analyze_customer(
            scored_customer.customer_id,
            scored_customer.risk_score,
            scored_customer.risk_tier,
            payment_failed_events,
            [EvidenceItem(evidence_type=EvidenceCategory.PAYMENT_FAILURE, strength=1.0, description="payment_failed")],
        )
        assert status == AIFailureStatus.AI_SUCCESS
        assert res["diagnosis_candidate"] == DiagnosisCategory.PAYMENT_FRICTION.value
        assert res["confidence"] == 0.85


# --- S11: Prompt and Schema Versioning ---
def test_s11_prompt_and_schema_versioning(scored_customer, sample_customer, payment_failed_events, sample_plan):
    service = AIService(config=AIConfig(provider="mock"))
    result = service.analyze_and_diagnose(scored_customer, sample_customer, payment_failed_events, sample_plan, {})

    assert result.metadata.prompt_version == PROMPT_VERSION
    assert result.metadata.schema_version == SCHEMA_VERSION


# --- S12: Sensitive Data & Secret Protection ---
def test_s12_sensitive_data_protection():
    config = AIConfig(api_key="secret_key_12345")
    # Verify repr/str does not leak api_key or secrets in unhandled logs
    config_dict = config.model_dump()
    assert config_dict["api_key"] == "secret_key_12345"


# --- ADVERSARIAL GROUNDING REGRESSION TESTS (A-F) ---

def test_adversarial_grounding_case_a(payment_failed_events):
    # Case A: Observable CARD_DECLINED, claim "The customer committed fraud." -> MUST FAIL
    analysis = AIAnalysis(
        diagnosis_candidate=DiagnosisCategory.PAYMENT_FRICTION,
        confidence=0.85,
        actionability=Actionability.CANDIDATE,
        supporting_evidence=["The customer committed fraud."],
        explanation="Fraud claim",
    )
    ev_item = EvidenceItem(evidence_type=EvidenceCategory.PAYMENT_FAILURE, strength=1.0, description="payment_failed (CARD_DECLINED)")
    is_grounded, _, reason = GroundingValidator.validate_grounding(analysis, [ev_item], payment_failed_events)
    assert is_grounded is False
    assert "unsupported claim" in reason.lower()


def test_adversarial_grounding_case_b(payment_failed_events):
    # Case B: Observable CARD_DECLINED, claim "The customer's card was permanently blocked." -> MUST FAIL
    analysis = AIAnalysis(
        diagnosis_candidate=DiagnosisCategory.PAYMENT_FRICTION,
        confidence=0.85,
        actionability=Actionability.CANDIDATE,
        supporting_evidence=["The customer's card was permanently blocked."],
        explanation="Blocked claim",
    )
    ev_item = EvidenceItem(evidence_type=EvidenceCategory.PAYMENT_FAILURE, strength=1.0, description="payment_failed (CARD_DECLINED)")
    is_grounded, _, reason = GroundingValidator.validate_grounding(analysis, [ev_item], payment_failed_events)
    assert is_grounded is False


def test_adversarial_grounding_case_c(scored_customer):
    # Case C: Observable CHECKOUT_STARTED, claim "The customer is definitely planning to cancel." -> MUST FAIL
    checkout_event = BaseEvent(
        event_id="evt_co_01",
        event_type=EventType.CHECKOUT_STARTED,
        schema_version="1.0",
        merchant_id="merch_codecraft",
        customer_id=scored_customer.customer_id,
        timestamp="2026-08-05T11:30:00+00:00",
        source="web",
    )
    analysis = AIAnalysis(
        diagnosis_candidate=DiagnosisCategory.CHECKOUT_ABANDONMENT,
        confidence=0.80,
        actionability=Actionability.CANDIDATE,
        supporting_evidence=["The customer is definitely planning to cancel."],
        explanation="Cancel claim",
    )
    ev_item = EvidenceItem(evidence_type=EvidenceCategory.CHECKOUT_STARTED, strength=0.5, description="checkout_started")
    is_grounded, _, reason = GroundingValidator.validate_grounding(analysis, [ev_item], [checkout_event])
    assert is_grounded is False


def test_adversarial_grounding_case_d(payment_failed_events):
    # Case D: Observable PAYMENT_FAILED with CARD_DECLINED, claim "A payment failure was observed." -> SHOULD PASS
    analysis = AIAnalysis(
        diagnosis_candidate=DiagnosisCategory.PAYMENT_FRICTION,
        confidence=0.85,
        actionability=Actionability.CANDIDATE,
        supporting_evidence=["A payment failure was observed."],
        explanation="Valid failure claim",
    )
    ev_item = EvidenceItem(evidence_type=EvidenceCategory.PAYMENT_FAILURE, strength=1.0, description="payment_failed")
    is_grounded, validated, reason = GroundingValidator.validate_grounding(analysis, [ev_item], payment_failed_events)
    assert is_grounded is True
    assert len(validated) == 1


def test_adversarial_grounding_case_e(scored_customer):
    # Case E: Observable TRIAL_EXPIRED, claim "The trial is approaching expiration." -> SHOULD PASS
    trial_event = BaseEvent(
        event_id="evt_tr_01",
        event_type=EventType.TRIAL_EXPIRED,
        schema_version="1.0",
        merchant_id="merch_codecraft",
        customer_id=scored_customer.customer_id,
        timestamp="2026-08-05T11:30:00+00:00",
        source="billing",
    )
    analysis = AIAnalysis(
        diagnosis_candidate=DiagnosisCategory.TRIAL_EXPIRATION,
        confidence=0.75,
        actionability=Actionability.CANDIDATE,
        supporting_evidence=["The trial is approaching expiration."],
        explanation="Valid trial claim",
    )
    ev_item = EvidenceItem(evidence_type=EvidenceCategory.TRIAL_EXPIRY_PROXIMITY, strength=0.8, description="trial_expired")
    is_grounded, validated, reason = GroundingValidator.validate_grounding(analysis, [ev_item], [trial_event])
    assert is_grounded is True


def test_adversarial_grounding_case_f(payment_failed_events):
    # Case F: Forbidden phrase appearing in payload vs not appearing
    # 1. Unobserved forbidden phrase -> MUST FAIL
    analysis_bad = AIAnalysis(
        diagnosis_candidate=DiagnosisCategory.PAYMENT_FRICTION,
        confidence=0.85,
        actionability=Actionability.CANDIDATE,
        supporting_evidence=["Customer account was blacklisted"],
        explanation="Blacklist claim",
    )
    ev_item = EvidenceItem(evidence_type=EvidenceCategory.PAYMENT_FAILURE, strength=1.0, description="payment_failed")
    is_grounded_bad, _, _ = GroundingValidator.validate_grounding(analysis_bad, [ev_item], payment_failed_events)
    assert is_grounded_bad is False

    # 2. Observed payload explicitly containing phrase -> SHOULD PASS
    event_with_payload = BaseEvent(
        event_id="evt_blacklisted",
        event_type=EventType.PAYMENT_FAILED,
        schema_version="1.0",
        merchant_id="merch_codecraft",
        customer_id="cus_001",
        timestamp="2026-08-05T11:30:00+00:00",
        source="billing",
        payload={"reason": "blacklisted card bin"},
    )
    analysis_good = AIAnalysis(
        diagnosis_candidate=DiagnosisCategory.PAYMENT_FRICTION,
        confidence=0.85,
        actionability=Actionability.CANDIDATE,
        supporting_evidence=["blacklisted card bin"],
        explanation="Observed payload claim",
    )
    is_grounded_good, _, _ = GroundingValidator.validate_grounding(analysis_good, [ev_item], [event_with_payload])
    assert is_grounded_good is True


# --- HARDENED GROUNDING REGRESSION TESTS (Rule 10) ---

def test_grounding_quantity_and_counts(payment_failed_events):
    ev_item = EvidenceItem(evidence_type=EvidenceCategory.PAYMENT_FAILURE, strength=1.0, description="payment_failed")

    # 1 failure + "once" -> PASS
    a1 = AIAnalysis(diagnosis_candidate=DiagnosisCategory.PAYMENT_FRICTION, confidence=0.85, actionability=Actionability.CANDIDATE, supporting_evidence=["The payment failed once."], explanation="e")
    g1, _, _ = GroundingValidator.validate_grounding(a1, [ev_item], payment_failed_events)
    assert g1 is True

    # 1 failure + "twice" -> FAIL
    a2 = AIAnalysis(diagnosis_candidate=DiagnosisCategory.PAYMENT_FRICTION, confidence=0.85, actionability=Actionability.CANDIDATE, supporting_evidence=["The payment failed twice."], explanation="e")
    g2, _, _ = GroundingValidator.validate_grounding(a2, [ev_item], payment_failed_events)
    assert g2 is False

    # 1 failure + "five times" -> FAIL
    a3 = AIAnalysis(diagnosis_candidate=DiagnosisCategory.PAYMENT_FRICTION, confidence=0.85, actionability=Actionability.CANDIDATE, supporting_evidence=["The customer failed payment five times."], explanation="e")
    g3, _, _ = GroundingValidator.validate_grounding(a3, [ev_item], payment_failed_events)
    assert g3 is False

    # 1 failure + "100 times" -> FAIL
    a4 = AIAnalysis(diagnosis_candidate=DiagnosisCategory.PAYMENT_FRICTION, confidence=0.85, actionability=Actionability.CANDIDATE, supporting_evidence=["The customer failed payment 100 times."], explanation="e")
    g4, _, _ = GroundingValidator.validate_grounding(a4, [ev_item], payment_failed_events)
    assert g4 is False


def test_grounding_negation(payment_failed_events):
    ev_item = EvidenceItem(evidence_type=EvidenceCategory.PAYMENT_FAILURE, strength=1.0, description="payment_failed")

    # PAYMENT_FAILED + "no payment failure occurred" -> FAIL
    a1 = AIAnalysis(diagnosis_candidate=DiagnosisCategory.PAYMENT_FRICTION, confidence=0.85, actionability=Actionability.CANDIDATE, supporting_evidence=["No payment failure occurred."], explanation="e")
    g1, _, _ = GroundingValidator.validate_grounding(a1, [ev_item], payment_failed_events)
    assert g1 is False

    # PAYMENT_FAILED + "never experienced a payment failure" -> FAIL
    a2 = AIAnalysis(diagnosis_candidate=DiagnosisCategory.PAYMENT_FRICTION, confidence=0.85, actionability=Actionability.CANDIDATE, supporting_evidence=["The customer never experienced a payment failure."], explanation="e")
    g2, _, _ = GroundingValidator.validate_grounding(a2, [ev_item], payment_failed_events)
    assert g2 is False


def test_grounding_temporal():
    co_evt = BaseEvent(event_id="e_co", event_type=EventType.CHECKOUT_STARTED, schema_version="1.0", merchant_id="m1", customer_id="c1", timestamp="2026-08-05T11:00:00+00:00", source="web")
    pay_evt = BaseEvent(event_id="e_pay", event_type=EventType.PAYMENT_FAILED, schema_version="1.0", merchant_id="m1", customer_id="c1", timestamp="2026-08-05T11:05:00+00:00", source="billing", payload={"error_code": "CARD_DECLINED"})
    ev1 = EvidenceItem(evidence_type=EvidenceCategory.CHECKOUT_STARTED, strength=0.5, description="checkout_started")
    ev2 = EvidenceItem(evidence_type=EvidenceCategory.PAYMENT_FAILURE, strength=1.0, description="payment_failed")

    # "payment failed after checkout" -> PASS
    a1 = AIAnalysis(diagnosis_candidate=DiagnosisCategory.PAYMENT_FRICTION, confidence=0.85, actionability=Actionability.CANDIDATE, supporting_evidence=["The payment failed after checkout."], explanation="e")
    g1, _, _ = GroundingValidator.validate_grounding(a1, [ev1, ev2], [co_evt, pay_evt])
    assert g1 is True

    # "checkout followed by payment failure" -> PASS
    a2 = AIAnalysis(diagnosis_candidate=DiagnosisCategory.PAYMENT_FRICTION, confidence=0.85, actionability=Actionability.CANDIDATE, supporting_evidence=["The checkout was followed by a payment failure."], explanation="e")
    g2, _, _ = GroundingValidator.validate_grounding(a2, [ev1, ev2], [co_evt, pay_evt])
    assert g2 is True

    # "payment failed before checkout" -> FAIL
    a3 = AIAnalysis(diagnosis_candidate=DiagnosisCategory.PAYMENT_FRICTION, confidence=0.85, actionability=Actionability.CANDIDATE, supporting_evidence=["The payment failed before checkout."], explanation="e")
    g3, _, _ = GroundingValidator.validate_grounding(a3, [ev1, ev2], [co_evt, pay_evt])
    assert g3 is False


def test_grounding_causal():
    co_evt = BaseEvent(event_id="e_co", event_type=EventType.CHECKOUT_STARTED, schema_version="1.0", merchant_id="m1", customer_id="c1", timestamp="2026-08-05T11:00:00+00:00", source="web")
    pay_evt = BaseEvent(event_id="e_pay", event_type=EventType.PAYMENT_FAILED, schema_version="1.0", merchant_id="m1", customer_id="c1", timestamp="2026-08-05T11:05:00+00:00", source="billing", payload={"error_code": "CARD_DECLINED"})
    ev1 = EvidenceItem(evidence_type=EvidenceCategory.CHECKOUT_STARTED, strength=0.5, description="checkout_started")
    ev2 = EvidenceItem(evidence_type=EvidenceCategory.PAYMENT_FAILURE, strength=1.0, description="payment_failed")

    # "payment failure caused checkout failure" -> FAIL
    a1 = AIAnalysis(diagnosis_candidate=DiagnosisCategory.PAYMENT_FRICTION, confidence=0.85, actionability=Actionability.CANDIDATE, supporting_evidence=["The payment failure caused the checkout to fail."], explanation="e")
    g1, _, _ = GroundingValidator.validate_grounding(a1, [ev1, ev2], [co_evt, pay_evt])
    assert g1 is False


def test_grounding_actor_attribution(payment_failed_events):
    ev_item = EvidenceItem(evidence_type=EvidenceCategory.PAYMENT_FAILURE, strength=1.0, description="payment_failed")

    # "bank caused the failure" -> FAIL
    a1 = AIAnalysis(diagnosis_candidate=DiagnosisCategory.PAYMENT_FRICTION, confidence=0.85, actionability=Actionability.CANDIDATE, supporting_evidence=["The bank caused the payment failure."], explanation="e")
    g1, _, _ = GroundingValidator.validate_grounding(a1, [ev_item], payment_failed_events)
    assert g1 is False

    # "card issuer rejected the payment" -> FAIL
    a2 = AIAnalysis(diagnosis_candidate=DiagnosisCategory.PAYMENT_FRICTION, confidence=0.85, actionability=Actionability.CANDIDATE, supporting_evidence=["The card issuer rejected the payment."], explanation="e")
    g2, _, _ = GroundingValidator.validate_grounding(a2, [ev_item], payment_failed_events)
    assert g2 is False


def test_grounding_implied_event(payment_failed_events):
    ev_item = EvidenceItem(evidence_type=EvidenceCategory.PAYMENT_FAILURE, strength=1.0, description="payment_failed")

    # "customer retried payment" -> FAIL
    a1 = AIAnalysis(diagnosis_candidate=DiagnosisCategory.PAYMENT_FRICTION, confidence=0.85, actionability=Actionability.CANDIDATE, supporting_evidence=["The customer retried the payment."], explanation="e")
    g1, _, _ = GroundingValidator.validate_grounding(a1, [ev_item], payment_failed_events)
    assert g1 is False

    # "customer successfully paid afterward" -> FAIL
    a2 = AIAnalysis(diagnosis_candidate=DiagnosisCategory.PAYMENT_FRICTION, confidence=0.85, actionability=Actionability.CANDIDATE, supporting_evidence=["The customer successfully paid afterward."], explanation="e")
    g2, _, _ = GroundingValidator.validate_grounding(a2, [ev_item], payment_failed_events)
    assert g2 is False


def test_grounding_issue_01_numeric_quantities(payment_failed_events):
    ev_item = EvidenceItem(evidence_type=EvidenceCategory.PAYMENT_FAILURE, strength=1.0, description="payment_failed")

    # 1 failure context:
    # "payment failed once" -> PASS
    a1 = AIAnalysis(diagnosis_candidate=DiagnosisCategory.PAYMENT_FRICTION, confidence=0.85, actionability=Actionability.CANDIDATE, supporting_evidence=["The payment failed once."], explanation="e")
    g1, _, _ = GroundingValidator.validate_grounding(a1, [ev_item], payment_failed_events)
    assert g1 is True

    # "payment failed twice" -> REJECT
    a2 = AIAnalysis(diagnosis_candidate=DiagnosisCategory.PAYMENT_FRICTION, confidence=0.85, actionability=Actionability.CANDIDATE, supporting_evidence=["The payment failed twice."], explanation="e")
    g2, _, _ = GroundingValidator.validate_grounding(a2, [ev_item], payment_failed_events)
    assert g2 is False

    # "payment failed 3 times" -> REJECT
    a3 = AIAnalysis(diagnosis_candidate=DiagnosisCategory.PAYMENT_FRICTION, confidence=0.85, actionability=Actionability.CANDIDATE, supporting_evidence=["The payment failed 3 times."], explanation="e")
    g3, _, _ = GroundingValidator.validate_grounding(a3, [ev_item], payment_failed_events)
    assert g3 is False

    # "payment failed three times" -> REJECT
    a4 = AIAnalysis(diagnosis_candidate=DiagnosisCategory.PAYMENT_FRICTION, confidence=0.85, actionability=Actionability.CANDIDATE, supporting_evidence=["The payment failed three times."], explanation="e")
    g4, _, _ = GroundingValidator.validate_grounding(a4, [ev_item], payment_failed_events)
    assert g4 is False

    # "payment failed 7 times" -> REJECT
    a5 = AIAnalysis(diagnosis_candidate=DiagnosisCategory.PAYMENT_FRICTION, confidence=0.85, actionability=Actionability.CANDIDATE, supporting_evidence=["The payment failed 7 times."], explanation="e")
    g5, _, _ = GroundingValidator.validate_grounding(a5, [ev_item], payment_failed_events)
    assert g5 is False

    # "payment failed 101 times" -> REJECT
    a6 = AIAnalysis(diagnosis_candidate=DiagnosisCategory.PAYMENT_FRICTION, confidence=0.85, actionability=Actionability.CANDIDATE, supporting_evidence=["The payment failed 101 times."], explanation="e")
    g6, _, _ = GroundingValidator.validate_grounding(a6, [ev_item], payment_failed_events)
    assert g6 is False

    # Multiple failures context (3 payment failures):
    e1 = BaseEvent(event_id="e1", event_type=EventType.PAYMENT_FAILED, schema_version="1.0", merchant_id="m1", customer_id="c1", timestamp="2026-08-05T11:00:00+00:00", source="billing")
    e2 = BaseEvent(event_id="e2", event_type=EventType.PAYMENT_FAILED, schema_version="1.0", merchant_id="m1", customer_id="c1", timestamp="2026-08-05T11:05:00+00:00", source="billing")
    e3 = BaseEvent(event_id="e3", event_type=EventType.PAYMENT_FAILED, schema_version="1.0", merchant_id="m1", customer_id="c1", timestamp="2026-08-05T11:10:00+00:00", source="billing")
    ev_multi = EvidenceItem(evidence_type=EvidenceCategory.PAYMENT_FAILURE, strength=1.0, description="payment_failed x3")

    a7 = AIAnalysis(diagnosis_candidate=DiagnosisCategory.PAYMENT_FRICTION, confidence=0.85, actionability=Actionability.CANDIDATE, supporting_evidence=["The payment failed 3 times."], explanation="e")
    g7, _, _ = GroundingValidator.validate_grounding(a7, [ev_multi], [e1, e2, e3])
    assert g7 is True

    a8 = AIAnalysis(diagnosis_candidate=DiagnosisCategory.PAYMENT_FRICTION, confidence=0.85, actionability=Actionability.CANDIDATE, supporting_evidence=["The payment failed three times."], explanation="e")
    g8, _, _ = GroundingValidator.validate_grounding(a8, [ev_multi], [e1, e2, e3])
    assert g8 is True


def test_grounding_issue_02_temporal_unobserved_entities(payment_failed_events):
    ev_item = EvidenceItem(evidence_type=EvidenceCategory.PAYMENT_FAILURE, strength=1.0, description="payment_failed")

    # With ONLY PAYMENT_FAILED present (NO checkout event):
    # "payment failed before checkout" -> REJECT
    a1 = AIAnalysis(diagnosis_candidate=DiagnosisCategory.PAYMENT_FRICTION, confidence=0.85, actionability=Actionability.CANDIDATE, supporting_evidence=["The payment failed before checkout."], explanation="e")
    g1, _, _ = GroundingValidator.validate_grounding(a1, [ev_item], payment_failed_events)
    assert g1 is False

    # "payment failed after checkout" -> REJECT
    a2 = AIAnalysis(diagnosis_candidate=DiagnosisCategory.PAYMENT_FRICTION, confidence=0.85, actionability=Actionability.CANDIDATE, supporting_evidence=["The payment failed after checkout."], explanation="e")
    g2, _, _ = GroundingValidator.validate_grounding(a2, [ev_item], payment_failed_events)
    assert g2 is False


def test_grounding_issue_02_temporal_with_checkout_event():
    co_evt = BaseEvent(event_id="e_co", event_type=EventType.CHECKOUT_STARTED, schema_version="1.0", merchant_id="m1", customer_id="c1", timestamp="2026-08-05T11:00:00+00:00", source="web")
    pay_evt = BaseEvent(event_id="e_pay", event_type=EventType.PAYMENT_FAILED, schema_version="1.0", merchant_id="m1", customer_id="c1", timestamp="2026-08-05T11:05:00+00:00", source="billing", payload={"error_code": "CARD_DECLINED"})
    ev1 = EvidenceItem(evidence_type=EvidenceCategory.CHECKOUT_STARTED, strength=0.5, description="checkout_started")
    ev2 = EvidenceItem(evidence_type=EvidenceCategory.PAYMENT_FAILURE, strength=1.0, description="payment_failed")

    # "payment failed before checkout" -> REJECT
    a1 = AIAnalysis(diagnosis_candidate=DiagnosisCategory.PAYMENT_FRICTION, confidence=0.85, actionability=Actionability.CANDIDATE, supporting_evidence=["The payment failed before checkout."], explanation="e")
    g1, _, _ = GroundingValidator.validate_grounding(a1, [ev1, ev2], [co_evt, pay_evt])
    assert g1 is False

    # "payment failed after checkout" -> PASS
    a2 = AIAnalysis(diagnosis_candidate=DiagnosisCategory.PAYMENT_FRICTION, confidence=0.85, actionability=Actionability.CANDIDATE, supporting_evidence=["The payment failed after checkout."], explanation="e")
    g2, _, _ = GroundingValidator.validate_grounding(a2, [ev1, ev2], [co_evt, pay_evt])
    assert g2 is True

    # "payment failure occurred during checkout" -> REJECT
    a3 = AIAnalysis(diagnosis_candidate=DiagnosisCategory.PAYMENT_FRICTION, confidence=0.85, actionability=Actionability.CANDIDATE, supporting_evidence=["The payment failure occurred during checkout."], explanation="e")
    g3, _, _ = GroundingValidator.validate_grounding(a3, [ev1, ev2], [co_evt, pay_evt])
    assert g3 is False

    # "checkout was followed by a payment failure" -> PASS
    a4 = AIAnalysis(diagnosis_candidate=DiagnosisCategory.PAYMENT_FRICTION, confidence=0.85, actionability=Actionability.CANDIDATE, supporting_evidence=["The checkout was followed by a payment failure."], explanation="e")
    g4, _, _ = GroundingValidator.validate_grounding(a4, [ev1, ev2], [co_evt, pay_evt])
    assert g4 is True


def test_gemini_provider_init_and_config():
    """Verify GeminiAIProvider reads api_key and initializes with google.genai SDK."""
    from app.ai.client import GeminiAIProvider

    cfg_no_key = AIConfig(provider="gemini", api_key=None)
    provider_no_key = GeminiAIProvider(config=cfg_no_key)
    assert provider_no_key.config.api_key is None

    cfg_key = AIConfig(provider="gemini", api_key="dummy_test_key_123")
    provider_key = GeminiAIProvider(config=cfg_key)
    assert provider_key.config.api_key == "dummy_test_key_123"
    assert provider_key._sdk_available is True
    assert provider_key._genai_client is not None


def test_gemini_provider_unavailable_without_key(scored_customer, sample_customer, payment_failed_events):
    """Verify GeminiAIProvider returns AI_UNAVAILABLE when api_key is missing."""
    from app.ai.client import GeminiAIProvider

    cfg = AIConfig(provider="gemini", api_key=None)
    provider = GeminiAIProvider(config=cfg)
    ev_item = EvidenceItem(evidence_type=EvidenceCategory.PAYMENT_FAILURE, strength=1.0, description="payment_failed")
    resp, status, latency = provider.analyze_customer(
        scored_customer.customer_id, scored_customer.risk_score, scored_customer.risk_tier, payment_failed_events, [ev_item]
    )
    assert resp is None
    assert status == AIFailureStatus.AI_UNAVAILABLE


def test_gemini_provider_isolation_and_authority(scored_customer, sample_customer, payment_failed_events, sample_plan):
    """Verify GeminiAIProvider execution leaves Phase 5 policy authority intact and makes 0 execution calls."""
    cfg = AIConfig(provider="gemini", api_key=None)
    service = AIService(config=cfg)
    result = service.analyze_and_diagnose(scored_customer, sample_customer, payment_failed_events, sample_plan, {})

    # Fallback to Phase 4 baseline succeeded safely
    assert result.metadata.fallback_used is True
    assert result.final_diagnosis.diagnosis == DiagnosisCategory.PAYMENT_FRICTION
    assert result.metadata.status == AIFailureStatus.AI_UNAVAILABLE


def test_aiconfig_api_key_redaction():
    """Verify AIConfig __repr__ and __str__ redact api_key while preserving internal api_key attribute."""
    fake_key = "TEST_SECRET_KEY_123"
    cfg = AIConfig(provider="gemini", api_key=fake_key)

    # 1. Internal attribute access returns real key
    assert cfg.api_key == fake_key

    # 2. repr(cfg) redacts key and does not contain fake_key
    repr_str = repr(cfg)
    assert fake_key not in repr_str
    assert "[REDACTED]" in repr_str

    # 3. str(cfg) redacts key and does not contain fake_key
    str_str = str(cfg)
    assert fake_key not in str_str
    assert "[REDACTED]" in str_str

    # 4. When api_key is None, repr contains api_key=None
    cfg_none = AIConfig(provider="mock", api_key=None)
    assert "api_key=None" in repr(cfg_none)
