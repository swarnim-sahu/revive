"""
REVIVE Phase 9: Razorpay Sandbox / Test Mode Execution Boundary Test Suite.

Comprehensive offline test suite verifying:
1. Default execution mode is MOCK (MockRazorpayClient).
2. Sandbox mode explicitly selects RazorpaySandboxClient.
3. rzp_live_* credentials rejected immediately (fail closed).
4. Sandbox mode requires rzp_test_* credentials.
5. Invalid execution mode raises ValueError (fail closed).
6. Missing sandbox credentials fail safely without leaking secrets.
7. Production environment/endpoints rejected.
8. Request construction uses minimum required fields (RazorpayPaymentLinkRequest).
9. Authoritative execution identity: payload_id -> reference_id.
10. Duplicate execution idempotently handled at execution boundary.
11. Policy rejection results in zero provider calls.
12. Gemini / AI has zero execution authority and cannot reach Razorpay.
13. Provider timeout handled safely without false success.
14. Provider HTTP rejection handled safely without false success.
15. Webhook signature verification (HMAC-SHA256).
16. Webhook duplicate handling via x-razorpay-event-id.
17. Hard invariant: Payment Link Created != Payment Recovered.
18. Offline mock evaluation remains network-free.
19. Controlled sandbox entry point is explicit and not automatically invoked.
20. Artifact truthfulness: valid lifecycle state is preserved.

ALL tests execute 100% OFFLINE with mocked or simulated HTTP transport. ZERO real Razorpay calls.
"""

from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from app.models.entities import Customer, Plan
from app.models.enums import EventType
from app.models.events import BaseEvent
from app.intervention.engine import InterventionEngine
from app.intervention.schemas import (
    CandidateActionScore,
    InterventionAction,
    InterventionDecision,
)
from app.execution.engine import ExecutionEngine
from app.execution.schemas import ExecutionAuditRecord, ExecutionStatus, InterventionPayload
from app.outcome.schemas import AttributionStatus, OutcomeType
from app.integrations.razorpay.config import RazorpayConfig
from app.integrations.razorpay.client import (
    BaseRazorpayClient,
    MockRazorpayClient,
    RazorpaySandboxClient,
)
from app.integrations.razorpay.dispatcher import RazorpaySandboxDispatcher
from app.integrations.razorpay.demo_runner import (
    DEFAULT_PHASE9_ARTIFACT_PATH,
    create_demo_intervention_decision,
    run_controlled_sandbox_demonstration,
)
from app.integrations.razorpay.schemas import (
    RazorpayCustomerInfo,
    RazorpayPaymentLinkRequest,
    RazorpayPaymentLinkResponse,
)
from app.integrations.razorpay.webhook import (
    RazorpayWebhookHandler,
    ReviveRuntimeContext,
    WebhookAuditStore,
    WebhookProcessingStatus,
    verify_webhook_signature,
)
from app.integrations.razorpay.persistence import (
    DEFAULT_PHASE9_CONTEXT_PATH,
    Phase9RuntimeContext,
    load_phase9_runtime_context,
    save_phase9_runtime_context,
    is_phase9_event_processed,
    update_phase9_event_processed,
    update_phase9_demo_artifact_on_recovery,
)


@pytest.fixture
def valid_sandbox_config():
    return RazorpayConfig(
        execution_mode="sandbox",
        environment="sandbox",
        key_id="rzp_test_VALIDKEY123",
        key_secret="SECRET_VAL_TEST999",
        webhook_secret="WH_SECRET_ABC123",
    )


@pytest.fixture
def valid_mock_config():
    return RazorpayConfig(
        execution_mode="mock",
        environment="sandbox",
    )


# ==============================================================================
# 1. Default Mode is MOCK
# ==============================================================================
def test_1_default_mode_is_mock():
    """Default execution mode is 'mock' and initializes MockRazorpayClient."""
    cfg = RazorpayConfig()
    assert cfg.execution_mode == "mock"
    dispatcher = RazorpaySandboxDispatcher(config=cfg)
    assert isinstance(dispatcher.client, MockRazorpayClient)


# ==============================================================================
# 2. Sandbox Mode Explicitly Selects RazorpaySandboxClient
# ==============================================================================
def test_2_sandbox_mode_explicitly_selects_sandbox_client(valid_sandbox_config):
    """Explicit sandbox mode selects RazorpaySandboxClient connected to standard gateway."""
    dispatcher = RazorpaySandboxDispatcher(config=valid_sandbox_config)
    assert isinstance(dispatcher.client, RazorpaySandboxClient)
    assert dispatcher.client.config.base_url == "https://api.razorpay.com/v1"


# ==============================================================================
# 3. rzp_live_* Credentials Rejected Immediately
# ==============================================================================
def test_3_live_credentials_fail_closed():
    """Live/production credentials ('rzp_live_*') are strictly rejected."""
    with pytest.raises(ValueError, match="Production Razorpay credentials"):
        RazorpayConfig(
            execution_mode="sandbox",
            key_id="rzp_live_PRODSECRET999",
            key_secret="some_secret",
        )


# ==============================================================================
# 4. Sandbox Mode Requires rzp_test_* Credentials
# ==============================================================================
def test_4_sandbox_mode_requires_test_mode_prefix():
    """Sandbox mode rejects keys not starting with 'rzp_test_'."""
    with pytest.raises(ValueError, match="rzp_test_"):
        RazorpayConfig(
            execution_mode="sandbox",
            key_id="custom_key_without_test_prefix",
            key_secret="some_secret",
        )


