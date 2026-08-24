"""
Unit and Integration Test Suite for Revive Phase 6 Execution & Workflow Engine.
Tests authorization guards, cooldown-aware idempotency, payload builders, retry state transitions,
failure classifications, audit logging, ground-truth isolation, dispatcher safety, deterministic events,
event payload contracts, fallback audit preservation, and configurable evaluator metrics.
"""

from decimal import Decimal
import pytest

from app.models.enums import EventType
from app.intervention.schemas import CandidateActionScore, InterventionAction, InterventionDecision
from app.execution.config import DEFAULT_EXECUTION_CONFIG, ExecutionConfig
from app.execution.dispatcher import TestModeDispatcher
from app.execution.engine import ExecutionEngine
from app.execution.audit import ExecutionAuditLogger
from app.execution.evaluation import ExecutionEvaluator
from app.execution.payloads import PayloadBuilder
from app.execution.schemas import ExecutionAuditRecord, ExecutionStatus, FailureType
from app.execution.state_machine import ExecutionStateMachine


@pytest.fixture
def base_intervention_decision():
    candidate = CandidateActionScore(
        action=InterventionAction.PRODUCT_GUIDANCE,
        expected_value=Decimal("200.20"),
        recovery_probability_assumption=0.25,
        direct_cost=Decimal("0.00"),
        incentive_penalty_assumption=Decimal("0.00"),
        harm_penalty_assumption=Decimal("0.00"),
        is_eligible=True,
    )
    return InterventionDecision(
        customer_id="cus_exec_test_001",
        decision_timestamp="2026-08-04T10:00:00+00:00",
        risk_score=0.80,
        risk_tier="CRITICAL",
        revenue_at_risk=Decimal("800.80"),
        diagnosis="LOW_INTENT",
        diagnosis_confidence=1.0,
        diagnosis_actionability="candidate",
        eligibility_status="ELIGIBLE",
        selected_action=InterventionAction.PRODUCT_GUIDANCE,
        expected_value=Decimal("200.20"),
        candidate_scores=[candidate],
        decision_reason="Test decision",
        supporting_evidence=["Low activity"],
    )


def test_successful_product_guidance_execution(base_intervention_decision):
    engine = ExecutionEngine()
    record = engine.execute_decision(base_intervention_decision)

    assert record.status == ExecutionStatus.EXECUTED
    assert record.action == InterventionAction.PRODUCT_GUIDANCE
    assert record.attempt_number == 1
    assert record.payload_id is not None
    assert "payload_pg_" in record.payload_id
    assert len(engine.emitted_events) == 1
    assert engine.emitted_events[0].event_type == EventType.RECOVERY_ACTION_EXECUTED
    assert engine.emitted_events[0].payload["customer_id"] == "cus_exec_test_001"
    assert engine.emitted_events[0].payload["payload_id"] == record.payload_id
    assert engine.emitted_events[0].payload["target_url"] == record.target_url


def test_successful_checkout_assistance_execution(base_intervention_decision):
    decision = base_intervention_decision.model_copy(
        update={"selected_action": InterventionAction.CHECKOUT_ASSISTANCE}
    )
    engine = ExecutionEngine()
    record = engine.execute_decision(decision)

    assert record.status == ExecutionStatus.EXECUTED
    assert record.action == InterventionAction.CHECKOUT_ASSISTANCE
    assert "payload_chk_" in record.payload_id


def test_no_action_handling(base_intervention_decision):
    decision = base_intervention_decision.model_copy(
        update={
            "selected_action": InterventionAction.NO_ACTION,
            "eligibility_status": "INELIGIBLE",
        }
    )
    engine = ExecutionEngine()
    record = engine.execute_decision(decision)

    assert record.status == ExecutionStatus.NO_ACTION
    assert record.payload_id is None
    assert len(engine.emitted_events) == 0


def test_ineligible_decision_blocked(base_intervention_decision):
    decision = base_intervention_decision.model_copy(
        update={"eligibility_status": "INELIGIBLE"}
    )
    engine = ExecutionEngine()
    record = engine.execute_decision(decision)

    assert record.status == ExecutionStatus.BLOCKED
    assert "Execution refused" in record.failure_reason
    assert len(engine.emitted_events) == 1
    assert engine.emitted_events[0].event_type == EventType.POLICY_REJECTED


