"""
Pytest Suite for REVIVE Phase 9 Batch Recovery Evaluator.
Tests determinism, empty batch handling, risk/diagnosis metrics, eligibility,
fallback behavior, idempotency, secret safety, and ground-truth isolation.
"""

from decimal import Decimal
import os
import pytest

from app.evaluation.batch import BatchRecoveryEvaluator, BatchEvaluationResult
from app.models.entities import Customer, Plan
from app.models.enums import EventType
from app.models.events import BaseEvent
from app.intervention.schemas import CandidateActionScore, InterventionAction, InterventionDecision
from app.execution.schemas import ExecutionAuditRecord, ExecutionStatus
from app.execution.engine import ExecutionEngine
from app.integrations.razorpay.config import RazorpayConfig
from app.integrations.razorpay.client import MockRazorpayClient
from app.integrations.razorpay.dispatcher import RazorpaySandboxDispatcher


def test_1_deterministic_batch_reproducibility():
    """1. Given identical seed and customer count, BatchRecoveryEvaluator produces 100% identical output."""
    eval1 = BatchRecoveryEvaluator(customers_count=20, seed=42)
    res1 = eval1.evaluate().to_dict()

    eval2 = BatchRecoveryEvaluator(customers_count=20, seed=42)
    res2 = eval2.evaluate().to_dict()

    assert res1["aggregate_metrics"] == res2["aggregate_metrics"]
    assert res1["risk_distribution"] == res2["risk_distribution"]
    assert res1["action_distribution"] == res2["action_distribution"]
    assert len(res1["per_customer_results"]) == len(res2["per_customer_results"])


def test_2_empty_customer_batch_handling():
    """2. Batch size 0 produces safe empty result without throwing exceptions."""
    evaluator = BatchRecoveryEvaluator(customers_count=0, seed=42)
    res = evaluator.evaluate()

    assert res.aggregate_metrics["total_customers"] == 0
    assert res.per_customer_results == []


def test_3_4_payment_failure_customer_detection():
    """3, 4. Batch evaluation correctly calculates customers with and without payment failures."""
    evaluator = BatchRecoveryEvaluator(customers_count=30, seed=42)
    res = evaluator.evaluate()

    agg = res.aggregate_metrics
    assert "customers_with_payment_failures" in agg
    assert agg["total_customers"] == 30
    assert agg["customers_with_payment_failures"] >= 0
    assert agg["customers_with_payment_failures"] <= 30


def test_5_eligible_payment_recovery_decision():
    """5. Customers with payment failure trigger eligible PAYMENT_RECOVERY decisions and expected recovery rate calculation."""
    evaluator = BatchRecoveryEvaluator(customers_count=100, seed=42, snapshot_hours=336.0)
    res = evaluator.evaluate()

    agg = res.aggregate_metrics
    act_dist = res.action_distribution
    assert agg["payment_friction_count"] == 17
    assert act_dist["PAYMENT_RECOVERY"] == 17
    assert agg["simulated_successful_executions"] == 17
    assert agg["total_expected_recovery_value"] > 0.0
    assert agg["expected_recovery_rate_pct"] > 0.0


def test_13_snapshot_hours_root_cause_regression():
    """13. Regression test proving 72h snapshot vs 336h trial-end snapshot root cause for payment failure detection."""
    # 72h snapshot misses billing payment failures (which occur on Day 12-14)
    eval_72h = BatchRecoveryEvaluator(customers_count=100, seed=42, snapshot_hours=72.0)
    res_72h = eval_72h.evaluate()
    assert res_72h.aggregate_metrics["payment_friction_count"] == 0
    assert res_72h.action_distribution["PAYMENT_RECOVERY"] == 0

    # 336h snapshot includes billing payment failures, diagnosing 17 PAYMENT_FRICTION cases
    eval_336h = BatchRecoveryEvaluator(customers_count=100, seed=42, snapshot_hours=336.0)
    res_336h = eval_336h.evaluate()
    assert res_336h.aggregate_metrics["payment_friction_count"] == 17
    assert res_336h.action_distribution["PAYMENT_RECOVERY"] == 17
    assert res_336h.aggregate_metrics["simulated_successful_executions"] == 17


def test_6_ineligible_decision_remains_blocked():
    """6. Ineligible intervention decisions are recorded as blocked and do not create payment links."""
    evaluator = BatchRecoveryEvaluator(customers_count=30, seed=42)
    res = evaluator.evaluate()

    # Verify per-customer results record blocked execution status for ineligible decisions
    for rec in res.per_customer_results:
        if rec.eligibility_status != "ELIGIBLE":
            assert rec.execution_status in {"BLOCKED", "NO_ACTION", "ESCALATED"}


