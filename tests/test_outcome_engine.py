"""
Unit and Integration Test Suite for Revive Phase 7 Outcome Measurement & Revenue Attribution Engine.
Tests temporal isolation, microsecond boundaries, pre-existing outcome protection, canonical resolution,
attribution levels, revenue accounting, idempotency, determinism, lineage completeness, and ground-truth isolation.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest

from app.models.enums import EventType
from app.models.events import BaseEvent
from app.models.entities import Plan
from app.intervention.schemas import CandidateActionScore, InterventionAction, InterventionDecision
from app.execution.schemas import ExecutionAuditRecord, ExecutionStatus
from app.outcome.config import DEFAULT_OUTCOME_CONFIG, OutcomeConfig
from app.outcome.engine import OutcomeEngine
from app.outcome.evaluation import OutcomeEvaluator
from app.outcome.observer import EventObserver, parse_iso_timestamp
from app.outcome.schemas import AttributionMethod, AttributionStatus, OutcomeRecord, OutcomeType


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
def base_intervention_decision():
    candidate = CandidateActionScore(
        action=InterventionAction.PAYMENT_RECOVERY,
        expected_value=Decimal("450.00"),
        recovery_probability_assumption=0.45,
        direct_cost=Decimal("3.00"),
        incentive_penalty_assumption=Decimal("0.00"),
        harm_penalty_assumption=Decimal("0.00"),
        is_eligible=True,
    )
    return InterventionDecision(
        customer_id="cus_out_test_001",
        decision_timestamp="2026-08-05T12:00:00+00:00",
        risk_score=0.85,
        risk_tier="CRITICAL",
        revenue_at_risk=Decimal("999.00"),
        diagnosis="PAYMENT_FRICTION",
        diagnosis_confidence=1.0,
        diagnosis_actionability="candidate",
        eligibility_status="ELIGIBLE",
        selected_action=InterventionAction.PAYMENT_RECOVERY,
        expected_value=Decimal("450.00"),
        candidate_scores=[candidate],
        decision_reason="Payment failure recovery candidate",
        supporting_evidence=["Payment attempt failed"],
    )


@pytest.fixture
def execution_record(base_intervention_decision):
    return ExecutionAuditRecord(
        execution_id="exec_cus_out_test_001_2026-08-05T12:00:00+00:00_att1",
        decision_id="dec_cus_out_test_001_2026-08-05T12:00:00+00:00",
        customer_id="cus_out_test_001",
        merchant_id="merch_codecraft",
        execution_timestamp="2026-08-05T12:00:00+00:00",
        action=InterventionAction.PAYMENT_RECOVERY,
        status=ExecutionStatus.EXECUTED,
        attempt_number=1,
        payload_id="payload_pay_001",
        target_url="sim://revive/payment-recovery?cid=cus_out_test_001",
    )


def create_event(evt_type: EventType, customer_id: str, ts_str: str, payload: dict = None) -> BaseEvent:
    return BaseEvent(
        event_id=f"evt_{customer_id}_{evt_type.value}_{ts_str}",
        event_type=evt_type,
        schema_version="1.0",
        merchant_id="merch_codecraft",
        customer_id=customer_id,
        timestamp=datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc),
        source="test_source",
        payload=payload or {},
    )


# --- 1. SUCCESSFUL RECOVERY & ATTRIBUTION TESTS ---

def test_successful_payment_recovery_outcome(execution_record, base_intervention_decision, sample_plan):
    engine = OutcomeEngine()
    post_event = create_event(
        EventType.PAYMENT_SUCCEEDED,
        "cus_out_test_001",
        "2026-08-05T14:00:00+00:00",
        {"payment_id": "pay_sim_12345", "amount": 999.00},
    )

    record = engine.measure_outcome(
        execution_record=execution_record,
        decision=base_intervention_decision,
        customer_events=[post_event],
        plan=sample_plan,
        observation_window_hours=168.0,
    )

    assert record.outcome == OutcomeType.RECOVERED
    assert record.attribution_status == AttributionStatus.DIRECTLY_OBSERVED
    assert record.attribution_method == AttributionMethod.DETERMINISTIC_RULES
    assert record.gross_observed_revenue == Decimal("999.00")
    assert record.attributable_revenue == Decimal("999.00")
    assert record.intervention_cost == Decimal("3.00")
    assert record.net_recovered_revenue == Decimal("996.00")
    assert record.revenue_at_risk_at_decision == Decimal("999.00")
    assert record.payment_reference == "pay_sim_12345"


def test_temporally_associated_product_guidance_outcome(base_intervention_decision, sample_plan):
    decision = base_intervention_decision.model_copy(
        update={"selected_action": InterventionAction.PRODUCT_GUIDANCE}
    )
    exec_rec = ExecutionAuditRecord(
        execution_id="exec_cus_out_test_001_2026-08-05T12:00:00+00:00_att1",
        decision_id="dec_cus_out_test_001_2026-08-05T12:00:00+00:00",
        customer_id="cus_out_test_001",
        merchant_id="merch_codecraft",
        execution_timestamp="2026-08-05T12:00:00+00:00",
        action=InterventionAction.PRODUCT_GUIDANCE,
        status=ExecutionStatus.EXECUTED,
        attempt_number=1,
        payload_id="payload_pg_001",
        target_url="sim://revive/product-guidance",
    )
    post_event = create_event(
        EventType.SUBSCRIPTION_CREATED,
        "cus_out_test_001",
        "2026-08-06T10:00:00+00:00",
        {"price": 999.00},
    )

    engine = OutcomeEngine()
    record = engine.measure_outcome(exec_rec, decision, [post_event], plan=sample_plan)

    assert record.outcome == OutcomeType.RECOVERED
    assert record.attribution_status == AttributionStatus.TEMPORALLY_ASSOCIATED
    assert record.attribution_method == AttributionMethod.TEMPORAL_WINDOW_ASSOCIATION
    assert record.gross_observed_revenue == Decimal("999.00")
    assert record.attributable_revenue == Decimal("499.50")
    assert record.intervention_cost == Decimal("0.00")
    assert record.net_recovered_revenue == Decimal("499.50")


# --- 2. TEMPORAL INTEGRITY & PRE-EXISTING CONVERSION TESTS ---

def test_pre_existing_conversion_not_attributed(execution_record, base_intervention_decision, sample_plan):
    # Event occurred BEFORE execution (2026-08-05T10:00:00 < 12:00:00)
    pre_event = create_event(
        EventType.PAYMENT_SUCCEEDED,
        "cus_out_test_001",
        "2026-08-05T10:00:00+00:00",
        {"payment_id": "pay_pre_999"},
    )

    engine = OutcomeEngine()
    record = engine.measure_outcome(execution_record, base_intervention_decision, [pre_event], plan=sample_plan)

    assert record.outcome == OutcomeType.ALREADY_CONVERTED
    assert record.attribution_status == AttributionStatus.UNATTRIBUTED
    assert record.attributable_revenue == Decimal("0.00")
    assert record.net_recovered_revenue == Decimal("-3.00")  # 0.00 - cost(3.00) <= 0


def test_event_outside_observation_window_ignored(execution_record, base_intervention_decision, sample_plan):
    late_event = create_event(
        EventType.PAYMENT_SUCCEEDED,
        "cus_out_test_001",
        "2026-08-15T12:00:00+00:00",
        {"payment_id": "pay_late_123"},
    )

    engine = OutcomeEngine()
    record = engine.measure_outcome(
        execution_record,
        base_intervention_decision,
        [late_event],
        plan=sample_plan,
        observation_window_hours=168.0,
        measurement_timestamp="2026-08-13T12:00:00+00:00",
    )

    assert record.outcome == OutcomeType.NOT_RECOVERED
    assert record.attribution_status == AttributionStatus.UNATTRIBUTED
    assert record.attributable_revenue == Decimal("0.00")


# --- 3. MICROSECOND BOUNDARY CONDITION REGRESSION TESTS ---

def test_microsecond_boundary_conditions(execution_record, base_intervention_decision, sample_plan):
    engine = OutcomeEngine()
    exec_dt = parse_iso_timestamp(execution_record.execution_timestamp)
    window_hours = 168.0
    end_dt = exec_dt + timedelta(hours=window_hours)

    # 1. Event exactly AT execution timestamp -> pre-existing (ALREADY_CONVERTED)
    evt_at_exec = BaseEvent(
        event_id="evt_at_exec",
        event_type=EventType.PAYMENT_SUCCEEDED,
        merchant_id="merch_codecraft",
        customer_id="cus_out_test_001",
        timestamp=exec_dt,
        source="test",
        payload={"amount": 999.00},
    )
    r_at_exec = engine.measure_outcome(execution_record, base_intervention_decision, [evt_at_exec], plan=sample_plan)
    assert r_at_exec.outcome == OutcomeType.ALREADY_CONVERTED
    assert r_at_exec.attribution_status == AttributionStatus.UNATTRIBUTED
    assert r_at_exec.attributable_revenue == Decimal("0.00")

    # 2. Event 1 microsecond AFTER execution timestamp -> eligible post-execution (RECOVERED)
    evt_after_exec = BaseEvent(
        event_id="evt_after_exec",
        event_type=EventType.PAYMENT_SUCCEEDED,
        merchant_id="merch_codecraft",
        customer_id="cus_out_test_001",
        timestamp=exec_dt + timedelta(microseconds=1),
        source="test",
        payload={"amount": 999.00},
    )
    e_new = OutcomeEngine()
    r_after_exec = e_new.measure_outcome(execution_record, base_intervention_decision, [evt_after_exec], plan=sample_plan)
    assert r_after_exec.outcome == OutcomeType.RECOVERED

    # 3. Event exactly AT observation end -> eligible post-execution (RECOVERED)
    evt_at_end = BaseEvent(
        event_id="evt_at_end",
        event_type=EventType.PAYMENT_SUCCEEDED,
        merchant_id="merch_codecraft",
        customer_id="cus_out_test_001",
        timestamp=end_dt,
        source="test",
        payload={"amount": 999.00},
    )
    e_end = OutcomeEngine()
    r_at_end = e_end.measure_outcome(execution_record, base_intervention_decision, [evt_at_end], plan=sample_plan)
    assert r_at_end.outcome == OutcomeType.RECOVERED

    # 4. Event 1 microsecond AFTER observation end -> excluded (NOT_RECOVERED)
    evt_past_end = BaseEvent(
        event_id="evt_past_end",
        event_type=EventType.PAYMENT_SUCCEEDED,
        merchant_id="merch_codecraft",
        customer_id="cus_out_test_001",
        timestamp=end_dt + timedelta(microseconds=1),
        source="test",
        payload={"amount": 999.00},
    )
    e_past = OutcomeEngine()
    r_past_end = e_past.measure_outcome(
        execution_record,
        base_intervention_decision,
        [evt_past_end],
        plan=sample_plan,
        measurement_timestamp=(end_dt + timedelta(days=1)).isoformat(),
    )
    assert r_past_end.outcome == OutcomeType.NOT_RECOVERED
    assert r_past_end.attributable_revenue == Decimal("0.00")


# --- 4. NON-RECOVERY & FAILURE OUTCOMES ---

def test_trial_expired_outcome(execution_record, base_intervention_decision, sample_plan):
    expired_event = create_event(
        EventType.TRIAL_EXPIRED,
        "cus_out_test_001",
        "2026-08-06T12:00:00+00:00",
    )

    engine = OutcomeEngine()
    record = engine.measure_outcome(execution_record, base_intervention_decision, [expired_event], plan=sample_plan)

    assert record.outcome == OutcomeType.EXPIRED
    assert record.attribution_status == AttributionStatus.UNATTRIBUTED
    assert record.attributable_revenue == Decimal("0.00")


def test_no_observable_outcome_when_window_open(execution_record, base_intervention_decision, sample_plan):
    engine = OutcomeEngine()
    record = engine.measure_outcome(
        execution_record,
        base_intervention_decision,
        [],
        plan=sample_plan,
        observation_window_hours=168.0,
        measurement_timestamp="2026-08-06T12:00:00+00:00",  # Only 24h passed
    )

    assert record.outcome == OutcomeType.NO_OBSERVABLE_OUTCOME
    assert record.attribution_status == AttributionStatus.UNATTRIBUTED


def test_not_recovered_when_window_closed(execution_record, base_intervention_decision, sample_plan):
    engine = OutcomeEngine()
    record = engine.measure_outcome(
        execution_record,
        base_intervention_decision,
        [],
        plan=sample_plan,
        observation_window_hours=168.0,
        measurement_timestamp="2026-08-13T12:00:00+00:00",  # 8 days passed
    )

    assert record.outcome == OutcomeType.NOT_RECOVERED
    assert record.attribution_status == AttributionStatus.UNATTRIBUTED


def test_no_action_baseline_not_attributed(base_intervention_decision, sample_plan):
    decision = base_intervention_decision.model_copy(
        update={"selected_action": InterventionAction.NO_ACTION}
    )
    exec_rec = ExecutionAuditRecord(
        execution_id="exec_cus_out_test_001_2026-08-05T12:00:00+00:00_att1",
        decision_id="dec_cus_out_test_001_2026-08-05T12:00:00+00:00",
        customer_id="cus_out_test_001",
        merchant_id="merch_codecraft",
        execution_timestamp="2026-08-05T12:00:00+00:00",
        action=InterventionAction.NO_ACTION,
        status=ExecutionStatus.NO_ACTION,
        attempt_number=1,
    )
    post_event = create_event(
        EventType.SUBSCRIPTION_CREATED,
        "cus_out_test_001",
        "2026-08-06T12:00:00+00:00",
        {"price": 999.00},
    )

    engine = OutcomeEngine()
    record = engine.measure_outcome(exec_rec, decision, [post_event], plan=sample_plan)

    assert record.outcome == OutcomeType.CONVERTED
    assert record.attribution_status == AttributionStatus.UNATTRIBUTED
    assert record.attributable_revenue == Decimal("0.00")
    assert record.net_recovered_revenue == Decimal("0.00")


def test_blocked_or_escalated_execution_not_attributed(base_intervention_decision, sample_plan):
    exec_rec = ExecutionAuditRecord(
        execution_id="exec_cus_out_test_001_2026-08-05T12:00:00+00:00_att1",
        decision_id="dec_cus_out_test_001_2026-08-05T12:00:00+00:00",
        customer_id="cus_out_test_001",
        merchant_id="merch_codecraft",
        execution_timestamp="2026-08-05T12:00:00+00:00",
        action=InterventionAction.HUMAN_REVIEW,
        status=ExecutionStatus.ESCALATED,
        attempt_number=1,
    )
    post_event = create_event(
        EventType.PAYMENT_SUCCEEDED,
        "cus_out_test_001",
        "2026-08-06T12:00:00+00:00",
        {"amount": 999.00},
    )

    engine = OutcomeEngine()
    record = engine.measure_outcome(exec_rec, base_intervention_decision, [post_event], plan=sample_plan)

    assert record.outcome == OutcomeType.CONVERTED
    assert record.attribution_status == AttributionStatus.UNATTRIBUTED
    assert record.attributable_revenue == Decimal("0.00")


# --- 5. IDEMPOTENCY & DETERMINISM TESTS ---

def test_idempotency_same_input_returns_same_record(execution_record, base_intervention_decision, sample_plan):
    post_event = create_event(
        EventType.PAYMENT_SUCCEEDED,
        "cus_out_test_001",
        "2026-08-05T14:00:00+00:00",
        {"payment_id": "pay_sim_12345", "amount": 999.00},
    )

    engine = OutcomeEngine()
    rec1 = engine.measure_outcome(execution_record, base_intervention_decision, [post_event], plan=sample_plan)
    rec2 = engine.measure_outcome(execution_record, base_intervention_decision, [post_event], plan=sample_plan)

    assert rec1.outcome_id == rec2.outcome_id
    assert rec1 == rec2
    assert len(engine.get_customer_outcomes("cus_out_test_001")) == 1


def test_deterministic_repeated_engine_resolution(execution_record, base_intervention_decision, sample_plan):
    post_event = create_event(
        EventType.PAYMENT_SUCCEEDED,
        "cus_out_test_001",
        "2026-08-05T14:00:00+00:00",
        {"payment_id": "pay_sim_12345", "amount": 999.00},
    )

    e1 = OutcomeEngine()
    e2 = OutcomeEngine()

    r1 = e1.measure_outcome(execution_record, base_intervention_decision, [post_event], plan=sample_plan)
    r2 = e2.measure_outcome(execution_record, base_intervention_decision, [post_event], plan=sample_plan)

    assert r1.model_dump_json() == r2.model_dump_json()


# --- 6. OBSERVATION WINDOW BOUNDARY CONFIGURATION TESTS ---

def test_configurable_observation_windows(execution_record, base_intervention_decision, sample_plan):
    post_event = create_event(
        EventType.PAYMENT_SUCCEEDED,
        "cus_out_test_001",
        "2026-08-07T12:00:00+00:00",  # 48h after execution
        {"payment_id": "pay_48h"},
    )

    engine = OutcomeEngine()

    # 24h window -> event is outside window -> NOT_RECOVERED
    rec_24 = engine.measure_outcome(
        execution_record,
        base_intervention_decision,
        [post_event],
        plan=sample_plan,
        observation_window_hours=24.0,
        measurement_timestamp="2026-08-08T12:00:00+00:00",
    )
    assert rec_24.outcome == OutcomeType.NOT_RECOVERED

    # 72h window -> event is inside window -> RECOVERED
    rec_72 = engine.measure_outcome(
        execution_record,
        base_intervention_decision,
        [post_event],
        plan=sample_plan,
        observation_window_hours=72.0,
        measurement_timestamp="2026-08-08T12:00:00+00:00",
    )
    assert rec_72.outcome == OutcomeType.RECOVERED


# --- 7. EVALUATOR METRICS & LEAKAGE TESTS ---

def test_evaluator_metrics_and_leakage(execution_record, base_intervention_decision, sample_plan):
    post_event = create_event(
        EventType.PAYMENT_SUCCEEDED,
        "cus_out_test_001",
        "2026-08-05T14:00:00+00:00",
        {"payment_id": "pay_sim_12345", "amount": 999.00},
    )

    engine = OutcomeEngine()
    rec = engine.measure_outcome(execution_record, base_intervention_decision, [post_event], plan=sample_plan)

    metrics = OutcomeEvaluator.evaluate_outcome_records([rec])

    assert metrics["total_outcomes_processed"] == 1
    assert metrics["outcome_counts"]["RECOVERED"] == 1
    assert metrics["attribution_counts"]["DIRECTLY_OBSERVED"] == 1
    assert metrics["gross_observed_revenue"] == 999.00
    assert metrics["attributable_revenue"] == 999.00
    assert metrics["intervention_cost"] == 3.00
    assert metrics["net_recovered_revenue"] == 996.00
    assert metrics["ground_truth_leakage_rate"] == 0.0
    assert metrics["lineage_completeness_rate"] == 1.0