def test_human_review_escalation(base_intervention_decision):
    decision = base_intervention_decision.model_copy(
        update={
            "selected_action": InterventionAction.HUMAN_REVIEW,
            "eligibility_status": "ESCALATED",
        }
    )
    engine = ExecutionEngine()
    record = engine.execute_decision(decision)

    assert record.status == ExecutionStatus.ESCALATED
    assert record.action == InterventionAction.HUMAN_REVIEW
    assert record.payload_id is None
    assert len(engine.emitted_events) == 1
    assert engine.emitted_events[0].event_type == EventType.RECOVERY_ESCALATED
    assert engine.emitted_events[0].payload["payload_id"] is None


def test_retryable_failure_handling(base_intervention_decision):
    def sim_failure(act, attempt):
        return "network_timeout" if attempt == 1 else None

    engine = ExecutionEngine()
    record = engine.execute_decision(base_intervention_decision, failure_simulator=sim_failure)

    assert record.status == ExecutionStatus.EXECUTED
    assert record.attempt_number == 2
    assert len(engine.emitted_events) == 2
    assert engine.emitted_events[0].event_type == EventType.RECOVERY_ACTION_FAILED
    assert engine.emitted_events[0].payload["payload_id"] is not None
    assert engine.emitted_events[1].event_type == EventType.RECOVERY_ACTION_EXECUTED


def test_non_retryable_failure_handling(base_intervention_decision):
    def sim_failure(act, attempt):
        return "malformed payload schema error"

    engine = ExecutionEngine()
    record = engine.execute_decision(base_intervention_decision, failure_simulator=sim_failure)

    assert record.status in {ExecutionStatus.ESCALATED, ExecutionStatus.NO_ACTION}
    assert record.failure_type == FailureType.NON_RETRYABLE


def test_retry_exhaustion(base_intervention_decision):
    decision = base_intervention_decision.model_copy(
        update={"selected_action": InterventionAction.TRIAL_EXTENSION}
    )
    def sim_failure(act, attempt):
        return f"network_timeout_attempt_{attempt}"

    engine = ExecutionEngine()
    record = engine.execute_decision(decision, failure_simulator=sim_failure)

    assert record.status == ExecutionStatus.ESCALATED
    assert record.attempt_number == 3


def test_fallback_action_execution(base_intervention_decision):
    decision = base_intervention_decision.model_copy(
        update={"selected_action": InterventionAction.CHECKOUT_ASSISTANCE}
    )
    def sim_failure(act, attempt):
        return "gateway_503_service_unavailable" if act == InterventionAction.CHECKOUT_ASSISTANCE else None

    engine = ExecutionEngine()
    record = engine.execute_decision(decision, failure_simulator=sim_failure)

    assert record.status == ExecutionStatus.EXECUTED
    assert record.action == InterventionAction.REMINDER
    assert record.fallback_action == InterventionAction.REMINDER


# --- AUDIT PRESERVATION & FALLBACK IDENTITY TESTS ---

def test_fallback_audit_preservation_and_identity(base_intervention_decision):
    decision = base_intervention_decision.model_copy(
        update={"selected_action": InterventionAction.CHECKOUT_ASSISTANCE}
    )
    def sim_failure(act, attempt):
        return "gateway_503_service_unavailable" if act == InterventionAction.CHECKOUT_ASSISTANCE else None

    engine = ExecutionEngine()
    fb_record = engine.execute_decision(decision, failure_simulator=sim_failure)

    history = engine.audit_logger.get_customer_audit_history(decision.customer_id)
    assert len(history) == 4  # 3 failed primary retry attempts + 1 fallback execution record

    # Primary attempt record remains FAILED in audit history
    primary_rec = [r for r in history if r.action == InterventionAction.CHECKOUT_ASSISTANCE][0]
    assert primary_rec.status == ExecutionStatus.FAILED
    assert primary_rec.execution_id.endswith("_att1")

    # Fallback record is EXECUTED under distinct fallback execution ID (exec_fb_...)
    assert fb_record.status == ExecutionStatus.EXECUTED
    assert "exec_fb_" in fb_record.execution_id

    # Both records share the exact same decision_id
    assert primary_rec.decision_id == fb_record.decision_id == f"dec_{decision.customer_id}_{decision.decision_timestamp}"

    # Repeated submission returns fallback record without creating new records
    repeat_rec = engine.execute_decision(decision, failure_simulator=sim_failure)
    assert repeat_rec.execution_id == fb_record.execution_id
    assert len(engine.audit_logger.get_customer_audit_history(decision.customer_id)) == 4


# --- IDEMPOTENCY & COOLDOWN TESTS ---