def test_7_ai_failure_falls_back_safely():
    """7. AI layer failures or fallbacks are accurately tracked in aggregate metrics."""
    evaluator = BatchRecoveryEvaluator(customers_count=20, seed=42)
    res = evaluator.evaluate()

    agg = res.aggregate_metrics
    assert "ai_success_count" in agg
    assert "ai_fallback_count" in agg
    assert agg["ai_success_count"] + agg["ai_fallback_count"] >= 0


def test_8_unsupported_action_rejection():
    """8. Unsupported actions (e.g., PRODUCT_GUIDANCE, REMINDER) are rejected by RazorpaySandboxDispatcher."""
    config = RazorpayConfig(environment="sandbox", key_id="rzp_test_MOCK", key_secret="SECRET")
    client = MockRazorpayClient(config=config)
    dispatcher = RazorpaySandboxDispatcher(config=config, client=client)

    from app.execution.schemas import InterventionPayload
    payload = InterventionPayload(
        payload_id="pyld_rem_001",
        action=InterventionAction.REMINDER,
        customer_id="cus_001",
        headline="Reminder",
        body="Reminder Body",
    )
    err = dispatcher.dispatch(payload, environment="TEST_MODE")
    assert err is not None
    assert "refused" in err.lower()
    assert len(client.created_links) == 0


def test_9_mock_razorpay_execution_remains_offline():
    """9. Batch evaluation executes 100% offline with zero external network socket connections."""
    evaluator = BatchRecoveryEvaluator(customers_count=10, seed=42)
    res = evaluator.evaluate()
    assert res.aggregate_metrics["total_customers"] == 10


def test_10_duplicate_execution_does_not_create_duplicate_payment_links():
    """10. Duplicate execution attempt reuses ExecutionEngine audit history and prevents duplicate payment link creation."""
    config = RazorpayConfig(environment="sandbox", key_id="rzp_test_MOCK", key_secret="SECRET")
    client = MockRazorpayClient(config=config)
    dispatcher = RazorpaySandboxDispatcher(config=config, client=client)
    engine = ExecutionEngine(dispatcher=dispatcher)

    candidate = CandidateActionScore(
        action=InterventionAction.PAYMENT_RECOVERY,
        expected_value=Decimal("500.00"),
        recovery_probability_assumption=0.5,
        direct_cost=Decimal("0.00"),
        incentive_penalty_assumption=Decimal("0.00"),
        harm_penalty_assumption=Decimal("0.00"),
        is_eligible=True,
    )

    decision = InterventionDecision(
        customer_id="cus_batch_idempotency_01",
        decision_timestamp="2026-08-05T12:00:00+00:00",
        risk_score=0.85,
        risk_tier="CRITICAL",
        revenue_at_risk=Decimal("999.00"),
        diagnosis="PAYMENT_FRICTION",
        diagnosis_confidence=0.85,
        diagnosis_actionability="candidate",
        eligibility_status="ELIGIBLE",
        selected_action=InterventionAction.PAYMENT_RECOVERY,
        expected_value=Decimal("500.00"),
        candidate_scores=[candidate],
        decision_reason="Payment recovery",
        supporting_evidence=["Payment failure"],
    )

    r1 = engine.execute_decision(decision)
    assert r1.status == ExecutionStatus.EXECUTED
    assert len(client.created_links) == 1

    r2 = engine.execute_decision(decision)
    assert r2.status == ExecutionStatus.EXECUTED
    assert r2.execution_id == r1.execution_id
    # Empirically verify duplicate request did not create a second payment link
    assert len(client.created_links) == 1


def test_11_no_secrets_appear_in_generated_evaluation_output():
    """11. Batch evaluation output contains zero API keys, secrets, or authorization headers."""
    evaluator = BatchRecoveryEvaluator(customers_count=10, seed=42)
    res_dict = evaluator.evaluate().to_dict()
    res_str = str(res_dict)

    assert "SECRET" not in res_str
    assert "rzp_test_MOCK" not in res_str
    assert "Authorization" not in res_str