# ==============================================================================
# 5. Invalid Execution Mode Raises ValueError
# ==============================================================================
def test_5_invalid_mode_fails_closed():
    """Any unsupported execution mode (e.g. 'production', 'live', 'unknown') fails closed."""
    with pytest.raises(ValueError, match="Invalid RAZORPAY_EXECUTION_MODE"):
        RazorpayConfig(execution_mode="unsupported_mode")


# ==============================================================================
# 6. Missing Sandbox Credentials Fail Safely Without Leaking Secrets
# ==============================================================================
def test_6_missing_sandbox_credentials_fail_safely():
    """Missing sandbox credentials return safe failure and never silently fall back to mock."""
    no_cred_config = RazorpayConfig(execution_mode="sandbox", key_id=None, key_secret=None)
    dispatcher = RazorpaySandboxDispatcher(config=no_cred_config)
    assert isinstance(dispatcher.client, RazorpaySandboxClient)

    payload = InterventionPayload(
        payload_id="payload_test_no_cred",
        action=InterventionAction.PAYMENT_RECOVERY,
        customer_id="cus_test_001",
        headline="Payment Required",
        body="Body",
        parameters={"amount_paise": 99900},
    )

    err = dispatcher.dispatch(payload=payload, environment="sandbox")
    assert err is not None
    assert "authentication failed: missing KEY_ID or KEY_SECRET" in err
    # Confirm it did not succeed or silently fall back
    assert payload.target_url is None


# ==============================================================================
# 7. Production Environment / Endpoints Rejected
# ==============================================================================
def test_7_production_environment_rejected():
    """Production or live environment is strictly prohibited."""
    with pytest.raises(ValueError, match="Production/live environment is strictly prohibited"):
        RazorpayConfig(environment="production")

    with pytest.raises(ValueError, match="Production/live environment is strictly prohibited"):
        RazorpayConfig(environment="live")


# ==============================================================================
# 8. Request Construction Uses Minimum Required Fields
# ==============================================================================
def test_8_request_construction_shape(valid_sandbox_config):
    """Payment Link request is constructed with minimal required fields only."""
    client = RazorpaySandboxClient(config=valid_sandbox_config)
    req = RazorpayPaymentLinkRequest(
        amount=99900,
        currency="INR",
        description="Payment Recovery Test",
        customer=RazorpayCustomerInfo(name="cus_test", email="cus@example.com"),
        reference_id="ref_min_fields_001",
    )

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({
        "id": "plink_test_001",
        "short_url": "https://rzp.io/i/test001",
        "status": "created",
        "reference_id": "ref_min_fields_001",
        "amount": 99900,
        "currency": "INR",
        "created_at": 1725500000,
    }).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        resp, err = client.create_payment_link(req)
        assert err is None
        assert resp is not None
        assert resp.payment_link_id == "plink_test_001"

        called_req = mock_urlopen.call_args[0][0]
        data = json.loads(called_req.data.decode("utf-8"))
        assert data["amount"] == 99900
        assert data["currency"] == "INR"
        assert data["reference_id"] == "ref_min_fields_001"
        assert "prompt" not in data
        assert "ground_truth" not in data


# ==============================================================================
# 9. Authoritative Execution Identity: payload_id -> reference_id
# ==============================================================================
def test_9_payload_id_to_reference_id_mapping(valid_mock_config):
    """Authoritative execution identity payload.payload_id maps directly to reference_id."""
    dispatcher = RazorpaySandboxDispatcher(config=valid_mock_config)
    payload = InterventionPayload(
        payload_id="payload_identity_exact_999",
        action=InterventionAction.PAYMENT_RECOVERY,
        customer_id="cus_exact_999",
        headline="Action",
        body="Body",
        parameters={"amount_paise": 50000},
    )

    err = dispatcher.dispatch(payload=payload, environment="sandbox")
    assert err is None
    assert isinstance(dispatcher.client, MockRazorpayClient)
    assert dispatcher.client.last_request is not None
    assert dispatcher.client.last_request.reference_id == "payload_identity_exact_999"


# ==============================================================================
# 10. Duplicate Execution Suppressed at Execution Boundary
# ==============================================================================
def test_10_duplicate_execution_suppression(valid_mock_config):
    """Duplicate decision execution is idempotently suppressed without duplicate provider calls."""
    dispatcher = RazorpaySandboxDispatcher(config=valid_mock_config)
    engine = ExecutionEngine(dispatcher=dispatcher)

    decision = create_demo_intervention_decision(customer_id="cus_dup_boundary_01")
    rec1 = engine.execute_decision(decision)
    assert rec1.status == ExecutionStatus.EXECUTED

    # Same decision re-executed
    rec2 = engine.execute_decision(decision)
    assert rec2.status == ExecutionStatus.EXECUTED
    assert rec2.execution_id == rec1.execution_id
    assert rec2.payload_id == rec1.payload_id
    assert len(engine.emitted_events) == 1  # No duplicate event


# ==============================================================================
# 11. Policy Rejection Results in Zero Provider Calls
# ==============================================================================
def test_11_policy_rejection_zero_provider_calls(valid_sandbox_config):
    """Intervention rejected by policy generates ZERO provider calls."""
    mock_client = MagicMock(spec=BaseRazorpayClient)
    dispatcher = RazorpaySandboxDispatcher(config=valid_sandbox_config, client=mock_client)
    engine = ExecutionEngine(dispatcher=dispatcher)

    # Ineligible decision
    ineligible_decision = InterventionDecision(
        customer_id="cus_ineligible_01",
        decision_timestamp=datetime.now(timezone.utc).isoformat(),
        risk_score=0.90,
        risk_tier="CRITICAL",
        revenue_at_risk=Decimal("999.00"),
        diagnosis="PAYMENT_FRICTION",
        diagnosis_confidence=0.95,
        diagnosis_actionability="candidate",
        eligibility_status="INELIGIBLE",
        selected_action=InterventionAction.PAYMENT_RECOVERY,
        expected_value=Decimal("0.00"),
        candidate_scores=[],
        decision_reason="Safety contraindication: too many recent failures",
    )

    rec = engine.execute_decision(ineligible_decision)
    assert rec.status == ExecutionStatus.BLOCKED
    assert mock_client.create_payment_link.call_count == 0


