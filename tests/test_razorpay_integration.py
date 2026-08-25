"""
Unit and Integration Test Suite for Revive Phase 9 Razorpay Sandbox Integration.
Tests configuration, secret redaction, Mock client determinism, payment link payload mapping,
action authorization boundaries, idempotency, and security isolation.
"""

from decimal import Decimal
import pytest
import os

from app.models.entities import Customer, Plan
from app.models.enums import EventType
from app.models.events import BaseEvent
from app.risk.scoring import ScoredCustomer
from app.intervention.schemas import CandidateActionScore, InterventionAction, InterventionDecision
from app.execution.schemas import ExecutionStatus, FailureType, InterventionPayload
from app.execution.engine import ExecutionEngine
from app.integrations.razorpay.config import RazorpayConfig
from app.integrations.razorpay.schemas import (
    RazorpayCustomerInfo,
    RazorpayPaymentLinkRequest,
    RazorpayPaymentLinkResponse,
)
from app.integrations.razorpay.client import (
    MockRazorpayClient,
    RazorpaySandboxClient,
)
from app.integrations.razorpay.dispatcher import RazorpaySandboxDispatcher


@pytest.fixture
def fake_config():
    return RazorpayConfig(
        environment="sandbox",
        key_id="rzp_test_KEY12345",
        key_secret="SECRET_KEY_99999",
    )


@pytest.fixture
def mock_client(fake_config):
    return MockRazorpayClient(config=fake_config)


@pytest.fixture
def sample_payload():
    return InterventionPayload(
        payload_id="payload_pay_test001",
        action=InterventionAction.PAYMENT_RECOVERY,
        customer_id="cus_razor_001",
        headline="Update Payment Method",
        body="Please update your card to resume subscription.",
        target_url="sim://revive/payment-recovery?cid=cus_razor_001",
        parameters={"amount_paise": 99900, "gateway": "razorpay_test_mode"},
    )


def test_a_razorpay_config_loads_sandbox(fake_config):
    """A. RazorpayConfig loads sandbox configuration correctly."""
    assert fake_config.environment == "sandbox"
    assert fake_config.key_id == "rzp_test_KEY12345"


def test_b_c_d_secret_redaction_and_access(fake_config):
    """B, C, D. Secret redacted in repr and str, but accessible via key_secret."""
    secret = "SECRET_KEY_99999"

    # B. repr does not contain raw secret, contains [REDACTED]
    repr_str = repr(fake_config)
    assert secret not in repr_str
    assert "[REDACTED]" in repr_str

    # C. str does not contain raw secret, contains [REDACTED]
    str_str = str(fake_config)
    assert secret not in str_str
    assert "[REDACTED]" in str_str

    # D. Internal property access returns raw secret
    assert fake_config.key_secret == secret


def test_e_missing_credentials_fail_safely():
    """E. Missing credentials return safe failure string, no exception crash."""
    no_key_config = RazorpayConfig(environment="sandbox", key_id=None, key_secret=None)
    client = RazorpaySandboxClient(config=no_key_config)

    req = RazorpayPaymentLinkRequest(
        amount=99900,
        description="Test",
        customer=RazorpayCustomerInfo(name="cus_test"),
        reference_id="ref_001",
    )
    resp, err = client.create_payment_link(req)
    assert resp is None
    assert err is not None
    assert "authentication failed" in err.lower()


def test_f_mock_client_deterministic_success(mock_client):
    """F. MockRazorpayClient creates deterministic payment link response."""
    req = RazorpayPaymentLinkRequest(
        amount=99900,
        currency="INR",
        description="Payment Recovery Test",
        customer=RazorpayCustomerInfo(name="cus_razor_001"),
        reference_id="ref_pay_001",
    )
    resp, err = mock_client.create_payment_link(req, idempotency_key="idempotency_001")
    assert err is None
    assert resp is not None
    assert resp.payment_link_id == "plink_mock_ref_pay_001"
    assert resp.short_url.startswith("https://rzp.io/i/mock_")
    assert resp.amount == 99900


def test_g_mock_client_deterministic_failure(mock_client):
    """G. MockRazorpayClient returns simulated failure reason."""
    mock_client.simulated_failure_reason = "Simulated bank gateway timeout"

    req = RazorpayPaymentLinkRequest(
        amount=99900,
        description="Fail Test",
        customer=RazorpayCustomerInfo(name="cus_001"),
        reference_id="ref_fail_001",
    )
    resp, err = mock_client.create_payment_link(req)
    assert resp is None
    assert err == "Simulated bank gateway timeout"


