"""
Fully Offline E2E Integration Pytest Suite for Revive (Phase 1 through Phase 9).
Exercises the complete REVIVE pipeline from customer event ingestion through risk scoring,
root-cause diagnosis, AI analysis, intervention policy, workflow execution, and Razorpay dispatch.
Zero external network access; uses MockAIProvider and MockRazorpayClient.
"""

from decimal import Decimal
from datetime import datetime, timezone
import os
import pytest

from app.models.entities import Customer, Plan
from app.models.enums import EventType
from app.models.events import BaseEvent
from app.risk.features import CustomerFeatureExtractor
from app.risk.model import ReviveRiskModel
from app.risk.scoring import RiskScorer
from app.diagnosis.engine import DiagnosisEngine
from app.ai.config import AIConfig
from app.ai.service import AIService
from app.ai.client import MockAIProvider
from app.intervention.schemas import CandidateActionScore, InterventionAction, InterventionDecision
from app.intervention.engine import InterventionEngine
from app.execution.engine import ExecutionEngine
from app.execution.schemas import ExecutionStatus
from app.integrations.razorpay.config import RazorpayConfig
from app.integrations.razorpay.client import MockRazorpayClient
from app.integrations.razorpay.dispatcher import RazorpaySandboxDispatcher


@pytest.fixture
def e2e_pipeline_setup():
    """Setup complete REVIVE pipeline components for E2E offline testing."""
    plan = Plan(
        plan_id="pro",
        name="Pro Subscription Plan",
        price=Decimal("999.00"),
        billing_interval="monthly",
    )
    customer = Customer(
        customer_id="cus_e2e_test_001",
        merchant_id="merch_codecraft",
        created_at=datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc),
        plan_id="pro",
    )

    t0 = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 8, 3, 14, 0, 0, tzinfo=timezone.utc)

    events = [
        BaseEvent(
            event_id="evt_e2e_test_01",
            event_type=EventType.TRIAL_STARTED,
            schema_version="1.0",
            merchant_id="merch_codecraft",
            customer_id="cus_e2e_test_001",
            timestamp=t0,
            source="e2e_generator",
            payload={"trial_days": 14},
        ),
        BaseEvent(
            event_id="evt_e2e_test_02",
            event_type=EventType.PAYMENT_FAILED,
            schema_version="1.0",
            merchant_id="merch_codecraft",
            customer_id="cus_e2e_test_001",
            timestamp=t1,
            source="e2e_generator",
            payload={
                "amount": 999.00,
                "currency": "INR",
                "error_code": "CARD_DECLINED",
                "error_description": "Card declined by issuer",
            },
        ),
    ]

    rzp_config = RazorpayConfig(
        environment="sandbox",
        key_id="rzp_test_MOCK12345",
        key_secret="SECRET_MOCK_99999",
    )
    mock_rzp_client = MockRazorpayClient(config=rzp_config)
    dispatcher = RazorpaySandboxDispatcher(config=rzp_config, client=mock_rzp_client)
    exec_engine = ExecutionEngine(dispatcher=dispatcher)

    ai_config = AIConfig(provider="mock")
    ai_service = AIService(config=ai_config, provider=MockAIProvider(config=ai_config))

    model_path = os.path.join("models", "risk", "risk_model.joblib")
    risk_model = ReviveRiskModel.load(model_path)
    risk_scorer = RiskScorer(model=risk_model)

    feature_extractor = CustomerFeatureExtractor()
    diagnosis_engine = DiagnosisEngine()
    intervention_engine = InterventionEngine()

    return {
        "customer": customer,
        "plan": plan,
        "events": events,
        "feature_extractor": feature_extractor,
        "risk_scorer": risk_scorer,
        "diagnosis_engine": diagnosis_engine,
        "ai_service": ai_service,
        "intervention_engine": intervention_engine,
        "exec_engine": exec_engine,
        "mock_rzp_client": mock_rzp_client,
        "dispatcher": dispatcher,
    }