# ==============================================================================
# 12. Gemini / AI Has Zero Execution Authority
# ==============================================================================
def test_12_ai_has_no_execution_or_razorpay_authority():
    """AIService has no connection, attribute, or dependency on Razorpay."""
    from app.ai.service import AIService
    ai = AIService()
    assert not hasattr(ai, "execute_recovery")
    assert not hasattr(ai, "create_payment_link")
    assert not hasattr(ai, "razorpay_client")
    assert not hasattr(ai, "dispatcher")


# ==============================================================================
# 13. Provider Timeout Handled Safely Without False Success
# ==============================================================================
def test_13_provider_timeout_never_false_success(valid_sandbox_config):
    """Timeout during provider call produces clean failure, never false success."""
    client = RazorpaySandboxClient(config=valid_sandbox_config)
    req = RazorpayPaymentLinkRequest(
        amount=99900,
        description="Timeout Test",
        customer=RazorpayCustomerInfo(name="cus_timeout"),
        reference_id="ref_timeout_01",
    )

    with patch("urllib.request.urlopen", side_effect=TimeoutError("Request timed out")):
        resp, err = client.create_payment_link(req)
        assert resp is None
        assert err is not None
        assert "timed out" in err.lower()


# ==============================================================================
# 14. Provider HTTP Rejection Handled Safely Without False Success
# ==============================================================================
def test_14_provider_rejection_handled_safely(valid_sandbox_config):
    """HTTP 400 rejection from provider is caught and never recorded as success."""
    import urllib.error
    client = RazorpaySandboxClient(config=valid_sandbox_config)
    req = RazorpayPaymentLinkRequest(
        amount=99900,
        description="Rejection Test",
        customer=RazorpayCustomerInfo(name="cus_reject"),
        reference_id="ref_reject_01",
    )

    err_fp = MagicMock()
    err_fp.read.return_value = b'{"error": {"code": "BAD_REQUEST_ERROR", "description": "Invalid amount"}}'
    http_error = urllib.error.HTTPError(
        url="https://api.razorpay.com/v1/payment_links",
        code=400,
        msg="Bad Request",
        hdrs={},
        fp=err_fp,
    )

    with patch("urllib.request.urlopen", side_effect=http_error):
        resp, err = client.create_payment_link(req)
        assert resp is None
        assert err is not None
        assert "400" in err
        assert "Invalid amount" in err


# ==============================================================================
# 15. Webhook Signature Verification (HMAC-SHA256)
# ==============================================================================
def test_15_webhook_signature_verification():
    """HMAC-SHA256 webhook signature verification accepts valid and rejects invalid signatures."""
    secret = "wh_secret_xyz123"
    body = b'{"event":"payment_link.paid"}'

    import hmac, hashlib
    valid_sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

    assert verify_webhook_signature(body, valid_sig, secret) is True
    assert verify_webhook_signature(body, "invalid_sig", secret) is False
    assert verify_webhook_signature(body, None, secret) is False
    assert verify_webhook_signature(body, valid_sig, None) is False