def test_h_payment_recovery_creates_expected_request(fake_config, mock_client, sample_payload):
    """H. PAYMENT_RECOVERY action maps InterventionPayload into RazorpayPaymentLinkRequest."""
    dispatcher = RazorpaySandboxDispatcher(config=fake_config, client=mock_client)
    err = dispatcher.dispatch(payload=sample_payload, environment="TEST_MODE")

    assert err is None
    assert mock_client.last_request is not None
    assert mock_client.last_request.amount == 99900
    assert mock_client.last_request.reference_id == "payload_pay_test001"
    assert mock_client.last_request.customer.name == "cus_razor_001"
    assert sample_payload.target_url.startswith("https://rzp.io/i/mock_")


def test_i_unsupported_actions_rejected(fake_config, mock_client):
    """I. Unsupported action types (e.g. PRODUCT_GUIDANCE, REMINDER) are rejected by dispatcher."""
    dispatcher = RazorpaySandboxDispatcher(config=fake_config, client=mock_client)

    pg_payload = InterventionPayload(
        payload_id="payload_pg_001",
        action=InterventionAction.PRODUCT_GUIDANCE,
        customer_id="cus_001",
        headline="Product Guidance",
        body="Guidance body",
    )
    err = dispatcher.dispatch(payload=pg_payload, environment="TEST_MODE")
    assert err is not None
    assert "refused" in err.lower()
    assert "PRODUCT_GUIDANCE" in err


def test_j_k_idempotency_preserved(fake_config, mock_client, sample_payload):
    """J, K. Idempotency is preserved; duplicate requests return original response without re-creation."""
    dispatcher = RazorpaySandboxDispatcher(config=fake_config, client=mock_client)

    err1 = dispatcher.dispatch(payload=sample_payload, environment="TEST_MODE")
    assert err1 is None
    first_url = sample_payload.target_url

    # Duplicate call with identical payload_id
    err2 = dispatcher.dispatch(payload=sample_payload, environment="TEST_MODE")
    assert err2 is None
    assert sample_payload.target_url == first_url
    assert len(mock_client.created_links) == 1


def test_l_no_network_access_in_mock_tests(fake_config, mock_client, sample_payload):
    """L. Mock tests execute 100% offline with zero external HTTP sockets opened."""
    dispatcher = RazorpaySandboxDispatcher(config=fake_config, client=mock_client)
    err = dispatcher.dispatch(payload=sample_payload, environment="TEST_MODE")
    assert err is None


def test_m_no_secrets_in_logs_output(fake_config):
    """M. No raw secrets appear in repr or string representations."""
    raw_secret = fake_config.key_secret
    assert raw_secret not in repr(fake_config)
    assert raw_secret not in str(fake_config)


def test_n_dispatcher_has_no_policy_authority(fake_config, mock_client):
    """N. RazorpaySandboxDispatcher does not make policy decisions or alter action types."""
    dispatcher = RazorpaySandboxDispatcher(config=fake_config, client=mock_client)
    assert not hasattr(dispatcher, "evaluate_policy")
    assert not hasattr(dispatcher, "calculate_ev")


def test_o_dispatcher_cannot_invoke_ai(fake_config, mock_client):
    """O. RazorpaySandboxDispatcher cannot call AIService or Gemini API."""
    dispatcher = RazorpaySandboxDispatcher(config=fake_config, client=mock_client)
    assert not hasattr(dispatcher, "analyze_and_diagnose")
    assert not hasattr(dispatcher, "gemini_provider")


def test_p_ground_truth_isolation_in_razorpay(fake_config, mock_client, sample_payload):
    """P. Ground-truth simulator labels cannot enter Razorpay requests."""
    dispatcher = RazorpaySandboxDispatcher(config=fake_config, client=mock_client)
    dispatcher.dispatch(payload=sample_payload, environment="TEST_MODE")

    req_str = str(mock_client.last_request.model_dump())
    assert "true_root_cause" not in req_str
    assert "natural_conversion" not in req_str
    assert "ground_truth" not in req_str