def test_duplicate_same_decision(base_intervention_decision):
    engine = ExecutionEngine()
    rec1 = engine.execute_decision(base_intervention_decision)
    rec2 = engine.execute_decision(base_intervention_decision)

    assert rec1.execution_id == rec2.execution_id
    assert rec1.status == rec2.status
    assert len(engine.emitted_events) == 1


def test_cooldown_same_customer_inside_window(base_intervention_decision):
    engine = ExecutionEngine()
    rec1 = engine.execute_decision(base_intervention_decision)
    assert rec1.status == ExecutionStatus.EXECUTED

    decision2 = base_intervention_decision.model_copy(
        update={
            "decision_timestamp": "2026-08-04T22:00:00+00:00",
            "selected_action": InterventionAction.CHECKOUT_ASSISTANCE,
        }
    )
    rec2 = engine.execute_decision(decision2)

    assert rec2.status == ExecutionStatus.BLOCKED
    assert "cooldown window" in rec2.failure_reason
    assert len(engine.emitted_events) == 2
    assert engine.emitted_events[1].event_type == EventType.POLICY_REJECTED


def test_cooldown_same_customer_after_window(base_intervention_decision):
    engine = ExecutionEngine()
    rec1 = engine.execute_decision(base_intervention_decision)
    assert rec1.status == ExecutionStatus.EXECUTED

    decision2 = base_intervention_decision.model_copy(
        update={
            "decision_timestamp": "2026-08-07T18:00:00+00:00",
            "selected_action": InterventionAction.CHECKOUT_ASSISTANCE,
        }
    )
    rec2 = engine.execute_decision(decision2)

    assert rec2.status == ExecutionStatus.EXECUTED
    assert rec2.action == InterventionAction.CHECKOUT_ASSISTANCE


def test_different_customers_independent_cooldowns(base_intervention_decision):
    engine = ExecutionEngine()
    d_cust1 = base_intervention_decision
    d_cust2 = base_intervention_decision.model_copy(update={"customer_id": "cus_exec_test_002"})

    r1 = engine.execute_decision(d_cust1)
    r2 = engine.execute_decision(d_cust2)

    assert r1.status == ExecutionStatus.EXECUTED
    assert r2.status == ExecutionStatus.EXECUTED


def test_no_action_does_not_create_cooldown(base_intervention_decision):
    engine = ExecutionEngine()
    d_no_act = base_intervention_decision.model_copy(
        update={
            "selected_action": InterventionAction.NO_ACTION,
            "eligibility_status": "INELIGIBLE",
            "decision_timestamp": "2026-08-04T09:00:00+00:00",
        }
    )
    r1 = engine.execute_decision(d_no_act)
    assert r1.status == ExecutionStatus.NO_ACTION

    d_active = base_intervention_decision.model_copy(
        update={"decision_timestamp": "2026-08-04T10:00:00+00:00"}
    )
    r2 = engine.execute_decision(d_active)
    assert r2.status == ExecutionStatus.EXECUTED


def test_human_review_does_not_create_dispatch_cooldown(base_intervention_decision):
    engine = ExecutionEngine()
    d_hr = base_intervention_decision.model_copy(
        update={
            "selected_action": InterventionAction.HUMAN_REVIEW,
            "eligibility_status": "ESCALATED",
            "decision_timestamp": "2026-08-04T09:00:00+00:00",
        }
    )
    r1 = engine.execute_decision(d_hr)
    assert r1.status == ExecutionStatus.ESCALATED

    d_active = base_intervention_decision.model_copy(
        update={"decision_timestamp": "2026-08-04T10:00:00+00:00"}
    )
    r2 = engine.execute_decision(d_active)
    assert r2.status == ExecutionStatus.EXECUTED


# --- DETERMINISM & EVENT CONTRACT ALIGNMENT TESTS ---

def test_deterministic_repeated_execution_and_events(base_intervention_decision):
    e1 = ExecutionEngine()
    e2 = ExecutionEngine()

    r1 = e1.execute_decision(base_intervention_decision)
    r2 = e2.execute_decision(base_intervention_decision)

    assert r1.action == r2.action
    assert r1.status == r2.status
    assert r1.payload_id == r2.payload_id
    assert r1.model_dump_json() == r2.model_dump_json()

    assert len(e1.emitted_events) == 1
    assert len(e2.emitted_events) == 1

    evt1 = e1.emitted_events[0]
    evt2 = e2.emitted_events[0]

    assert evt1.event_id == evt2.event_id
    assert evt1.timestamp == evt2.timestamp
    assert evt1.model_dump_json() == evt2.model_dump_json()