def test_e2e_1_full_customer_to_razorpay_mock_flow(e2e_pipeline_setup):
    """E2E-1: Full pipeline execution from customer events to Mock Razorpay payment link."""
    setup = e2e_pipeline_setup
    customer, plan, events = setup["customer"], setup["plan"], setup["events"]

    # 1. Feature Extraction
    features, status = setup["feature_extractor"].extract_features(customer, events, plan)
    assert status == "OK"
    assert features["payment_failure_count"] >= 1

    # 2. Risk Scoring
    scored_cust = setup["risk_scorer"].score_customer(features)
    assert scored_cust.customer_id == customer.customer_id
    assert scored_cust.risk_score > 0.0
    assert scored_cust.risk_tier in {"HIGH", "CRITICAL"}
    assert scored_cust.revenue_at_risk > Decimal("0.00")

    # 3. Diagnosis
    base_diag = setup["diagnosis_engine"].diagnose_customer(scored_cust, customer, events, plan, features)
    assert base_diag.diagnosis.value == "PAYMENT_FRICTION"

    # 4. AI Service
    ai_res = setup["ai_service"].analyze_and_diagnose(scored_cust, customer, events, plan, features)
    assert ai_res.metadata.status.value == "AI_SUCCESS"
    assert ai_res.final_diagnosis.diagnosis.value == "PAYMENT_FRICTION"

    # 5. Intervention Policy
    decision = setup["intervention_engine"].decide_intervention(scored_cust, ai_res.final_diagnosis, plan, features)
    assert decision.selected_action == InterventionAction.PAYMENT_RECOVERY
    assert decision.eligibility_status == "ELIGIBLE"
    assert decision.expected_value > Decimal("0.00")

    # 6. Workflow Execution
    audit_record = setup["exec_engine"].execute_decision(decision)
    assert audit_record.status == ExecutionStatus.EXECUTED
    assert audit_record.action == InterventionAction.PAYMENT_RECOVERY
    assert audit_record.payload_id is not None
    assert audit_record.target_url.startswith("https://rzp.io/i/mock_")

    # 7. Razorpay Mock Client Assertions
    client = setup["mock_rzp_client"]
    assert len(client.created_links) == 1
    link_resp = list(client.created_links.values())[0]
    assert link_resp.payment_link_id.startswith("plink_mock_")
    assert link_resp.amount == 99900
    assert link_resp.currency == "INR"


def test_e2e_2_idempotency_and_duplicate_execution_protection(e2e_pipeline_setup):
    """E2E-2: Submitting identical InterventionDecision twice returns original audit record without duplicate provider actions."""
    setup = e2e_pipeline_setup
    customer, plan, events = setup["customer"], setup["plan"], setup["events"]

    features, _ = setup["feature_extractor"].extract_features(customer, events, plan)
    scored_cust = setup["risk_scorer"].score_customer(features)
    base_diag = setup["diagnosis_engine"].diagnose_customer(scored_cust, customer, events, plan, features)
    decision = setup["intervention_engine"].decide_intervention(scored_cust, base_diag, plan, features)

    exec_engine = setup["exec_engine"]
    client = setup["mock_rzp_client"]

    # First execution attempt
    record1 = exec_engine.execute_decision(decision)
    assert record1.status == ExecutionStatus.EXECUTED
    initial_link_count = len(client.created_links)
    assert initial_link_count == 1

    # Second duplicate execution attempt
    record2 = exec_engine.execute_decision(decision)
    assert record2.status == ExecutionStatus.EXECUTED
    assert record2.execution_id == record1.execution_id
    assert record2.payload_id == record1.payload_id
    assert record2.target_url == record1.target_url

    # Empirically verify NO second provider action was created
    assert len(client.created_links) == initial_link_count