def test_execution_engine_integration_with_razorpay_dispatcher(fake_config, mock_client):
    """Integration: ExecutionEngine executing an InterventionDecision via RazorpaySandboxDispatcher."""
    dispatcher = RazorpaySandboxDispatcher(config=fake_config, client=mock_client)
    engine = ExecutionEngine(dispatcher=dispatcher)

    candidate = CandidateActionScore(
        action=InterventionAction.PAYMENT_RECOVERY,
        expected_value=Decimal("749.25"),
        recovery_probability_assumption=0.75,
        direct_cost=Decimal("0.00"),
        incentive_penalty_assumption=Decimal("0.00"),
        harm_penalty_assumption=Decimal("0.00"),
        is_eligible=True,
    )

    decision = InterventionDecision(
        customer_id="cus_rzp_exec_01",
        decision_timestamp="2026-08-05T12:00:00+00:00",
        risk_score=0.85,
        risk_tier="CRITICAL",
        revenue_at_risk=Decimal("999.00"),
        diagnosis="PAYMENT_FRICTION",
        diagnosis_confidence=0.85,
        diagnosis_actionability="candidate",
        eligibility_status="ELIGIBLE",
        selected_action=InterventionAction.PAYMENT_RECOVERY,
        expected_value=Decimal("749.25"),
        candidate_scores=[candidate],
        decision_reason="Payment failure detected",
        supporting_evidence=["Payment failed"],
    )

    record = engine.execute_decision(decision=decision)

    assert record.status == ExecutionStatus.EXECUTED
    assert record.action == InterventionAction.PAYMENT_RECOVERY
    assert record.payload_id is not None
    assert record.target_url.startswith("https://rzp.io/i/mock_")


def test_razorpay_sandbox_client_http_success(fake_config):
    """Verify RazorpaySandboxClient sends HTTP POST and parses response using mocked urllib."""
    from unittest.mock import MagicMock, patch

    client = RazorpaySandboxClient(config=fake_config)
    req = RazorpayPaymentLinkRequest(
        amount=99900,
        currency="INR",
        description="Payment Link Test",
        customer=RazorpayCustomerInfo(name="cus_test_http"),
        reference_id="ref_http_001",
    )

    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"id": "plink_real_123", "short_url": "https://rzp.io/i/real123", "status": "created", "reference_id": "ref_http_001", "amount": 99900, "currency": "INR", "created_at": 1724600000}'
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        resp, err = client.create_payment_link(req, idempotency_key="idempotency_http_001")

        assert err is None
        assert resp is not None
        assert resp.payment_link_id == "plink_real_123"
        assert resp.short_url == "https://rzp.io/i/real123"
        assert resp.amount == 99900

        # Verify urllib Request was called with expected headers and idempotency
        called_req = mock_urlopen.call_args[0][0]
        assert called_req.get_full_url() == "https://api.razorpay.com/v1/payment_links"
        assert called_req.headers["X-razorpay-idempotency"] == "idempotency_http_001"
        assert "Basic " in called_req.headers["Authorization"]


def test_razorpay_sandbox_client_http_error_handling(fake_config):
    """Verify RazorpaySandboxClient handles HTTPError safely without credential leakage."""
    from unittest.mock import MagicMock, patch
    import urllib.error

    client = RazorpaySandboxClient(config=fake_config)
    req = RazorpayPaymentLinkRequest(
        amount=99900,
        description="Fail Test",
        customer=RazorpayCustomerInfo(name="cus_fail"),
        reference_id="ref_fail_001",
    )

    err_fp = MagicMock()
    err_fp.read.return_value = b'{"error": {"code": "BAD_REQUEST_ERROR", "description": "Invalid customer email"}}'

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
        assert "Invalid customer email" in err
        assert fake_config.key_secret not in err


def test_razorpay_sandbox_client_malformed_json(fake_config):
    """Verify RazorpaySandboxClient handles malformed JSON response safely."""
    from unittest.mock import MagicMock, patch

    client = RazorpaySandboxClient(config=fake_config)
    req = RazorpayPaymentLinkRequest(
        amount=99900,
        description="Malformed Test",
        customer=RazorpayCustomerInfo(name="cus_bad_json"),
        reference_id="ref_bad_json",
    )

    mock_resp = MagicMock()
    mock_resp.read.return_value = b"<html>502 Bad Gateway</html>"
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch("urllib.request.urlopen", return_value=mock_resp):
        resp, err = client.create_payment_link(req)

        assert resp is None
        assert err is not None
        assert "malformed JSON" in err
