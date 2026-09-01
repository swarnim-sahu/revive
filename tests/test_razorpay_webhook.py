"""
Unit & Integration Test Suite for REVIVE Phase A Razorpay Webhook Integration.
Tests retry-safe at-least-once delivery semantics, authoritative Plan correlation,
production-equivalent shared runtime context, exact decision correlation, payment_link.paid
recovery transitions, payment.captured non-recovery isolation, in-memory event-id deduplication,
append-only audit tracking, fail-closed security, and ground-truth isolation.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import hmac
import json
from typing import Any, Dict, List, Optional, Set, Tuple
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.api.webhooks import get_runtime_context, set_runtime_context, set_webhook_handler
from app.models.entities import Plan
from app.models.enums import EventType
from app.models.events import BaseEvent
from app.intervention.schemas import CandidateActionScore, InterventionAction, InterventionDecision
from app.execution.schemas import ExecutionAuditRecord, ExecutionStatus
from app.outcome.engine import OutcomeEngine
from app.outcome.schemas import AttributionStatus, OutcomeType
from app.integrations.razorpay.config import RazorpayConfig
from app.integrations.razorpay.webhook import (
    RazorpayWebhookHandler,
    ReviveRuntimeContext,
    WebhookAuditRecord,
    WebhookAuditStore,
    WebhookProcessingStatus,
    translate_razorpay_event_to_base_event,
    verify_webhook_signature,
)


@pytest.fixture
def webhook_secret():
    return "test_wh_secret_xyz12345"


@pytest.fixture
def razorpay_config(webhook_secret):
    return RazorpayConfig(
        environment="sandbox",
        key_id="rzp_test_KEY12345",
        key_secret="SECRET_KEY_99999",
        webhook_secret=webhook_secret,
    )


@pytest.fixture
def sample_plan_pro():
    return Plan(
        plan_id="pro",
        name="Pro Subscription Plan",
        price=Decimal("999.00"),
        currency="INR",
        billing_interval="monthly",
    )


@pytest.fixture
def sample_plan_business():
    return Plan(
        plan_id="business",
        name="Business Subscription Plan",
        price=Decimal("2499.00"),
        currency="INR",
        billing_interval="monthly",
    )


@pytest.fixture
def sample_decision():
    customer_id = "cus_wh_test_001"
    exec_ts = "2026-08-05T12:00:00+00:00"

    candidate = CandidateActionScore(
        action=InterventionAction.PAYMENT_RECOVERY,
        expected_value=Decimal("749.25"),
        recovery_probability_assumption=0.75,
        direct_cost=Decimal("3.00"),
        incentive_penalty_assumption=Decimal("0.00"),
        harm_penalty_assumption=Decimal("0.00"),
        is_eligible=True,
    )

    return InterventionDecision(
        customer_id=customer_id,
        decision_timestamp=exec_ts,
        risk_score=0.85,
        risk_tier="CRITICAL",
        revenue_at_risk=Decimal("999.00"),
        diagnosis="PAYMENT_FRICTION",
        diagnosis_confidence=1.0,
        diagnosis_actionability="candidate",
        eligibility_status="ELIGIBLE",
        selected_action=InterventionAction.PAYMENT_RECOVERY,
        expected_value=Decimal("749.25"),
        candidate_scores=[candidate],
        decision_reason="Payment failure recovery",
        supporting_evidence=["Card declined"],
    )


def generate_razorpay_payment_link_paid_payload(
    reference_id: str,
    event_id: str = "event_rzp_test_001",
    payment_id: str = "pay_test_9999",
    amount_paise: int = 99900,
    created_at_ts: int = 1785938400,  # 2026-08-05T14:00:00+00:00 (2h post-execution)
) -> Dict[str, Any]:
    """Construct authentic Razorpay payment_link.paid webhook payload dictionary."""
    return {
        "entity": "event",
        "account_id": "acc_test_1234",
        "event": "payment_link.paid",
        "contains": ["payment_link", "payment"],
        "payload": {
            "payment_link": {
                "entity": {
                    "id": f"plink_{reference_id}",
                    "reference_id": reference_id,
                    "amount": amount_paise,
                    "currency": "INR",
                    "status": "paid",
                    "customer": {"name": "cus_wh_test_001", "email": "cus@example.com"},
                }
            },
            "payment": {
                "entity": {
                    "id": payment_id,
                    "amount": amount_paise,
                    "currency": "INR",
                    "status": "captured",
                    "method": "card",
                    "created_at": created_at_ts,
                }
            },
        },
        "created_at": created_at_ts,
    }


def sign_payload(raw_body: bytes, secret: str) -> str:
    """Compute HMAC-SHA256 hex digest for given raw bytes and secret."""
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


# --- 1. SIGNATURE & SECURITY VERIFICATION TESTS ---

def test_signature_valid_accepted(webhook_secret):
    """Valid HMAC-SHA256 signature is accepted."""
    raw_body = b'{"event": "payment_link.paid", "id": "evt_001"}'
    valid_sig = sign_payload(raw_body, webhook_secret)
    assert verify_webhook_signature(raw_body, valid_sig, webhook_secret) is True


def test_signature_invalid_rejected(webhook_secret):
    """Tampered or incorrect signature is rejected."""
    raw_body = b'{"event": "payment_link.paid", "id": "evt_001"}'
    assert verify_webhook_signature(raw_body, "tampered_sig", webhook_secret) is False


def test_signature_missing_rejected(webhook_secret):
    """Missing signature is rejected."""
    raw_body = b'{"event": "payment_link.paid"}'
    assert verify_webhook_signature(raw_body, None, webhook_secret) is False
    assert verify_webhook_signature(raw_body, "", webhook_secret) is False


def test_signature_missing_secret_fails_closed():
    """Missing webhook secret fails closed safely."""
    raw_body = b'{"event": "payment_link.paid"}'
    assert verify_webhook_signature(raw_body, "some_sig", None) is False
    assert verify_webhook_signature(raw_body, "some_sig", "") is False


def test_unmatched_reference_returns_404(razorpay_config):
    """Webhook with uncorrelatable reference_id returns HTTP 404 with no mutation."""
    context = ReviveRuntimeContext(config=razorpay_config)
    set_runtime_context(context)

    client = TestClient(app)
    data = generate_razorpay_payment_link_paid_payload(reference_id="non_existent_ref", event_id="e_404")
    raw = json.dumps(data).encode("utf-8")
    sig = sign_payload(raw, razorpay_config.webhook_secret)

    r = client.post("/webhooks/razorpay", content=raw, headers={"X-Razorpay-Signature": sig, "X-Razorpay-Event-Id": "e_404"})
    assert r.status_code == 404
    assert r.json()["status"] == "not_found"


def test_customer_name_fallback_is_impossible(razorpay_config, sample_plan_pro):
    """Customer with multiple executions is not matched via customer name when reference_id is invalid."""
    customer_id = "cus_no_name_fallback"
    d1 = InterventionDecision(
        customer_id=customer_id,
        decision_timestamp="2026-08-01T10:00:00+00:00",
        risk_score=0.85,
        risk_tier="CRITICAL",
        revenue_at_risk=Decimal("999.00"),
        diagnosis="PAYMENT_FRICTION",
        diagnosis_confidence=1.0,
        diagnosis_actionability="candidate",
        eligibility_status="ELIGIBLE",
        selected_action=InterventionAction.PAYMENT_RECOVERY,
        expected_value=Decimal("749.25"),
        candidate_scores=[],
        decision_reason="Attempt 1",
        supporting_evidence=[],
    )
    d2 = InterventionDecision(
        customer_id=customer_id,
        decision_timestamp="2026-08-05T12:00:00+00:00",
        risk_score=0.85,
        risk_tier="CRITICAL",
        revenue_at_risk=Decimal("999.00"),
        diagnosis="PAYMENT_FRICTION",
        diagnosis_confidence=1.0,
        diagnosis_actionability="candidate",
        eligibility_status="ELIGIBLE",
        selected_action=InterventionAction.PAYMENT_RECOVERY,
        expected_value=Decimal("749.25"),
        candidate_scores=[],
        decision_reason="Attempt 2",
        supporting_evidence=[],
    )

    context = ReviveRuntimeContext(config=razorpay_config)
    r1 = context.execute_decision(d1, plan=sample_plan_pro)
    r2 = context.execute_decision(d2, plan=sample_plan_pro)

    data = {
        "entity": "event",
        "account_id": "acc_test",
        "event": "payment_link.paid",
        "payload": {
            "payment_link": {
                "entity": {
                    "id": "plink_unknown",
                    "reference_id": "payload_non_existent_999",
                    "customer": {"name": customer_id},
                }
            },
            "payment": {"entity": {"id": "pay_xyz", "amount": 99900}},
        },
        "created_at": 1785938400,
    }
    raw = json.dumps(data).encode("utf-8")
    sig = sign_payload(raw, razorpay_config.webhook_secret)

    st, resp = context.webhook_handler.process_webhook(raw_body=raw, signature=sig, event_id_header="evt_no_fallback")
    assert st == 404
    assert resp["status"] == "not_found"
    assert len(context.outcome_engine.get_customer_outcomes(customer_id)) == 0


# --- 2. RETRY SAFETY & AT-LEAST-ONCE DELIVERY TESTS ---

def test_1_unmatched_reference_is_retryable(razorpay_config, sample_decision, sample_plan_pro):
    """
    1. UNMATCHED_REFERENCE IS RETRYABLE:
    - First delivery fails with 404 and is NOT added to processed_event_ids.
    - Execution context is then made available.
    - Second delivery with SAME event_id succeeds with 200 PROCESSED.
    - Both audit records preserved in append-only store.
    """
    context = ReviveRuntimeContext(config=razorpay_config)
    event_id = "evt_unmatched_retry_101"

    # 1. First Attempt: Execution not yet in audit logger -> 404
    data1 = generate_razorpay_payment_link_paid_payload(
        reference_id="unmatched_payload_999",
        event_id=event_id,
        payment_id="pay_retry_001",
    )
    raw1 = json.dumps(data1).encode("utf-8")
    sig1 = sign_payload(raw1, razorpay_config.webhook_secret)

    st1, resp1 = context.webhook_handler.process_webhook(raw_body=raw1, signature=sig1, event_id_header=event_id)
    assert st1 == 404
    assert resp1["status"] == "not_found"
    assert event_id not in context.webhook_handler.processed_event_ids

    # 2. Execution context arrives / is recorded
    audit_rec = context.execute_decision(sample_decision, plan=sample_plan_pro)
    assert audit_rec.status == ExecutionStatus.EXECUTED

    # 3. Second Attempt: Same event_id retried by Razorpay with matching reference_id -> Must succeed
    data2 = generate_razorpay_payment_link_paid_payload(
        reference_id=audit_rec.payload_id,
        event_id=event_id,
        payment_id="pay_retry_001",
    )
    raw2 = json.dumps(data2).encode("utf-8")
    sig2 = sign_payload(raw2, razorpay_config.webhook_secret)

    st2, resp2 = context.webhook_handler.process_webhook(raw_body=raw2, signature=sig2, event_id_header=event_id)
    assert st2 == 200
    assert resp2["status"] == "processed"
    assert resp2["outcome"] == "RECOVERED"
    assert resp2["attribution_status"] == "DIRECTLY_OBSERVED"
    assert resp2["attributable_revenue"] == 999.0

    # 4. Verify append-only audit store preserves both attempts
    history = context.audit_store.get_records_by_event_id(event_id)
    assert len(history) == 2
    assert history[0].status == WebhookProcessingStatus.UNMATCHED_REFERENCE
    assert history[1].status == WebhookProcessingStatus.PROCESSED


def test_2_decision_unavailable_is_retryable(razorpay_config, sample_decision, sample_plan_pro):
    """
    2. DECISION_UNAVAILABLE IS RETRYABLE:
    - First delivery fails with 422 because decision is missing.
    - Decision is restored in context.
    - Second delivery with SAME event_id succeeds with 200 PROCESSED.
    """
    context = ReviveRuntimeContext(config=razorpay_config)
    engine = context.create_execution_engine()
    audit_rec = engine.execute_decision(sample_decision)
    # Associate plan but intentionally remove decision from decision_store
    decision_id = f"dec_{sample_decision.customer_id}_{sample_decision.decision_timestamp}"
    context.decision_plan_store[decision_id] = sample_plan_pro

    event_id = "evt_dec_retry_102"
    data = generate_razorpay_payment_link_paid_payload(
        reference_id=audit_rec.payload_id,
        event_id=event_id,
    )
    raw = json.dumps(data).encode("utf-8")
    sig = sign_payload(raw, razorpay_config.webhook_secret)

    # 1. First Attempt -> 422 DECISION_UNAVAILABLE
    st1, resp1 = context.webhook_handler.process_webhook(raw_body=raw, signature=sig, event_id_header=event_id)
    assert st1 == 422
    assert resp1["status"] == "decision_unavailable"
    assert event_id not in context.webhook_handler.processed_event_ids

    # 2. Decision is restored in context
    context.decision_store[decision_id] = sample_decision

    # 3. Second Attempt (Retry) -> 200 PROCESSED
    st2, resp2 = context.webhook_handler.process_webhook(raw_body=raw, signature=sig, event_id_header=event_id)
    assert st2 == 200
    assert resp2["status"] == "processed"
    assert resp2["outcome"] == "RECOVERED"


def test_3_plan_unavailable_is_retryable(razorpay_config, sample_decision, sample_plan_pro):
    """
    3. PLAN_UNAVAILABLE IS RETRYABLE:
    - First delivery fails with 422 because Plan is missing.
    - Plan is restored in context.
    - Second delivery with SAME event_id succeeds with 200 PROCESSED.
    """
    context = ReviveRuntimeContext(config=razorpay_config)
    context.record_decision(sample_decision, plan=None)
    engine = context.create_execution_engine()
    audit_rec = engine.execute_decision(sample_decision)

    event_id = "evt_plan_retry_103"
    data = generate_razorpay_payment_link_paid_payload(
        reference_id=audit_rec.payload_id,
        event_id=event_id,
    )
    raw = json.dumps(data).encode("utf-8")
    sig = sign_payload(raw, razorpay_config.webhook_secret)

    # 1. First Attempt -> 422 PLAN_UNAVAILABLE
    st1, resp1 = context.webhook_handler.process_webhook(raw_body=raw, signature=sig, event_id_header=event_id)
    assert st1 == 422
    assert resp1["status"] == "plan_unavailable"
    assert event_id not in context.webhook_handler.processed_event_ids

    # 2. Plan is restored in context
    decision_id = f"dec_{sample_decision.customer_id}_{sample_decision.decision_timestamp}"
    context.decision_plan_store[decision_id] = sample_plan_pro

    # 3. Second Attempt (Retry) -> 200 PROCESSED
    st2, resp2 = context.webhook_handler.process_webhook(raw_body=raw, signature=sig, event_id_header=event_id)
    assert st2 == 200
    assert resp2["status"] == "processed"
    assert resp2["outcome"] == "RECOVERED"


def test_4_successful_duplicate_remains_idempotent(razorpay_config, sample_decision, sample_plan_pro):
    """
    4. SUCCESSFUL DUPLICATE REMAINS IDEMPOTENT:
    - First delivery = PROCESSED (200 OK).
    - Second delivery = DUPLICATE_IGNORED (200 OK).
    - Exactly one OutcomeRecord and exactly one revenue attribution.
    """
    context = ReviveRuntimeContext(config=razorpay_config)
    audit_rec = context.execute_decision(sample_decision, plan=sample_plan_pro)

    event_id = "evt_dup_idemp_104"
    data = generate_razorpay_payment_link_paid_payload(
        reference_id=audit_rec.payload_id,
        event_id=event_id,
    )
    raw = json.dumps(data).encode("utf-8")
    sig = sign_payload(raw, razorpay_config.webhook_secret)

    # First delivery -> PROCESSED
    st1, resp1 = context.webhook_handler.process_webhook(raw_body=raw, signature=sig, event_id_header=event_id)
    assert st1 == 200
    assert resp1["status"] == "processed"

    # Second delivery -> DUPLICATE_IGNORED
    st2, resp2 = context.webhook_handler.process_webhook(raw_body=raw, signature=sig, event_id_header=event_id)
    assert st2 == 200
    assert resp2["status"] == "duplicate_acknowledged"

    # Exactly 1 OutcomeRecord in OutcomeEngine
    outcomes = context.outcome_engine.get_customer_outcomes(sample_decision.customer_id)
    assert len(outcomes) == 1


def test_5_unsupported_event_terminally_ignored(razorpay_config):
    """
    5. UNSUPPORTED EVENT IS TERMINALLY IGNORED:
    - First delivery: order.paid -> 200 OK (UNSUPPORTED_IGNORED).
    - Second delivery of same event_id -> 200 OK (duplicate_acknowledged).
    """
    context = ReviveRuntimeContext(config=razorpay_config)
    event_id = "evt_unsupp_105"
    data = {
        "entity": "event",
        "account_id": "acc_test",
        "event": "order.paid",
        "payload": {"order": {"entity": {"id": "order_123"}}},
        "created_at": 1785938400,
    }
    raw = json.dumps(data).encode("utf-8")
    sig = sign_payload(raw, razorpay_config.webhook_secret)

    # First delivery -> ignored
    st1, resp1 = context.webhook_handler.process_webhook(raw_body=raw, signature=sig, event_id_header=event_id)
    assert st1 == 200
    assert resp1["status"] == "ignored"
    assert event_id in context.webhook_handler.processed_event_ids

    # Second delivery -> duplicate_acknowledged
    st2, resp2 = context.webhook_handler.process_webhook(raw_body=raw, signature=sig, event_id_header=event_id)
    assert st2 == 200
    assert resp2["status"] == "duplicate_acknowledged"


def test_6_unexpected_processing_failure_is_retryable(razorpay_config, sample_decision, sample_plan_pro):
    """
    6. UNEXPECTED PROCESSING FAILURE IS RETRYABLE:
    - Transient exception during measure_outcome returns 500 and is NOT marked processed.
    - Subsequent retry after transient issue resolves succeeds with 200 PROCESSED.
    """
    context = ReviveRuntimeContext(config=razorpay_config)
    audit_rec = context.execute_decision(sample_decision, plan=sample_plan_pro)

    event_id = "evt_err_retry_106"
    data = generate_razorpay_payment_link_paid_payload(
        reference_id=audit_rec.payload_id,
        event_id=event_id,
    )
    raw = json.dumps(data).encode("utf-8")
    sig = sign_payload(raw, razorpay_config.webhook_secret)

    # 1. Simulate unexpected transient internal failure
    with patch.object(context.outcome_engine, "measure_outcome", side_effect=RuntimeError("Transient database timeout")):
        st1, resp1 = context.webhook_handler.process_webhook(raw_body=raw, signature=sig, event_id_header=event_id)
        assert st1 == 500
        assert resp1["status"] == "internal_error"
        assert event_id not in context.webhook_handler.processed_event_ids

    # 2. Retry with normal healthy execution -> 200 PROCESSED
    st2, resp2 = context.webhook_handler.process_webhook(raw_body=raw, signature=sig, event_id_header=event_id)
    assert st2 == 200
    assert resp2["status"] == "processed"
    assert resp2["outcome"] == "RECOVERED"


# --- 3. MULTI-PLAN & PRODUCTION COMPOSITION TESTS ---

def test_multi_plan_authoritative_correlation(razorpay_config, sample_plan_pro, sample_plan_business):
    """
    Multi-plan correlation proves OutcomeEngine receives the authoritative Plan
    associated with each specific execution, never an arbitrary default.
    - Customer A / Decision A: Pro Plan (₹999.00)
    - Customer B / Decision B: Business Plan (₹2499.00)
    """
    context = ReviveRuntimeContext(config=razorpay_config)

    dA = InterventionDecision(
        customer_id="cus_plan_A",
        decision_timestamp="2026-08-05T10:00:00+00:00",
        risk_score=0.85,
        risk_tier="CRITICAL",
        revenue_at_risk=Decimal("999.00"),
        diagnosis="PAYMENT_FRICTION",
        diagnosis_confidence=1.0,
        diagnosis_actionability="candidate",
        eligibility_status="ELIGIBLE",
        selected_action=InterventionAction.PAYMENT_RECOVERY,
        expected_value=Decimal("749.25"),
        candidate_scores=[],
        decision_reason="Pro recovery",
        supporting_evidence=[],
    )

    dB = InterventionDecision(
        customer_id="cus_plan_B",
        decision_timestamp="2026-08-05T11:00:00+00:00",
        risk_score=0.85,
        risk_tier="CRITICAL",
        revenue_at_risk=Decimal("2499.00"),
        diagnosis="PAYMENT_FRICTION",
        diagnosis_confidence=1.0,
        diagnosis_actionability="candidate",
        eligibility_status="ELIGIBLE",
        selected_action=InterventionAction.PAYMENT_RECOVERY,
        expected_value=Decimal("1874.25"),
        candidate_scores=[],
        decision_reason="Business recovery",
        supporting_evidence=[],
    )

    recA = context.execute_decision(dA, plan=sample_plan_pro)
    recB = context.execute_decision(dB, plan=sample_plan_business)

    handler = context.webhook_handler

    # 1. Process Webhook for Business Execution (Customer B)
    dataB = generate_razorpay_payment_link_paid_payload(
        reference_id=recB.payload_id,
        event_id="evt_plan_B",
        payment_id="pay_biz_001",
        amount_paise=249900,
    )
    rawB = json.dumps(dataB).encode("utf-8")
    sigB = sign_payload(rawB, razorpay_config.webhook_secret)
    stB, respB = handler.process_webhook(raw_body=rawB, signature=sigB, event_id_header="evt_plan_B")

    assert stB == 200
    assert respB["plan_id"] == "business"
    assert respB["attributable_revenue"] == 2499.0
    assert respB["net_recovered_revenue"] == 2496.0

    # 2. Process Webhook for Pro Execution (Customer A)
    dataA = generate_razorpay_payment_link_paid_payload(
        reference_id=recA.payload_id,
        event_id="evt_plan_A",
        payment_id="pay_pro_001",
        amount_paise=99900,
    )
    rawA = json.dumps(dataA).encode("utf-8")
    sigA = sign_payload(rawA, razorpay_config.webhook_secret)
    stA, respA = handler.process_webhook(raw_body=rawA, signature=sigA, event_id_header="evt_plan_A")

    assert stA == 200
    assert respA["plan_id"] == "pro"
    assert respA["attributable_revenue"] == 999.0
    assert respA["net_recovered_revenue"] == 996.0


def test_production_equivalent_shared_context_e2e(razorpay_config, sample_decision, sample_plan_pro):
    """
    Production-equivalent path:
    InterventionDecision -> ReviveRuntimeContext.execute_decision() -> ExecutionAuditLogger
    -> Razorpay payment_link.paid -> FastAPI /webhooks/razorpay -> same context correlation
    WITHOUT any test-only manual register hacks.
    """
    context = ReviveRuntimeContext(config=razorpay_config)
    set_runtime_context(context)

    audit_record = context.execute_decision(sample_decision, plan=sample_plan_pro)
    assert audit_record.status == ExecutionStatus.EXECUTED
    assert audit_record.payload_id is not None

    client = TestClient(app)
    data = generate_razorpay_payment_link_paid_payload(
        reference_id=audit_record.payload_id,
        event_id="evt_e2e_shared_001",
        payment_id="pay_real_9999",
        amount_paise=99900,
    )
    raw_body = json.dumps(data).encode("utf-8")
    sig = sign_payload(raw_body, razorpay_config.webhook_secret)

    resp = client.post(
        "/webhooks/razorpay",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": sig,
            "X-Razorpay-Event-Id": "evt_e2e_shared_001",
        },
    )

    assert resp.status_code == 200
    res_json = resp.json()
    assert res_json["status"] == "processed"
    assert res_json["outcome"] == "RECOVERED"
    assert res_json["attribution_status"] == "DIRECTLY_OBSERVED"
    assert res_json["attributable_revenue"] == 999.0
    assert res_json["net_recovered_revenue"] == 996.0
    assert res_json["payment_reference"] == "pay_real_9999"
    assert res_json["plan_id"] == "pro"


# --- 4. EXACT DECISION CORRELATION & NON-RECOVERY TESTS ---

def test_exact_decision_correlation_multiple_decisions(razorpay_config, sample_plan_pro):
    """Customer with multiple decisions maps strictly by exact decision_id."""
    customer_id = "cus_multi_dec_001"

    d1 = InterventionDecision(
        customer_id=customer_id,
        decision_timestamp="2026-08-01T10:00:00+00:00",
        risk_score=0.70,
        risk_tier="HIGH",
        revenue_at_risk=Decimal("999.00"),
        diagnosis="PAYMENT_FRICTION",
        diagnosis_confidence=1.0,
        diagnosis_actionability="candidate",
        eligibility_status="ELIGIBLE",
        selected_action=InterventionAction.PAYMENT_RECOVERY,
        expected_value=Decimal("500.00"),
        candidate_scores=[],
        decision_reason="Decision 1",
        supporting_evidence=[],
    )

    d2 = InterventionDecision(
        customer_id=customer_id,
        decision_timestamp="2026-08-05T12:00:00+00:00",
        risk_score=0.90,
        risk_tier="CRITICAL",
        revenue_at_risk=Decimal("999.00"),
        diagnosis="PAYMENT_FRICTION",
        diagnosis_confidence=1.0,
        diagnosis_actionability="candidate",
        eligibility_status="ELIGIBLE",
        selected_action=InterventionAction.PAYMENT_RECOVERY,
        expected_value=Decimal("800.00"),
        candidate_scores=[],
        decision_reason="Decision 2",
        supporting_evidence=[],
    )

    context = ReviveRuntimeContext(config=razorpay_config)
    r1 = context.execute_decision(d1, plan=sample_plan_pro)
    r2 = context.execute_decision(d2, plan=sample_plan_pro)

    handler = context.webhook_handler

    data1 = generate_razorpay_payment_link_paid_payload(reference_id=r1.payload_id, event_id="evt_r1")
    raw1 = json.dumps(data1).encode("utf-8")
    sig1 = sign_payload(raw1, razorpay_config.webhook_secret)
    st1, resp1 = handler.process_webhook(raw_body=raw1, signature=sig1, event_id_header="evt_r1")

    assert st1 == 200
    assert resp1["execution_id"] == r1.execution_id
    rec1 = context.outcome_engine.get_outcome_record(resp1["outcome_id"])
    assert rec1 is not None
    assert rec1.decision_id == r1.decision_id
    assert rec1.decision_id != r2.decision_id


def test_payment_captured_cannot_independently_recover(razorpay_config, sample_decision, sample_plan_pro):
    """payment.captured is non-primary and cannot create a second recovery or double-count."""
    context = ReviveRuntimeContext(config=razorpay_config)
    audit_record = context.execute_decision(sample_decision, plan=sample_plan_pro)

    data = {
        "entity": "event",
        "account_id": "acc_test",
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_captured_001",
                    "amount": 99900,
                    "currency": "INR",
                    "notes": {"reference_id": audit_record.payload_id},
                }
            }
        },
        "created_at": 1785938400,
    }
    raw = json.dumps(data).encode("utf-8")
    sig = sign_payload(raw, razorpay_config.webhook_secret)

    st, resp = context.webhook_handler.process_webhook(raw_body=raw, signature=sig, event_id_header="evt_captured_001")

    assert st == 200
    assert resp["status"] == "ignored"
    assert len(context.outcome_engine.get_customer_outcomes(sample_decision.customer_id)) == 0


def test_security_signature_and_headers(razorpay_config):
    """Invalid signature, missing signature, missing event ID, and malformed JSON."""
    client = TestClient(app)
    raw = b'{"event": "payment_link.paid"}'

    # 1. Invalid signature -> 401
    r_inv = client.post("/webhooks/razorpay", content=raw, headers={"X-Razorpay-Signature": "bad_sig", "X-Razorpay-Event-Id": "e1"})
    assert r_inv.status_code == 401

    # 2. Missing signature -> 401
    r_mis_sig = client.post("/webhooks/razorpay", content=raw, headers={"X-Razorpay-Event-Id": "e2"})
    assert r_mis_sig.status_code == 401

    # 3. Missing event ID -> 400
    sig = sign_payload(raw, razorpay_config.webhook_secret)
    r_mis_id = client.post("/webhooks/razorpay", content=raw, headers={"X-Razorpay-Signature": sig})
    assert r_mis_id.status_code == 400

    # 4. Malformed JSON -> 400
    r_bad_json = client.post("/webhooks/razorpay", content=b"{bad", headers={"X-Razorpay-Signature": sign_payload(b"{bad", razorpay_config.webhook_secret), "X-Razorpay-Event-Id": "e3"})
    assert r_bad_json.status_code == 400


def test_secret_redaction(razorpay_config):
    """Secret is redacted in config string/repr and never leaked in HTTP error responses."""
    assert razorpay_config.webhook_secret not in repr(razorpay_config)
    assert "[REDACTED]" in repr(razorpay_config)


def test_ground_truth_isolation():
    """Translated BaseEvent strictly contains no simulator-only hidden fields."""
    data = generate_razorpay_payment_link_paid_payload(reference_id="payload_pay_001")
    evt = translate_razorpay_event_to_base_event(data, correlated_customer_id="cus_001", event_id="evt_gt_001")
    assert evt is not None
    evt_str = str(evt.model_dump())

    forbidden = {
        "ground_truth",
        "true_root_cause",
        "natural_conversion",
        "recoverable",
        "maximum_recoverable_revenue",
        "conversion_after_intervention",
    }
    for field in forbidden:
        assert field not in evt_str


def test_pre_existing_conversion_protection(razorpay_config, sample_decision, sample_plan_pro):
    """Pre-existing conversion event before execution resolves ALREADY_CONVERTED with ₹0 attributable revenue."""
    context = ReviveRuntimeContext(config=razorpay_config)
    audit_rec = context.execute_decision(sample_decision, plan=sample_plan_pro)
    exec_dt = datetime.fromisoformat(audit_rec.execution_timestamp)

    pre_conv = BaseEvent(
        event_id="evt_pre_001",
        event_type=EventType.PAYMENT_SUCCEEDED,
        schema_version="1.0",
        merchant_id="merch_codecraft",
        customer_id=sample_decision.customer_id,
        timestamp=exec_dt - timedelta(hours=2),
        source="billing",
        payload={"amount": "999.00", "payment_id": "pay_old_001"},
    )
    context.customer_events_store[sample_decision.customer_id] = [pre_conv]

    data = generate_razorpay_payment_link_paid_payload(reference_id=audit_rec.payload_id, event_id="evt_pre_test")
    raw = json.dumps(data).encode("utf-8")
    sig = sign_payload(raw, razorpay_config.webhook_secret)

    st, resp = context.webhook_handler.process_webhook(raw_body=raw, signature=sig, event_id_header="evt_pre_test")

    assert st == 200
    assert resp["outcome"] == "ALREADY_CONVERTED"
    assert resp["attribution_status"] == "UNATTRIBUTED"
    assert resp["attributable_revenue"] == 0.0
    assert resp["net_recovered_revenue"] == -3.0