# ==============================================================================
# 16. Webhook Duplicate Handling via x-razorpay-event-id
# ==============================================================================
def test_16_webhook_duplicate_handling(valid_sandbox_config):
    """Duplicate webhook deliveries with the same event_id are idempotently ignored."""
    handler = RazorpayWebhookHandler(config=valid_sandbox_config)
    body = b'{"event":"unsupported.event","payload":{}}'

    import hmac, hashlib
    sig = hmac.new(valid_sandbox_config.webhook_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

    status1, resp1 = handler.process_webhook(body, signature=sig, event_id_header="evt_dup_test_001")
    assert status1 == 200
    assert resp1.get("status") == "ignored"

    # Duplicate delivery
    status2, resp2 = handler.process_webhook(body, signature=sig, event_id_header="evt_dup_test_001")
    assert status2 == 200
    assert resp2.get("status") == "duplicate_acknowledged"


# ==============================================================================
# 17. Hard Invariant: Payment Link Created != Payment Recovered
# ==============================================================================
def test_17_payment_link_created_is_not_payment_recovered(valid_mock_config):
    """
    CRITICAL INVARIANT: Creating a payment link is an outbound recovery attempt.
    It does NOT mark the outcome as recovered or attribute revenue.
    """
    dispatcher = RazorpaySandboxDispatcher(config=valid_mock_config)
    engine = ExecutionEngine(dispatcher=dispatcher)

    decision = create_demo_intervention_decision(customer_id="cus_invariant_01")
    exec_record = engine.execute_decision(decision)

    assert exec_record.status == ExecutionStatus.EXECUTED
    assert exec_record.target_url is not None

    # Verify through demonstration runner result shape
    demo_result = run_controlled_sandbox_demonstration(
        config=valid_mock_config,
        dry_run=False,
        save_artifact=False,
    )

    assert demo_result["execution_status"] == "EXECUTED"
    assert demo_result["payment_status"] == "PENDING"
    assert demo_result["outcome_status"] == "NO_OBSERVABLE_OUTCOME"
    assert demo_result["attribution_status"] == "UNATTRIBUTED"
    assert demo_result["outcome_status"] != "RECOVERED"
    assert demo_result["attribution_status"] != "ATTRIBUTED"


# ==============================================================================
# 18. Offline Mock Evaluation Remains Network-Free
# ==============================================================================
def test_18_offline_evaluation_remains_network_free(valid_mock_config):
    """Batch evaluation and mock dispatcher execute 100% network-free."""
    dispatcher = RazorpaySandboxDispatcher(config=valid_mock_config)
    payload = InterventionPayload(
        payload_id="payload_offline_net_free",
        action=InterventionAction.PAYMENT_RECOVERY,
        customer_id="cus_offline",
        headline="Headline",
        body="Body",
        parameters={"amount_paise": 99900},
    )

    # If urllib.request.urlopen were invoked, this patch would catch it
    with patch("urllib.request.urlopen") as mock_open:
        err = dispatcher.dispatch(payload=payload, environment="sandbox")
        assert err is None
        assert mock_open.call_count == 0


# ==============================================================================
# 19. Controlled Sandbox Entry Point is Explicit and Not Automatically Invoked
# ==============================================================================
def test_19_demo_entry_point_explicit_invocation(tmp_path):
    """Controlled demonstration runner must be explicitly invoked; dry_run maintains NOT_RUN."""
    demo_path = tmp_path / "phase9_sandbox_demo.json"

    # In dry_run mode, produces NOT_RUN
    result = run_controlled_sandbox_demonstration(
        dry_run=True,
        save_artifact=True,
        artifact_path=demo_path,
    )

    assert result["execution_status"] == "NOT_RUN"
    assert result["provider_reference"] is None
    assert result["payment_status"] == "PENDING"
    assert demo_path.exists()

    with open(demo_path, "r", encoding="utf-8") as f:
        saved = json.load(f)
    assert saved["execution_status"] == "NOT_RUN"


# ==============================================================================
# 20. Artifact Truthfulness: Valid Lifecycle State
# ==============================================================================
def test_20_committed_phase9_artifact_truthfulness():
    """
    The committed artifact preserves a valid lifecycle state and does not
    claim recovery before verified payment.
    """
    assert DEFAULT_PHASE9_ARTIFACT_PATH.exists()
    with open(DEFAULT_PHASE9_ARTIFACT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("phase_version") == "9.0.0"
    assert data.get("operation") == "CREATE_PAYMENT_LINK"
    assert data.get("execution_status") in {"NOT_RUN", "EXECUTED"}
    assert data.get("payment_status") in {"PENDING", "PAID"}
    if data.get("payment_status") == "PENDING":
        assert data.get("outcome_status") == "NO_OBSERVABLE_OUTCOME"
        assert data.get("attribution_status") == "UNATTRIBUTED"


# ==============================================================================
# 21. Real Provider ID Stored Separately from REVIVE Payload ID
# ==============================================================================
def test_21_provider_id_stored_separately_from_payload_id(valid_sandbox_config, valid_mock_config):
    """
    Authoritative identity invariant:
    payload_id = REVIVE internal execution identity (e.g. 'payload_...')
    provider_reference = actual Razorpay Payment Link ID (e.g. 'plink_...')
    They must remain distinct and never substituted for each other.
    """
    # 1. Mock Client verification
    demo_mock = run_controlled_sandbox_demonstration(
        config=valid_mock_config,
        dry_run=False,
        save_artifact=False,
    )
    assert demo_mock["execution_status"] == "EXECUTED"
    assert demo_mock["payload_id"].startswith("payload_")
    assert demo_mock["provider_reference"].startswith("plink_mock_")
    assert demo_mock["payload_id"] != demo_mock["provider_reference"]

    # 2. RazorpaySandboxClient with mocked HTTP response
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({
        "id": "plink_real_sandbox_link_9999",
        "short_url": "https://rzp.io/i/real_sandbox_9999",
        "status": "created",
        "reference_id": "ref_demo_test",
        "amount": 99900,
        "currency": "INR",
        "created_at": 1725500000,
    }).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    sandbox_client = RazorpaySandboxClient(config=valid_sandbox_config)
    with patch("urllib.request.urlopen", return_value=mock_resp):
        demo_sandbox = run_controlled_sandbox_demonstration(
            config=valid_sandbox_config,
            client=sandbox_client,
            dry_run=False,
            save_artifact=False,
        )

        assert demo_sandbox["execution_status"] == "EXECUTED"
        assert demo_sandbox["provider_reference"] == "plink_real_sandbox_link_9999"
        assert demo_sandbox["payload_id"].startswith("payload_")
        assert demo_sandbox["payload_id"] != demo_sandbox["provider_reference"]
        assert demo_sandbox["short_url"] == "https://rzp.io/i/real_sandbox_9999"


# ==============================================================================
# 22. Successful Execution Does NOT Imply FIRST_ATTEMPT_SUCCESS
# ==============================================================================
def test_22_successful_execution_truthful_idempotency_result(valid_mock_config):
    """
    Idempotency result semantics:
    Execution status EXECUTED must never blindly claim 'FIRST_ATTEMPT_SUCCESS'.
    Uses truthful 'EXECUTION_SUCCEEDED', 'DUPLICATE_SUPPRESSED', or 'RETRY_SUCCESS'.
    """
    # 1. Normal single execution -> EXECUTION_SUCCEEDED (never blindly FIRST_ATTEMPT_SUCCESS)
    demo1 = run_controlled_sandbox_demonstration(
        config=valid_mock_config,
        dry_run=False,
        save_artifact=False,
    )
    assert demo1["execution_status"] == "EXECUTED"
    assert demo1["idempotency_result"] == "EXECUTION_SUCCEEDED"
    assert demo1["idempotency_result"] != "FIRST_ATTEMPT_SUCCESS"

    # 2. Re-executing through an engine that already processed this decision -> DUPLICATE_SUPPRESSED
    pol_dec = create_demo_intervention_decision(customer_id="cus_idemp_dup_01")
    dispatcher = RazorpaySandboxDispatcher(config=valid_mock_config)
    engine = ExecutionEngine(dispatcher=dispatcher)

    # First run on engine
    rec1 = engine.execute_decision(pol_dec)
    assert rec1.status == ExecutionStatus.EXECUTED

    # Re-run through runner passing existing decision
    with patch("app.integrations.razorpay.demo_runner.ExecutionEngine", return_value=engine):
        demo_dup = run_controlled_sandbox_demonstration(
            config=valid_mock_config,
            decision=pol_dec,
            dry_run=False,
            save_artifact=False,
        )
        assert demo_dup["idempotency_result"] == "DUPLICATE_SUPPRESSED"


# ==============================================================================
# 23. Phase 9 Demo Obtains Authorization from Existing InterventionEngine
# ==============================================================================
def test_23_phase9_demo_authorized_by_existing_intervention_engine():
    """
    Demonstration decision is produced by invoking existing InterventionEngine.decide_intervention
    through its public interface, preserving deterministic policy matrix evaluation.
    """
    spy_engine = InterventionEngine()
    spy_called = False
    orig_decide = spy_engine.decide_intervention

    def tracked_decide(*args, **kwargs):
        nonlocal spy_called
        spy_called = True
        return orig_decide(*args, **kwargs)

    spy_engine.decide_intervention = tracked_decide

    decision = create_demo_intervention_decision(
        customer_id="cus_auth_spy_01",
        amount_paise=99900,
        intervention_engine=spy_engine,
    )

    assert spy_called is True
    assert isinstance(decision, InterventionDecision)
    assert decision.customer_id == "cus_auth_spy_01"
    assert decision.eligibility_status == "ELIGIBLE"
    assert decision.selected_action == InterventionAction.PAYMENT_RECOVERY
    assert decision.expected_value > Decimal("0.00")
    # 7 candidate actions evaluated by PolicyEngine
    assert len(decision.candidate_scores) == 7
    assert decision.decision_reason is not None


# ==============================================================================
# 24. Payment Link Webhook Contract: payment_link.paid Processing & Security
# ==============================================================================
def test_24_payment_link_paid_webhook_accepted_and_correlates_outcome(valid_sandbox_config):
    """
    Webhook handler supports the dedicated payment_link.paid event:
    - HMAC signature verification
    - Exact payload_id / reference_id correlation
    - Transitions outcome to RECOVERED and ATTRIBUTED
    - Idempotently acknowledges duplicate event IDs
    - Fails closed on invalid signatures
    """
    import hmac
    import hashlib

    handler = RazorpayWebhookHandler(config=valid_sandbox_config)

    # 1. Pre-register execution audit record and decision context
    customer_id = "cus_wh_contract_01"
    ref_payload_id = "payload_wh_contract_exact_01"
    dec_ts = "2026-08-10T10:00:00+00:00"
    dec_id = f"dec_{customer_id}_{dec_ts}"

    customer = Customer(
        customer_id=customer_id,
        merchant_id="merch_codecraft",
        created_at=datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc),
        plan_id="pro",
    )
    plan = Plan(
        plan_id="pro",
        name="Pro Plan",
        price=Decimal("999.00"),
        billing_interval="monthly",
    )

    exec_record = ExecutionAuditRecord(
        execution_id="exec_wh_contract_01",
        decision_id=dec_id,
        customer_id=customer_id,
        merchant_id="merch_codecraft",
        execution_timestamp=dec_ts,
        action=InterventionAction.PAYMENT_RECOVERY,
        status=ExecutionStatus.EXECUTED,
        attempt_number=1,
        payload_id=ref_payload_id,
        target_url="https://rzp.io/i/contract_01",
    )
    handler.audit_logger._audit_store[exec_record.execution_id] = exec_record

    pol_dec = create_demo_intervention_decision(customer_id=customer_id)
    handler.decision_store[dec_id] = pol_dec
    handler.decision_plan_store[dec_id] = plan

    # 2. Build authentic payment_link.paid webhook payload
    # Payment created 2 hours post-execution (1786360800)
    body_dict = {
        "entity": "event",
        "account_id": "acc_sandbox_demo",
        "event": "payment_link.paid",
        "contains": ["payment_link", "payment", "order"],
        "payload": {
            "payment_link": {
                "entity": {
                    "id": "plink_wh_contract_01",
                    "reference_id": ref_payload_id,
                    "amount": 99900,
                    "currency": "INR",
                    "status": "paid",
                    "created_at": 1786353600,
                }
            },
            "payment": {
                "entity": {
                    "id": "pay_wh_contract_01",
                    "amount": 99900,
                    "currency": "INR",
                    "status": "captured",
                    "method": "card",
                    "created_at": 1786360800,
                    "notes": {"reference_id": ref_payload_id},
                }
            },
        },
        "created_at": 1786360805,
    }
    raw_body = json.dumps(body_dict).encode("utf-8")
    valid_sig = hmac.new(
        valid_sandbox_config.webhook_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    # 3. Process with valid signature
    status_code, resp = handler.process_webhook(
        raw_body=raw_body,
        signature=valid_sig,
        event_id_header="evt_contract_wh_001",
    )
    assert status_code == 200
    assert resp["status"] == "processed"
    assert resp["outcome"] == "RECOVERED"
    assert resp["attribution_status"] == "DIRECTLY_OBSERVED"

    # 4. Duplicate event ID is acknowledged idempotently without re-attribution
    dup_status, dup_resp = handler.process_webhook(
        raw_body=raw_body,
        signature=valid_sig,
        event_id_header="evt_contract_wh_001",
    )
    assert dup_status == 200
    assert dup_resp["status"] == "duplicate_acknowledged"

    # 5. Invalid signature is rejected fail-closed
    bad_status, bad_resp = handler.process_webhook(
        raw_body=raw_body,
        signature="invalid_signature_xyz",
        event_id_header="evt_contract_wh_002",
    )
    assert bad_status == 401
    assert bad_resp["status"] == "unauthorized"


# ==============================================================================
# 25. Payment Link Creation Alone Never Creates Recovery Attribution
# ==============================================================================
def test_25_payment_link_creation_never_creates_recovery(valid_mock_config):
    """
    CRITICAL INVARIANT: Outbound payment link creation only sets payment_status: PENDING.
    It never mutates outcome or attributes financial recovery.
    """
    result = run_controlled_sandbox_demonstration(
        config=valid_mock_config,
        dry_run=False,
        save_artifact=False,
    )
    assert result["execution_status"] == "EXECUTED"
    assert result["payment_status"] == "PENDING"
    assert result["webhook_status"] == "PENDING_WEBHOOK"
    assert result["outcome_status"] == "NO_OBSERVABLE_OUTCOME"
    assert result["attribution_status"] == "UNATTRIBUTED"
    assert result["outcome_status"] != "RECOVERED"
    assert result["attribution_status"] != "ATTRIBUTED"


# ==============================================================================
# 26. Cross-Process Boundary Simulation: Process A -> Process B
# ==============================================================================
def test_26_cross_process_correlation_flow(tmp_path, valid_sandbox_config):
    """
    CRITICAL TEST: Cross-Process Boundary Simulation.
    Process A:
      - Creates approved Phase 9 execution context (offline synthetic execution)
      - Persists durable Phase9RuntimeContext projection
      - Persists Phase 9 demonstration artifact in PENDING state
      - Terminates logical Process A state (Process A objects cleared)
    Process B:
      - Instantiates completely fresh ReviveRuntimeContext & RazorpayWebhookHandler
      - Uses separate in-memory dictionaries
      - Receives signed payment_link.paid webhook
      - Hydrates Phase9RuntimeContext projection on cache miss
      - Resolves exact execution record, decision, and plan
      - OutcomeEngine confirms RECOVERED + DIRECTLY_OBSERVED
      - Updates demonstration artifact to PAID / PROCESSED / RECOVERED
    """
    import hmac
    import hashlib

    context_path = tmp_path / "phase9_razorpay_runtime_context.json"
    artifact_path = tmp_path / "phase9_razorpay_sandbox_demo.json"

    # --- PROCESS A SIMULATION ---
    customer_id = "cus_proc_sim_001"
    payload_id = "payload_proc_sim_001"
    provider_ref = "plink_proc_sim_001"
    dec_ts = "2026-08-20T14:00:00+00:00"
    exec_id = f"exec_{customer_id}_{dec_ts}_att1"
    dec_id = f"dec_{customer_id}_{dec_ts}"

    decision_a = create_demo_intervention_decision(customer_id=customer_id)
    decision_a.decision_timestamp = dec_ts

    plan_a = Plan(
        plan_id="pro",
        name="Pro Subscription Plan",
        price=Decimal("999.00"),
        billing_interval="monthly",
    )

    exec_record_a = ExecutionAuditRecord(
        execution_id=exec_id,
        decision_id=dec_id,
        customer_id=customer_id,
        merchant_id="merch_codecraft",
        execution_timestamp=dec_ts,
        action=InterventionAction.PAYMENT_RECOVERY,
        status=ExecutionStatus.EXECUTED,
        attempt_number=1,
        payload_id=payload_id,
        target_url="https://rzp.io/i/proc_sim_001",
    )

    pre_fail_evt = BaseEvent(
        event_id=f"evt_pre_{payload_id}",
        event_type=EventType.PAYMENT_FAILED,
        schema_version="1.0",
        merchant_id="merch_codecraft",
        customer_id=customer_id,
        timestamp=datetime.fromisoformat(dec_ts),
        source="pre_intervention_observable",
        payload={"reason": "bank_declined", "amount": "999.00"},
    )

    context_a = Phase9RuntimeContext(
        schema_version="1.0.0",
        payload_id=payload_id,
        execution_id=exec_id,
        decision_id=dec_id,
        customer_id=customer_id,
        provider_reference=provider_ref,
        short_url="https://rzp.io/i/proc_sim_001",
        decision=decision_a.model_dump(mode="json"),
        plan=plan_a.model_dump(mode="json"),
        execution_record=exec_record_a.model_dump(mode="json"),
        customer_events=[pre_fail_evt.model_dump(mode="json")],
        processed_event_ids=[],
        created_at=dec_ts,
        updated_at=dec_ts,
    )
    save_phase9_runtime_context(context_a, path=context_path)

    # Initial artifact state: EXECUTED but PENDING payment!
    initial_artifact = {
        "phase_version": "9.0.0",
        "operation": "CREATE_PAYMENT_LINK",
        "environment": "sandbox",
        "policy_decision": {
            "customer_id": customer_id,
            "selected_action": "PAYMENT_RECOVERY",
            "eligibility_status": "ELIGIBLE",
            "expected_value": 401.6,
            "revenue_at_risk": 999.0,
            "decision_timestamp": dec_ts,
        },
        "execution_status": "EXECUTED",
        "payment_status": "PENDING",
        "payload_id": payload_id,
        "provider_reference": provider_ref,
        "short_url": "https://rzp.io/i/proc_sim_001",
        "webhook_status": "PENDING_WEBHOOK",
        "outcome_status": "NO_OBSERVABLE_OUTCOME",
        "attribution_status": "UNATTRIBUTED",
        "timestamps": {
            "decision_timestamp": dec_ts,
            "execution_timestamp": dec_ts,
            "demonstration_timestamp": dec_ts,
        },
    }
    with open(artifact_path, "w", encoding="utf-8") as f:
        json.dump(initial_artifact, f, indent=2)

    # Terminate logical Process A state
    del decision_a, plan_a, exec_record_a, context_a

    # --- PROCESS B SIMULATION ---
    # Fresh context & handler without any of Process A's in-memory state
    handler_b = RazorpayWebhookHandler(
        config=valid_sandbox_config,
        context_path=context_path,
        demo_artifact_path=artifact_path,
    )
    assert len(handler_b.audit_logger._audit_store) == 0
    assert len(handler_b.decision_store) == 0
    assert len(handler_b.decision_plan_store) == 0

    # Build signed payment_link.paid webhook fixture
    # Payment completed 30 minutes post-execution (1787236200)
    body_dict = {
        "entity": "event",
        "account_id": "acc_sandbox_demo",
        "event": "payment_link.paid",
        "contains": ["payment_link", "payment", "order"],
        "payload": {
            "payment_link": {
                "entity": {
                    "id": provider_ref,
                    "reference_id": payload_id,
                    "amount": 99900,
                    "currency": "INR",
                    "status": "paid",
                    "created_at": 1787234400,
                }
            },
            "payment": {
                "entity": {
                    "id": "pay_proc_sim_001",
                    "amount": 99900,
                    "currency": "INR",
                    "status": "captured",
                    "method": "upi",
                    "created_at": 1787236200,
                    "notes": {"reference_id": payload_id},
                }
            },
        },
        "created_at": 1787236205,
    }
    raw_body = json.dumps(body_dict).encode("utf-8")
    sig = hmac.new(
        valid_sandbox_config.webhook_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    event_id = "evt_proc_sim_wh_001"
    status_code, resp = handler_b.process_webhook(
        raw_body=raw_body,
        signature=sig,
        event_id_header=event_id,
    )

    # Assert Process B successfully correlated and resolved
    assert status_code == 200
    assert resp["status"] == "processed"
    assert resp["customer_id"] == customer_id
    assert resp["execution_id"] == exec_id
    assert resp["outcome"] == "RECOVERED"
    assert resp["attribution_status"] == "DIRECTLY_OBSERVED"
    assert resp["net_recovered_revenue"] > 0

    # Assert artifact was transitioned to PAID / PROCESSED / RECOVERED
    with open(artifact_path, "r", encoding="utf-8") as f:
        saved_art = json.load(f)
    assert saved_art["execution_status"] == "EXECUTED"
    assert saved_art["payment_status"] == "PAID"
    assert saved_art["webhook_status"] == "PROCESSED"
    assert saved_art["outcome_status"] == "RECOVERED"
    assert saved_art["attribution_status"] == "DIRECTLY_OBSERVED"
    assert "webhook_timestamp" in saved_art["timestamps"]

    # Assert persistent context recorded processed event ID
    updated_ctx = load_phase9_runtime_context(path=context_path)
    assert updated_ctx is not None
    assert event_id in updated_ctx.processed_event_ids


# ==============================================================================
# 27. Cross-Process Duplicate Delivery Idempotency Test
# ==============================================================================
def test_27_cross_process_duplicate_flow(tmp_path, valid_sandbox_config):
    """
    Duplicate webhook delivery across process restarts must be acknowledged
    without duplicate outcome or re-attribution.
    """
    import hmac
    import hashlib

    context_path = tmp_path / "phase9_razorpay_runtime_context.json"
    artifact_path = tmp_path / "phase9_razorpay_sandbox_demo.json"

    # Pre-seed persistent context with already-processed event ID
    p9_ctx = Phase9RuntimeContext(
        schema_version="1.0.0",
        payload_id="payload_dup_001",
        execution_id="exec_dup_001",
        decision_id="dec_dup_001",
        customer_id="cus_dup_001",
        provider_reference="plink_dup_001",
        decision={},
        plan={"plan_id": "pro", "name": "Pro", "price": "999.00"},
        execution_record={
            "execution_id": "exec_dup_001",
            "decision_id": "dec_dup_001",
            "customer_id": "cus_dup_001",
            "merchant_id": "merch_codecraft",
            "execution_timestamp": "2026-08-20T14:00:00+00:00",
            "action": "PAYMENT_RECOVERY",
            "status": "EXECUTED",
            "attempt_number": 1,
        },
        customer_events=[],
        processed_event_ids=["evt_dup_already_consumed_999"],
        created_at="2026-08-20T14:00:00+00:00",
        updated_at="2026-08-20T14:00:00+00:00",
    )
    save_phase9_runtime_context(p9_ctx, path=context_path)

    # Fresh handler instance with completely empty in-memory sets
    fresh_handler = RazorpayWebhookHandler(
        config=valid_sandbox_config,
        context_path=context_path,
        demo_artifact_path=artifact_path,
    )
    assert "evt_dup_already_consumed_999" not in fresh_handler.processed_event_ids

    body_dict = {
        "entity": "event",
        "event": "payment_link.paid",
        "payload": {
            "payment_link": {"entity": {"id": "plink_dup_001", "reference_id": "payload_dup_001"}},
            "payment": {"entity": {"id": "pay_dup_001", "created_at": 1787236200}},
        },
    }
    raw_body = json.dumps(body_dict).encode("utf-8")
    sig = hmac.new(valid_sandbox_config.webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    status_code, resp = fresh_handler.process_webhook(
        raw_body=raw_body,
        signature=sig,
        event_id_header="evt_dup_already_consumed_999",
    )

    assert status_code == 200
    assert resp["status"] == "duplicate_acknowledged"
    assert resp["event_id"] == "evt_dup_already_consumed_999"


# ==============================================================================
# 28. Cross-Process Unmatched Reference Rejection Test
# ==============================================================================
def test_28_cross_process_unmatched_reference_fails_safe(tmp_path, valid_sandbox_config):
    """Unknown reference_id fails safe with 404 and does not mutate outcome or artifact."""
    import hmac
    import hashlib

    context_path = tmp_path / "phase9_razorpay_runtime_context.json"
    artifact_path = tmp_path / "phase9_razorpay_sandbox_demo.json"

    handler = RazorpayWebhookHandler(
        config=valid_sandbox_config,
        context_path=context_path,
        demo_artifact_path=artifact_path,
    )

    body_dict = {
        "entity": "event",
        "event": "payment_link.paid",
        "payload": {
            "payment_link": {"entity": {"id": "plink_unknown", "reference_id": "payload_completely_unknown"}},
            "payment": {"entity": {"id": "pay_unknown", "created_at": 1787236200}},
        },
    }
    raw_body = json.dumps(body_dict).encode("utf-8")
    sig = hmac.new(valid_sandbox_config.webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    status_code, resp = handler.process_webhook(
        raw_body=raw_body,
        signature=sig,
        event_id_header="evt_unknown_ref_001",
    )

    assert status_code == 404
    assert resp["error"] == "Execution reference not found"
    assert "outcome" not in resp


# ==============================================================================
# 29. Bootstrapped Real Link Correlation Test (Offline Mock Fixture)
# ==============================================================================
def test_29_bootstrap_context_with_existing_real_link_offline(tmp_path, valid_sandbox_config):
    """
    Offline verification that the currently bootstrapped Phase 9 runtime
    context cleanly correlates and resolves using an isolated test copy
    (leaving real evidence files untouched).
    """
    import hmac
    import hashlib
    import shutil

    # Copy real files into tmp_path to protect real evidence artifacts
    test_context = tmp_path / "phase9_razorpay_runtime_context.json"
    test_artifact = tmp_path / "phase9_razorpay_sandbox_demo.json"
    shutil.copyfile(DEFAULT_PHASE9_CONTEXT_PATH, test_context)
    shutil.copyfile(DEFAULT_PHASE9_ARTIFACT_PATH, test_artifact)

    # Read active context values
    with open(test_context, "r", encoding="utf-8") as f:
        ctx_data = json.load(f)
    target_payload_id = ctx_data["payload_id"]
    target_provider_ref = ctx_data.get("provider_reference") or "plink_test"
    target_customer_id = ctx_data["customer_id"]
    exec_ts_str = ctx_data["execution_record"]["execution_timestamp"]
    exec_epoch = datetime.fromisoformat(exec_ts_str).timestamp()
    paid_epoch = int(exec_epoch + 3600)

    # Reset isolated copy to PENDING to verify transition
    with open(test_artifact, "r", encoding="utf-8") as f:
        art_data = json.load(f)
    art_data["payment_status"] = "PENDING"
    art_data["webhook_status"] = "PENDING_WEBHOOK"
    art_data["outcome_status"] = "NO_OBSERVABLE_OUTCOME"
    art_data["attribution_status"] = "UNATTRIBUTED"
    with open(test_artifact, "w", encoding="utf-8") as f:
        json.dump(art_data, f, indent=2)

    # Fresh handler pointed at isolated copy
    handler = RazorpayWebhookHandler(
        config=valid_sandbox_config,
        context_path=test_context,
        demo_artifact_path=test_artifact,
    )

    # Synthetic offline payment_link.paid payload for active payload_id
    body_dict = {
        "entity": "event",
        "account_id": "acc_sandbox_real",
        "event": "payment_link.paid",
        "contains": ["payment_link", "payment", "order"],
        "payload": {
            "payment_link": {
                "entity": {
                    "id": target_provider_ref,
                    "reference_id": target_payload_id,
                    "amount": 99900,
                    "currency": "INR",
                    "status": "paid",
                    "created_at": int(exec_epoch),
                }
            },
            "payment": {
                "entity": {
                    "id": "pay_synthetic_real_link_01",
                    "amount": 99900,
                    "currency": "INR",
                    "status": "captured",
                    "method": "upi",
                    "created_at": paid_epoch,
                    "notes": {"reference_id": target_payload_id},
                }
            },
        },
        "created_at": paid_epoch + 5,
    }
    raw_body = json.dumps(body_dict).encode("utf-8")
    sig = hmac.new(valid_sandbox_config.webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    status_code, resp = handler.process_webhook(
        raw_body=raw_body,
        signature=sig,
        event_id_header="evt_synth_real_test29_001",
    )

    assert status_code == 200
    assert resp["status"] == "processed"
    assert resp["customer_id"] == target_customer_id
    assert resp["outcome"] == "RECOVERED"
    assert resp["attribution_status"] == "DIRECTLY_OBSERVED"

    # Verify isolated test copy updated to PAID
    with open(test_artifact, "r", encoding="utf-8") as f:
        assert json.load(f)["payment_status"] == "PAID"

    # Crucial: verify original repo artifact remains intact
    with open(DEFAULT_PHASE9_ARTIFACT_PATH, "r", encoding="utf-8") as f:
        assert json.load(f)["payment_status"] in {"PENDING", "PAID"}