def test_event_payload_contract_alignment(base_intervention_decision):
    def sim_failure(act, attempt):
        return "timeout_err" if attempt == 1 else None

    engine = ExecutionEngine()
    rec = engine.execute_decision(base_intervention_decision, failure_simulator=sim_failure)

    assert len(engine.emitted_events) == 2
    failed_evt = engine.emitted_events[0]
    exec_evt = engine.emitted_events[1]

    # Verify event payload contract includes payload_id and target_url
    assert failed_evt.payload["payload_id"] is not None
    assert failed_evt.payload["target_url"] is not None
    assert failed_evt.payload["failure_reason"] == "timeout_err"

    assert exec_evt.payload["payload_id"] is not None
    assert exec_evt.payload["target_url"] is not None


def test_live_environment_dispatch_blocked(base_intervention_decision):
    dispatcher = TestModeDispatcher()
    payload = PayloadBuilder.build_payload(base_intervention_decision)

    with pytest.raises(RuntimeError, match="Live execution dispatcher is blocked"):
        dispatcher.dispatch(payload, environment="PRODUCTION")


def test_simulated_payload_scheme_isolation(base_intervention_decision):
    payload = PayloadBuilder.build_payload(base_intervention_decision)
    assert payload.target_url.startswith("sim://revive/")


def test_evaluator_test_mode_isolation_detection(base_intervention_decision):
    rec_safe = ExecutionAuditRecord(
        execution_id="exec_test_safe",
        decision_id="dec_test_safe",
        customer_id="cus_001",
        merchant_id="merch_001",
        execution_timestamp="2026-08-04T10:00:00+00:00",
        action=InterventionAction.PRODUCT_GUIDANCE,
        status=ExecutionStatus.EXECUTED,
        attempt_number=1,
        payload_id="payload_pg_001",
        target_url="sim://revive/product-guidance?cid=cus_001",
    )
    m_safe = ExecutionEvaluator.evaluate_execution_records([rec_safe])
    assert m_safe["test_mode_isolation_rate"] == 1.0

    rec_unsafe1 = ExecutionAuditRecord(
        execution_id="exec_test_unsafe1",
        decision_id="dec_test_unsafe1",
        customer_id="cus_002",
        merchant_id="merch_001",
        execution_timestamp="2026-08-04T10:00:00+00:00",
        action=InterventionAction.PAYMENT_RECOVERY,
        status=ExecutionStatus.EXECUTED,
        attempt_number=1,
        payload_id="payload_pay_002",
        target_url="https://api.razorpay.com/v1/subscriptions/pay",
    )
    m_unsafe1 = ExecutionEvaluator.evaluate_execution_records([rec_unsafe1])
    assert m_unsafe1["test_mode_isolation_rate"] == 0.0


def test_evaluator_configurable_retry_budget():
    # Record with 3 attempts
    rec_att3 = ExecutionAuditRecord(
        execution_id="exec_test_att3",
        decision_id="dec_test_att3",
        customer_id="cus_001",
        merchant_id="merch_001",
        execution_timestamp="2026-08-04T10:00:00+00:00",
        action=InterventionAction.PRODUCT_GUIDANCE,
        status=ExecutionStatus.EXECUTED,
        attempt_number=3,
        payload_id="payload_pg_001",
        target_url="sim://revive/product-guidance?cid=cus_001",
    )
    # Default config (max_retries=2 -> max_allowed_attempts=3) -> compliant
    m_default = ExecutionEvaluator.evaluate_execution_records([rec_att3])
    assert m_default["retry_budget_compliance_rate"] == 1.0

    # Custom config (max_retries=1 -> max_allowed_attempts=2) -> violation detected!
    custom_cfg = ExecutionConfig(max_retries=1)
    m_custom = ExecutionEvaluator.evaluate_execution_records([rec_att3], config=custom_cfg)
    assert m_custom["retry_budget_compliance_rate"] == 0.0


def test_audit_record_immutability(base_intervention_decision):
    logger = ExecutionAuditLogger()
    r1 = logger.log_execution_attempt(
        decision=base_intervention_decision,
        status=ExecutionStatus.EXECUTED,
        attempt_number=1,
    )
    r2 = logger.log_execution_attempt(
        decision=base_intervention_decision,
        status=ExecutionStatus.BLOCKED,
        attempt_number=1,
    )
    assert r1.status == ExecutionStatus.EXECUTED
    assert r2.status == ExecutionStatus.EXECUTED
    assert r1 == r2
