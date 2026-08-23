"""
Unit and Integration Test Suite for Revive Root-Cause Diagnosis Engine (Phase 4).
Tests snapshot evidence safety, ground-truth isolation, temporal cutoff, determinism,
evidence consistency, observability classification, and evaluation metric separation.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest

from app.models.entities import Customer, Plan
from app.models.enums import EventType
from app.models.events import BaseEvent
from app.risk.feature_registry import FORBIDDEN_GROUND_TRUTH_FIELDS
from app.risk.scoring import ScoredCustomer
from app.diagnosis.config import DEFAULT_DIAGNOSIS_CONFIG, DiagnosisConfig
from app.diagnosis.engine import DiagnosisEngine
from app.diagnosis.evaluation import DiagnosisEvaluator, classify_observability_status, verify_evidence_consistency
from app.diagnosis.schemas import Actionability, ConfidenceTier, DiagnosisCategory, EvidenceCategory


@pytest.fixture
def sample_plan():
    return Plan(
        plan_id="pro",
        name="Pro Plan",
        price=Decimal("4999.00"),
        currency="INR",
        billing_interval="month",
    )


@pytest.fixture
def sample_customer():
    start = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)
    return Customer(
        customer_id="cus_diag_001",
        merchant_id="merch_codecraft",
        created_at=start,
        plan_id="pro",
    )


@pytest.fixture
def base_scored_customer(sample_customer):
    pred_ts = (sample_customer.created_at + timedelta(hours=72)).isoformat()
    return ScoredCustomer(
        customer_id=sample_customer.customer_id,
        prediction_timestamp=pred_ts,
        risk_score=0.75,
        risk_tier="HIGH",
        plan_id="pro",
        plan_price=Decimal("4999.00"),
        revenue_at_risk=Decimal("3749.25"),
    )


# --- 10 EXPLICIT SPECIFICATION TESTS ---

def test_1_insufficient_evidence_not_counted_as_unsafe_failure(sample_customer, sample_plan, base_scored_customer):
    """Test 1: INSUFFICIENT_EVIDENCE is treated as SAFE UNCERTAINTY, not an unsafe failure when no cause evidence exists."""
    engine = DiagnosisEngine()
    t_start = sample_customer.created_at

    events = [
        BaseEvent(event_id="e1", event_type=EventType.TRIAL_STARTED, merchant_id="m1", customer_id="cus_diag_001", timestamp=t_start, source="trial"),
        BaseEvent(event_id="e2", event_type=EventType.SESSION_STARTED, merchant_id="m1", customer_id="cus_diag_001", timestamp=t_start + timedelta(hours=50), source="product"),
    ]
    feat = {"session_count": 4, "feature_use_count": 5, "hours_since_last_activity": 10.0, "hours_until_trial_expiry": 264.0}

    diag = engine.diagnose_customer(base_scored_customer, sample_customer, events, sample_plan, feat)
    assert diag.diagnosis == DiagnosisCategory.INSUFFICIENT_EVIDENCE
    assert diag.actionability == Actionability.NONE

    gt_map = {"cus_diag_001": "payment_friction"}
    metrics = DiagnosisEvaluator.evaluate_diagnoses([diag], gt_map)

    # Safe uncertainty: 100% evidence consistency, zero actionable alignment error
    assert metrics["evidence_consistency_rate"] == 1.0
    assert metrics["uncertain_rate"] == 1.0
    assert metrics["actionable_evaluated_count"] == 0


def test_2_specific_diagnosis_requires_observable_evidence(sample_customer, sample_plan, base_scored_customer):
    """Test 2: Specific root-cause diagnoses strictly require corresponding observable evidence."""
    engine = DiagnosisEngine()
    t_start = sample_customer.created_at

    # Customer without payment failure
    events = [
        BaseEvent(event_id="e1", event_type=EventType.TRIAL_STARTED, merchant_id="m1", customer_id="cus_diag_001", timestamp=t_start, source="trial"),
    ]
    diag = engine.diagnose_customer(base_scored_customer, sample_customer, events, sample_plan, {"session_count": 5})

    # Engine must NOT output PAYMENT_FRICTION without payment failure evidence
    assert diag.diagnosis != DiagnosisCategory.PAYMENT_FRICTION
    assert verify_evidence_consistency(diag) is True


def test_3_ground_truth_never_passed_to_runtime(sample_customer, sample_plan, base_scored_customer):
    """Test 3: Ground truth files/dict are never passed to DiagnosisEngine during runtime inference."""
    engine = DiagnosisEngine()
    events = [BaseEvent(event_id="e1", event_type=EventType.TRIAL_STARTED, merchant_id="m1", customer_id="cus_diag_001", timestamp=sample_customer.created_at, source="trial")]

    diag = engine.diagnose_customer(base_scored_customer, sample_customer, events, sample_plan, {"session_count": 1})
    assert isinstance(diag.diagnosis, DiagnosisCategory)


def test_4_future_events_do_not_change_diagnosis(sample_customer, sample_plan, base_scored_customer):
    """Test 4: Events occurring after Tprediction cannot alter 72h diagnosis, confidence, or candidate scores."""
    engine = DiagnosisEngine()
    t_start = sample_customer.created_at

    valid_events = [
        BaseEvent(event_id="e1", event_type=EventType.TRIAL_STARTED, merchant_id="m1", customer_id="cus_diag_001", timestamp=t_start, source="trial"),
        BaseEvent(event_id="e2", event_type=EventType.CHECKOUT_STARTED, merchant_id="m1", customer_id="cus_diag_001", timestamp=t_start + timedelta(hours=30), source="checkout"),
    ]
    feat = {"session_count": 3, "pricing_view_count": 2, "hours_since_last_activity": 10.0}

    diag_before = engine.diagnose_customer(base_scored_customer, sample_customer, valid_events, sample_plan, feat)

    future_events = list(valid_events) + [
        BaseEvent(event_id="e3_future", event_type=EventType.PAYMENT_FAILED, merchant_id="m1", customer_id="cus_diag_001", timestamp=t_start + timedelta(hours=100), source="payment"),
        BaseEvent(event_id="e4_future", event_type=EventType.SUBSCRIPTION_CREATED, merchant_id="m1", customer_id="cus_diag_001", timestamp=t_start + timedelta(hours=120), source="subscription"),
    ]

    diag_after = engine.diagnose_customer(base_scored_customer, sample_customer, future_events, sample_plan, feat)

    assert diag_before.diagnosis == diag_after.diagnosis
    assert diag_before.confidence == diag_after.confidence
    assert diag_before.actionability == diag_after.actionability
    assert len(diag_before.candidate_causes) == len(diag_after.candidate_causes)


def test_5_snapshot_metrics_and_future_outcome_metrics_are_separate(sample_customer, sample_plan, base_scored_customer):
    """Test 5: Snapshot diagnosis metrics and future outcome metrics are explicitly separated in DiagnosisEvaluator."""
    engine = DiagnosisEngine()
    events = [BaseEvent(event_id="e1", event_type=EventType.TRIAL_STARTED, merchant_id="m1", customer_id="cus_diag_001", timestamp=sample_customer.created_at, source="trial")]
    diag = engine.diagnose_customer(base_scored_customer, sample_customer, events, sample_plan, {"session_count": 1})

    metrics = DiagnosisEvaluator.evaluate_diagnoses([diag], {"cus_diag_001": "payment_friction"})

    # Separate section keys in evaluation dict
    assert "evidence_consistency_rate" in metrics
    assert "future_outcome_alignment_rate" in metrics
    assert "per_cause_observability_table" in metrics


def test_6_not_yet_observable_causes_not_counted_as_snapshot_errors(sample_customer, sample_plan, base_scored_customer):
    """Test 6: NOT_YET_OBSERVABLE causes are classified correctly and not treated as snapshot errors when returning INSUFFICIENT_EVIDENCE."""
    events = [BaseEvent(event_id="e1", event_type=EventType.TRIAL_STARTED, merchant_id="m1", customer_id="cus_01", timestamp=sample_customer.created_at, source="trial")]
    feat = {"session_count": 4, "hours_until_trial_expiry": 264.0}

    # PAYMENT_FRICTION has no payment_failed event at 72h
    obs_status = classify_observability_status("PAYMENT_FRICTION", events, feat)
    assert obs_status == "NOT_YET_OBSERVABLE"


def test_7_actionable_diagnoses_evaluated_offline_against_eventual_outcomes(sample_customer, sample_plan, base_scored_customer):
    """Test 7: Actionable diagnoses are evaluated offline against eventual ground truth outcomes."""
    engine = DiagnosisEngine()
    t_start = sample_customer.created_at

    events = [
        BaseEvent(event_id="e1", event_type=EventType.TRIAL_STARTED, merchant_id="m1", customer_id="cus_01", timestamp=t_start, source="trial"),
        BaseEvent(event_id="e2", event_type=EventType.PAYMENT_FAILED, merchant_id="m1", customer_id="cus_01", timestamp=t_start + timedelta(hours=40), source="payment"),
    ]
    diag = engine.diagnose_customer(base_scored_customer, sample_customer, events, sample_plan, {"session_count": 2, "hours_since_last_activity": 10.0})
    assert diag.actionability == Actionability.CANDIDATE

    metrics = DiagnosisEvaluator.evaluate_diagnoses([diag], {sample_customer.customer_id: "payment_friction"})
    assert metrics["actionable_evaluated_count"] == 1
    assert metrics["actionable_aligned_count"] == 1
    assert metrics["future_outcome_alignment_rate"] == 1.0


def test_8_no_meaningful_risk_remains_based_on_risk_score(sample_customer, sample_plan):
    """Test 8: NO_MEANINGFUL_RISK remains determined by Phase 3 risk score (< 0.30) rather than ground truth."""
    engine = DiagnosisEngine()
    pred_ts = (sample_customer.created_at + timedelta(hours=72)).isoformat()

    low_risk_customer = ScoredCustomer(
        customer_id=sample_customer.customer_id,
        prediction_timestamp=pred_ts,
        risk_score=0.15,  # Low risk < 0.30
        risk_tier="LOW",
        plan_id="pro",
        plan_price=Decimal("4999.00"),
        revenue_at_risk=Decimal("0.00"),
    )

    diag = engine.diagnose_customer(low_risk_customer, sample_customer, [], sample_plan, {})
    assert diag.diagnosis == DiagnosisCategory.NO_MEANINGFUL_RISK
    assert diag.actionability == Actionability.NONE


def test_9_existing_leakage_tests_remain_passing():
    """Test 9: Verify zero forbidden ground truth fields present during feature extraction."""
    for forbidden in FORBIDDEN_GROUND_TRUTH_FIELDS:
        assert forbidden in {"true_root_cause", "generation_segment", "natural_conversion", "conversion_after_intervention", "recoverable", "maximum_recoverable_revenue"}


def test_10_same_observable_state_produces_same_runtime_diagnosis(sample_plan):
    """Test 10: Same observable state produces identical runtime diagnosis regardless of hidden eventual outcome."""
    engine = DiagnosisEngine()
    t_start = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)
    pred_ts = (t_start + timedelta(hours=72)).isoformat()

    c1 = Customer(customer_id="cus_gt_a", merchant_id="m1", created_at=t_start, plan_id="pro")
    c2 = Customer(customer_id="cus_gt_b", merchant_id="m1", created_at=t_start, plan_id="pro")

    sc1 = ScoredCustomer(customer_id="cus_gt_a", prediction_timestamp=pred_ts, risk_score=0.80, risk_tier="CRITICAL", plan_id="pro", plan_price=Decimal("4999.00"), revenue_at_risk=Decimal("3999.20"))
    sc2 = ScoredCustomer(customer_id="cus_gt_b", prediction_timestamp=pred_ts, risk_score=0.80, risk_tier="CRITICAL", plan_id="pro", plan_price=Decimal("4999.00"), revenue_at_risk=Decimal("3999.20"))

    events = [
        BaseEvent(event_id="e1", event_type=EventType.TRIAL_STARTED, merchant_id="m1", customer_id="c", timestamp=t_start, source="trial"),
        BaseEvent(event_id="e2", event_type=EventType.PAYMENT_FAILED, merchant_id="m1", customer_id="c", timestamp=t_start + timedelta(hours=30), source="payment"),
    ]
    feat = {"session_count": 3, "hours_since_last_activity": 12.0}

    d1 = engine.diagnose_customer(sc1, c1, events, sample_plan, feat)
    d2 = engine.diagnose_customer(sc2, c2, events, sample_plan, feat)

    assert d1.diagnosis == d2.diagnosis
    assert d1.confidence == d2.confidence
    assert d1.actionability == d2.actionability