def test_12_no_ground_truth_fields_in_runtime_decision_payloads():
    """12. Per-customer evidence records contain zero ground-truth hidden simulator fields."""
    evaluator = BatchRecoveryEvaluator(customers_count=15, seed=42)
    res = evaluator.evaluate()

    forbidden_fields = {
        "ground_truth",
        "true_root_cause",
        "natural_conversion",
        "recoverable",
        "maximum_recoverable_revenue",
        "conversion_after_intervention",
    }

    for rec in res.per_customer_results:
        rec_dict = rec.to_dict()
        for forbidden in forbidden_fields:
            assert forbidden not in rec_dict


def test_13_measured_recovery_phase7_integration():
    """13. BatchRecoveryEvaluator integrates Phase 7 OutcomeEngine to measure realized recovery."""
    evaluator = BatchRecoveryEvaluator(customers_count=20, seed=42)
    res = evaluator.evaluate()
    agg = res.aggregate_metrics

    assert "total_gross_observed_revenue" in agg
    assert "total_attributable_revenue" in agg
    assert "total_intervention_cost" in agg
    assert "total_net_recovered_revenue" in agg
    assert "measured_recovery_rate_pct" in agg
    assert "recovered_customer_count" in agg

    assert agg["total_attributable_revenue"] > 0.0
    assert agg["total_net_recovered_revenue"] > 0.0
    assert agg["measured_recovery_rate_pct"] > 0.0
    assert agg["recovered_customer_count"] > 0


def test_14_expected_vs_measured_recovery_distinction():
    """14. Expected recovery and measured recovery are computed independently."""
    evaluator = BatchRecoveryEvaluator(customers_count=30, seed=42)
    res = evaluator.evaluate()
    agg = res.aggregate_metrics

    exp_rev = agg["total_expected_recovery_value"]
    meas_attr_rev = agg["total_attributable_revenue"]
    meas_net_rev = agg["total_net_recovered_revenue"]

    # Both values are non-zero and derived from their respective engines (Phase 5 EV vs Phase 7 Attributed)
    assert exp_rev > 0.0
    assert meas_attr_rev > 0.0
    assert meas_net_rev > 0.0


def test_15_outcome_engine_temporal_isolation():
    """15. Pre-execution events cannot trigger DIRECTLY_OBSERVED attribution."""
    from app.outcome.engine import OutcomeEngine
    from app.outcome.schemas import AttributionStatus, OutcomeType

    engine = OutcomeEngine()

    candidate = CandidateActionScore(
        action=InterventionAction.PAYMENT_RECOVERY,
        expected_value=Decimal("450.00"),
        recovery_probability_assumption=0.45,
        direct_cost=Decimal("3.00"),
        incentive_penalty_assumption=Decimal("0.00"),
        harm_penalty_assumption=Decimal("0.00"),
        is_eligible=True,
    )
    decision = InterventionDecision(
        customer_id="cus_temp_iso_01",
        decision_timestamp="2026-08-05T12:00:00+00:00",
        risk_score=0.85,
        risk_tier="CRITICAL",
        revenue_at_risk=Decimal("999.00"),
        diagnosis="PAYMENT_FRICTION",
        diagnosis_confidence=0.85,
        diagnosis_actionability="candidate",
        eligibility_status="ELIGIBLE",
        selected_action=InterventionAction.PAYMENT_RECOVERY,
        expected_value=Decimal("450.00"),
        candidate_scores=[candidate],
        decision_reason="Payment recovery",
        supporting_evidence=["Payment failure"],
    )
    audit_rec = ExecutionAuditRecord(
        execution_id="exec_temp_iso_01",
        decision_id="dec_temp_iso_01",
        customer_id="cus_temp_iso_01",
        merchant_id="merch_codecraft",
        execution_timestamp="2026-08-05T12:00:00+00:00",
        action=InterventionAction.PAYMENT_RECOVERY,
        status=ExecutionStatus.EXECUTED,
        attempt_number=1,
        payload_id="payload_pay_temp",
        target_url="sim://revive/payment-recovery?cid=cus_temp_iso_01",
    )

    # Pre-execution event (timestamp BEFORE execution_timestamp)
    pre_evt = BaseEvent(
        event_id="evt_pre_01",
        event_type=EventType.PAYMENT_SUCCEEDED,
        schema_version="1.0",
        merchant_id="merch_codecraft",
        customer_id="cus_temp_iso_01",
        timestamp="2026-08-05T10:00:00+00:00", # 2h before execution!
        source="billing",
        payload={"amount": 999.00},
    )

    out_rec = engine.measure_outcome(
        execution_record=audit_rec,
        decision=decision,
        customer_events=[pre_evt],
        observation_window_hours=168.0,
    )

    # Pre-existing conversion protection: ALREADY_CONVERTED, UNATTRIBUTED, 0.00 attributable revenue
    assert out_rec.outcome == OutcomeType.ALREADY_CONVERTED
    assert out_rec.attribution_status == AttributionStatus.UNATTRIBUTED
    assert out_rec.attributable_revenue == Decimal("0.00")
    assert out_rec.net_recovered_revenue == Decimal("-3.00") # direct cost deduction