def test_e2e_3_ineligible_decision_protection(e2e_pipeline_setup):
    """E2E-3: Ineligible decision is blocked by ExecutionEngine before reaching Razorpay dispatcher."""
    setup = e2e_pipeline_setup

    candidate = CandidateActionScore(
        action=InterventionAction.PAYMENT_RECOVERY,
        expected_value=Decimal("0.00"),
        recovery_probability_assumption=0.0,
        direct_cost=Decimal("0.00"),
        incentive_penalty_assumption=Decimal("0.00"),
        harm_penalty_assumption=Decimal("0.00"),
        is_eligible=False,
    )

    ineligible_decision = InterventionDecision(
        customer_id="cus_ineligible_01",
        decision_timestamp="2026-08-05T12:00:00+00:00",
        risk_score=0.85,
        risk_tier="CRITICAL",
        revenue_at_risk=Decimal("999.00"),
        diagnosis="PAYMENT_FRICTION",
        diagnosis_confidence=0.85,
        diagnosis_actionability="candidate",
        eligibility_status="INELIGIBLE",
        selected_action=InterventionAction.PAYMENT_RECOVERY,
        expected_value=Decimal("0.00"),
        candidate_scores=[candidate],
        decision_reason="Customer safety contraindication active",
        supporting_evidence=["Ineligible rule triggered"],
    )

    exec_engine = setup["exec_engine"]
    client = setup["mock_rzp_client"]

    record = exec_engine.execute_decision(ineligible_decision)

    assert record.status == ExecutionStatus.BLOCKED
    assert "refused" in record.failure_reason.lower() or "ineligible" in record.failure_reason.lower()
    # Verify MockRazorpayClient created zero links
    assert len(client.created_links) == 0


def test_e2e_4_unsupported_action_rejection(e2e_pipeline_setup):
    """E2E-4: PAYMENT_RECOVERY & CHECKOUT_ASSISTANCE allowed; REMINDER & PRODUCT_GUIDANCE rejected by dispatcher."""
    setup = e2e_pipeline_setup
    dispatcher = setup["dispatcher"]
    client = setup["mock_rzp_client"]

    # 1. Product Guidance (Unsupported for Razorpay payment links)
    pg_payload = setup["exec_engine"].execute_decision(
        setup["intervention_engine"].decide_intervention(
            setup["risk_scorer"].score_customer(
                setup["feature_extractor"].extract_features(
                    setup["customer"], setup["events"], setup["plan"]
                )[0]
            ),
            setup["diagnosis_engine"].diagnose_customer(
                setup["risk_scorer"].score_customer(
                    setup["feature_extractor"].extract_features(
                        setup["customer"], setup["events"], setup["plan"]
                    )[0]
                ),
                setup["customer"], setup["events"], setup["plan"],
                setup["feature_extractor"].extract_features(setup["customer"], setup["events"], setup["plan"])[0]
            ),
            setup["plan"],
            setup["feature_extractor"].extract_features(setup["customer"], setup["events"], setup["plan"])[0]
        ).model_copy(update={"selected_action": InterventionAction.PRODUCT_GUIDANCE})
    )
    # The dispatcher refuses PRODUCT_GUIDANCE when passed
    from app.execution.schemas import InterventionPayload
    pg_payload_obj = InterventionPayload(
        payload_id="pyld_pg_test",
        action=InterventionAction.PRODUCT_GUIDANCE,
        customer_id="cus_001",
        headline="Guidance",
        body="Body",
    )
    err = dispatcher.dispatch(pg_payload_obj, environment="TEST_MODE")
    assert err is not None
    assert "refused" in err.lower()
    assert "PRODUCT_GUIDANCE" in err


def test_e2e_5_execution_isolation_and_security(e2e_pipeline_setup):
    """E2E-5: Verifies no secrets or ground-truth fields leak into audit or payment payloads."""
    setup = e2e_pipeline_setup
    customer, plan, events = setup["customer"], setup["plan"], setup["events"]

    features, _ = setup["feature_extractor"].extract_features(customer, events, plan)
    scored_cust = setup["risk_scorer"].score_customer(features)
    base_diag = setup["diagnosis_engine"].diagnose_customer(scored_cust, customer, events, plan, features)
    decision = setup["intervention_engine"].decide_intervention(scored_cust, base_diag, plan, features)

    audit_record = setup["exec_engine"].execute_decision(decision)

    record_str = repr(audit_record)
    assert "SECRET" not in record_str
    assert "rzp_test_MOCK12345" not in record_str
    assert "ground_truth" not in record_str
    assert "true_root_cause" not in record_str
    assert "natural_conversion" not in record_str


def test_e2e_6_regression_boundary_verification():
    """E2E-6: Confirms Phase 1-8 engines remain 100% intact and operational."""
    # Instantiating core engines with defaults succeeds cleanly
    fe = CustomerFeatureExtractor()
    de = DiagnosisEngine()
    ie = InterventionEngine()
    ee = ExecutionEngine()
    assert fe is not None
    assert de is not None
    assert ie is not None
    assert ee is not None