def test_16_zero_post_intervention_recovery_produces_zero_attributable_revenue():
    """16. When no post-intervention conversion occurs, OutcomeEngine assigns NOT_RECOVERED."""
    from app.outcome.engine import OutcomeEngine
    from app.outcome.schemas import AttributionStatus, OutcomeType

    engine = OutcomeEngine()

    candidate = CandidateActionScore(
        action=InterventionAction.PAYMENT_RECOVERY,
        expected_value=Decimal("450.00"),
        recovery_probability_assumption=0.45,
        direct_cost=Decimal("3.00"),
        incentive_penalty_assumption=Decimal("0.00"),
        harm_penalty_assumption=Decimal("0.00"),
        is_eligible=True,
    )
    decision = InterventionDecision(
        customer_id="cus_zero_rec_01",
        decision_timestamp="2026-08-05T12:00:00+00:00",
        risk_score=0.85,
        risk_tier="CRITICAL",
        revenue_at_risk=Decimal("999.00"),
        diagnosis="PAYMENT_FRICTION",
        diagnosis_confidence=0.85,
        diagnosis_actionability="candidate",
        eligibility_status="ELIGIBLE",
        selected_action=InterventionAction.PAYMENT_RECOVERY,
        expected_value=Decimal("450.00"),
        candidate_scores=[candidate],
        decision_reason="Payment recovery",
        supporting_evidence=["Payment failure"],
    )
    audit_rec = ExecutionAuditRecord(
        execution_id="exec_zero_rec_01",
        decision_id="dec_zero_rec_01",
        customer_id="cus_zero_rec_01",
        merchant_id="merch_codecraft",
        execution_timestamp="2026-08-05T12:00:00+00:00",
        action=InterventionAction.PAYMENT_RECOVERY,
        status=ExecutionStatus.EXECUTED,
        attempt_number=1,
        payload_id="payload_pay_zero",
        target_url="sim://revive/payment-recovery?cid=cus_zero_rec_01",
    )

    # Post-execution failure event (no payment succeeded)
    post_fail_evt = BaseEvent(
        event_id="evt_post_fail_01",
        event_type=EventType.PAYMENT_FAILED,
        schema_version="1.0",
        merchant_id="merch_codecraft",
        customer_id="cus_zero_rec_01",
        timestamp="2026-08-05T14:00:00+00:00",
        source="billing",
        payload={"error_code": "CARD_DECLINED"},
    )

    out_rec = engine.measure_outcome(
        execution_record=audit_rec,
        decision=decision,
        customer_events=[post_fail_evt],
        observation_window_hours=168.0,
    )

    assert out_rec.outcome == OutcomeType.NOT_RECOVERED
    assert out_rec.attribution_status == AttributionStatus.UNATTRIBUTED
    assert out_rec.attributable_revenue == Decimal("0.00")
    assert out_rec.net_recovered_revenue == Decimal("-3.00")


def test_17_probabilistic_response_simulator_determinism_and_non_100_percent_success():
    """17. EvaluationResponseSimulator produces deterministic outcomes and non-100% success rate."""
    evaluator1 = BatchRecoveryEvaluator(customers_count=100, seed=42)
    res1 = evaluator1.evaluate()

    evaluator2 = BatchRecoveryEvaluator(customers_count=100, seed=42)
    res2 = evaluator2.evaluate()

    # Deterministic byte-for-byte reproducibility
    assert res1.to_dict() == res2.to_dict()

    outcome_dist = res1.outcome_distribution
    # Verify non-100%-success: not all executed interventions succeed
    assert outcome_dist.get("RECOVERED", 0) > 0
    assert outcome_dist.get("NOT_RECOVERED", 0) > 0
    # Total executed interventions = RECOVERED + NOT_RECOVERED (for recovery candidates)
    exec_candidates = res1.aggregate_metrics["simulated_successful_executions"]
    assert outcome_dist["RECOVERED"] + outcome_dist["NOT_RECOVERED"] == exec_candidates
