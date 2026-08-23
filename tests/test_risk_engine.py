"""
Unit and integration test suite for Revive Revenue Risk Engine (Phase 3).
Tests snapshot rule, feature extraction, division safety, leakage prevention,
probabilistic model scoring, revenue-at-risk calculation, risk tiers, and reproducibility.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import os
import tempfile
import pytest

from app.models.entities import Customer, Plan
from app.models.enums import EventType
from app.models.events import BaseEvent
from app.risk.feature_registry import FEATURE_REGISTRY_VERSION, FORBIDDEN_GROUND_TRUTH_FIELDS, get_inference_feature_names
from app.risk.features import CustomerFeatureExtractor, FeatureDatasetBuilder, safe_divide
from app.risk.model import ReviveRiskModel
from app.risk.scoring import RiskScorer, ScoredCustomer, determine_risk_tier


# --- FIXTURES ---

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
        customer_id="cus_test_001",
        merchant_id="merch_codecraft",
        created_at=start,
        plan_id="pro",
    )


# --- FEATURE EXTRACTION TESTS ---

def test_feature_extraction_session_count(sample_customer, sample_plan):
    extractor = CustomerFeatureExtractor(snapshot_hours=72.0)
    t_start = sample_customer.created_at

    events = [
        BaseEvent(
            event_id="evt_01",
            event_type=EventType.TRIAL_STARTED,
            merchant_id="merch_codecraft",
            customer_id="cus_test_001",
            timestamp=t_start,
            source="trial",
        ),
        BaseEvent(
            event_id="evt_02",
            event_type=EventType.SESSION_STARTED,
            merchant_id="merch_codecraft",
            customer_id="cus_test_001",
            timestamp=t_start + timedelta(hours=10),
            source="product",
        ),
        BaseEvent(
            event_id="evt_03",
            event_type=EventType.SESSION_STARTED,
            merchant_id="merch_codecraft",
            customer_id="cus_test_001",
            timestamp=t_start + timedelta(hours=20),
            source="product",
        ),
    ]

    features, status = extractor.extract_features(sample_customer, events, sample_plan)
    assert status == "OK"
    assert features["session_count"] == 2


def test_feature_extraction_feature_use_count(sample_customer, sample_plan):
    extractor = CustomerFeatureExtractor(snapshot_hours=72.0)
    t_start = sample_customer.created_at

    events = [
        BaseEvent(
            event_id="evt_01",
            event_type=EventType.TRIAL_STARTED,
            merchant_id="merch_codecraft",
            customer_id="cus_test_001",
            timestamp=t_start,
            source="trial",
        ),
        BaseEvent(
            event_id="evt_02",
            event_type=EventType.FEATURE_USED,
            merchant_id="merch_codecraft",
            customer_id="cus_test_001",
            timestamp=t_start + timedelta(hours=5),
            source="product",
        ),
        BaseEvent(
            event_id="evt_03",
            event_type=EventType.FEATURE_USED,
            merchant_id="merch_codecraft",
            customer_id="cus_test_001",
            timestamp=t_start + timedelta(hours=15),
            source="product",
        ),
    ]

    features, status = extractor.extract_features(sample_customer, events, sample_plan)
    assert status == "OK"
    assert features["feature_use_count"] == 2


def test_feature_extraction_pricing_view_count(sample_customer, sample_plan):
    extractor = CustomerFeatureExtractor(snapshot_hours=72.0)
    t_start = sample_customer.created_at

    events = [
        BaseEvent(
            event_id="evt_01",
            event_type=EventType.TRIAL_STARTED,
            merchant_id="merch_codecraft",
            customer_id="cus_test_001",
            timestamp=t_start,
            source="trial",
        ),
        BaseEvent(
            event_id="evt_02",
            event_type=EventType.PRICING_VIEWED,
            merchant_id="merch_codecraft",
            customer_id="cus_test_001",
            timestamp=t_start + timedelta(hours=12),
            source="product",
        ),
    ]

    features, status = extractor.extract_features(sample_customer, events, sample_plan)
    assert status == "OK"
    assert features["pricing_view_count"] == 1


def test_feature_extraction_checkout_state(sample_customer, sample_plan):
    extractor = CustomerFeatureExtractor(snapshot_hours=72.0)
    t_start = sample_customer.created_at

    events = [
        BaseEvent(
            event_id="evt_01",
            event_type=EventType.TRIAL_STARTED,
            merchant_id="merch_codecraft",
            customer_id="cus_test_001",
            timestamp=t_start,
            source="trial",
        ),
        BaseEvent(
            event_id="evt_02",
            event_type=EventType.CHECKOUT_STARTED,
            merchant_id="merch_codecraft",
            customer_id="cus_test_001",
            timestamp=t_start + timedelta(hours=30),
            source="checkout",
        ),
        BaseEvent(
            event_id="evt_03",
            event_type=EventType.PAYMENT_METHOD_ADDED,
            merchant_id="merch_codecraft",
            customer_id="cus_test_001",
            timestamp=t_start + timedelta(hours=35),
            source="payment",
        ),
    ]

    features, status = extractor.extract_features(sample_customer, events, sample_plan)
    assert status == "OK"
    assert features["checkout_started"] == 1
    assert features["checkout_completed"] == 0
    assert features["payment_method_added"] == 1


def test_feature_extraction_payment_failure_count(sample_customer, sample_plan):
    extractor = CustomerFeatureExtractor(snapshot_hours=72.0)
    t_start = sample_customer.created_at

    events = [
        BaseEvent(
            event_id="evt_01",
            event_type=EventType.TRIAL_STARTED,
            merchant_id="merch_codecraft",
            customer_id="cus_test_001",
            timestamp=t_start,
            source="trial",
        ),
        BaseEvent(
            event_id="evt_02",
            event_type=EventType.PAYMENT_ATTEMPTED,
            merchant_id="merch_codecraft",
            customer_id="cus_test_001",
            timestamp=t_start + timedelta(hours=40),
            source="payment",
        ),
        BaseEvent(
            event_id="evt_03",
            event_type=EventType.PAYMENT_FAILED,
            merchant_id="merch_codecraft",
            customer_id="cus_test_001",
            timestamp=t_start + timedelta(hours=40, seconds=5),
            source="payment",
            payload={"failure_reason": "bank_declined"},
        ),
    ]

    features, status = extractor.extract_features(sample_customer, events, sample_plan)
    assert status == "OK"
    assert features["payment_attempt_count"] == 1
    assert features["payment_failure_count"] == 1
    assert features["has_payment_failure"] == 1


def test_feature_extraction_recency(sample_customer, sample_plan):
    extractor = CustomerFeatureExtractor(snapshot_hours=72.0)
    t_start = sample_customer.created_at

    # Prediction snapshot will be t_start + 72h
    events = [
        BaseEvent(
            event_id="evt_01",
            event_type=EventType.TRIAL_STARTED,
            merchant_id="merch_codecraft",
            customer_id="cus_test_001",
            timestamp=t_start,
            source="trial",
        ),
        BaseEvent(
            event_id="evt_02",
            event_type=EventType.SESSION_STARTED,
            merchant_id="merch_codecraft",
            customer_id="cus_test_001",
            timestamp=t_start + timedelta(hours=60),  # 12h before snapshot
            source="product",
        ),
    ]

    features, status = extractor.extract_features(sample_customer, events, sample_plan)
    assert status == "OK"
    assert pytest.approx(features["hours_since_last_session"], 0.01) == 12.0
    assert pytest.approx(features["hours_since_last_activity"], 0.01) == 12.0


def test_feature_extraction_trial_remaining_time(sample_customer, sample_plan):
    extractor = CustomerFeatureExtractor(snapshot_hours=72.0)
    t_start = sample_customer.created_at

    events = [
        BaseEvent(
            event_id="evt_01",
            event_type=EventType.TRIAL_STARTED,
            merchant_id="merch_codecraft",
            customer_id="cus_test_001",
            timestamp=t_start,
            source="trial",
        ),
    ]

    features, status = extractor.extract_features(sample_customer, events, sample_plan)
    assert status == "OK"
    assert pytest.approx(features["trial_age_hours"], 0.01) == 72.0
    # Trial duration is 14 days (336 hours). Remaining = 336 - 72 = 264 hours
    assert pytest.approx(features["hours_until_trial_expiry"], 0.01) == 264.0
    assert features["trial_expiring_soon"] == 0


def test_feature_extraction_plan_price(sample_customer, sample_plan):
    extractor = CustomerFeatureExtractor(snapshot_hours=72.0)
    t_start = sample_customer.created_at

    events = [
        BaseEvent(
            event_id="evt_01",
            event_type=EventType.TRIAL_STARTED,
            merchant_id="merch_codecraft",
            customer_id="cus_test_001",
            timestamp=t_start,
            source="trial",
        ),
    ]

    features, status = extractor.extract_features(sample_customer, events, sample_plan)
    assert status == "OK"
    assert features["plan_id"] == "pro"
    assert features["plan_price"] == 4999.00


# --- SNAPSHOT TESTS ---

def test_snapshot_trial_start_plus_72_hours(sample_customer):
    extractor = CustomerFeatureExtractor(snapshot_hours=72.0)
    t_start = sample_customer.created_at
    t_end = t_start + timedelta(days=14)

    pred_ts = extractor.compute_prediction_timestamp(t_start, t_end)
    assert pred_ts == t_start + timedelta(hours=72)


def test_snapshot_capped_at_trial_end(sample_customer):
    extractor = CustomerFeatureExtractor(snapshot_hours=72.0)
    t_start = sample_customer.created_at
    t_end = t_start + timedelta(hours=48)  # Short trial ending in 48h

    pred_ts = extractor.compute_prediction_timestamp(t_start, t_end)
    assert pred_ts == t_end


# --- LEAKAGE TESTS ---

def test_leakage_forbidden_ground_truth_fields_excluded(sample_customer, sample_plan):
    extractor = CustomerFeatureExtractor(snapshot_hours=72.0)
    t_start = sample_customer.created_at

    events = [
        BaseEvent(
            event_id="evt_01",
            event_type=EventType.TRIAL_STARTED,
            merchant_id="merch_codecraft",
            customer_id="cus_test_001",
            timestamp=t_start,
            source="trial",
        ),
    ]

    features, status = extractor.extract_features(sample_customer, events, sample_plan)
    assert status == "OK"

    # Verify no forbidden field is present in the feature dictionary
    for forbidden in FORBIDDEN_GROUND_TRUTH_FIELDS:
        assert forbidden not in features


def test_leakage_future_events_excluded(sample_customer, sample_plan):
    extractor = CustomerFeatureExtractor(snapshot_hours=72.0)
    t_start = sample_customer.created_at

    events = [
        BaseEvent(
            event_id="evt_01",
            event_type=EventType.TRIAL_STARTED,
            merchant_id="merch_codecraft",
            customer_id="cus_test_001",
            timestamp=t_start,
            source="trial",
        ),
        # Pre-snapshot event (at t_start + 10h)
        BaseEvent(
            event_id="evt_02",
            event_type=EventType.SESSION_STARTED,
            merchant_id="merch_codecraft",
            customer_id="cus_test_001",
            timestamp=t_start + timedelta(hours=10),
            source="product",
        ),
        # FUTURE EVENT (at t_start + 100h, which is after 72h snapshot!)
        BaseEvent(
            event_id="evt_03_future",
            event_type=EventType.SESSION_STARTED,
            merchant_id="merch_codecraft",
            customer_id="cus_test_001",
            timestamp=t_start + timedelta(hours=100),
            source="product",
        ),
        BaseEvent(
            event_id="evt_04_future_checkout",
            event_type=EventType.CHECKOUT_STARTED,
            merchant_id="merch_codecraft",
            customer_id="cus_test_001",
            timestamp=t_start + timedelta(hours=120),
            source="checkout",
        ),
    ]

    features, status = extractor.extract_features(sample_customer, events, sample_plan)
    assert status == "OK"

    # Must only count the 1 session before 72h snapshot
    assert features["session_count"] == 1
    # Future checkout_started MUST be excluded
    assert features["checkout_started"] == 0


# --- RATIO DIVISION SAFETY TESTS ---

def test_ratios_zero_denominators_no_nan_no_inf():
    assert safe_divide(10.0, 0.0) == 0.0
    assert safe_divide(0.0, 0.0) == 0.0
    assert safe_divide(5.0, float("nan")) == 0.0
    assert safe_divide(float("inf"), 2.0) == 0.0


# --- MODEL & SCORING TESTS ---

def test_model_output_risk_score_bounds(sample_customer, sample_plan):
    extractor = CustomerFeatureExtractor(snapshot_hours=72.0)
    t_start = sample_customer.created_at

    events = [
        BaseEvent(
            event_id="evt_01",
            event_type=EventType.TRIAL_STARTED,
            merchant_id="merch_codecraft",
            customer_id="cus_test_001",
            timestamp=t_start,
            source="trial",
        ),
    ]

    feat, _ = extractor.extract_features(sample_customer, events, sample_plan)

    # Train dummy model
    model = ReviveRiskModel(model_type="logistic_regression", seed=42)
    model.fit([feat, feat], [0, 1])

    scorer = RiskScorer(model)
    scored_cus = scorer.score_customer(feat)

    assert 0.0 <= scored_cus.risk_score <= 1.0


def test_revenue_at_risk_calculation():
    # plan_price = 4999.00, risk_score = 0.80 -> revenue_at_risk = 3999.20
    price = Decimal("4999.00")
    score = 0.80
    rev_raw = price * Decimal(str(round(score, 6)))
    assert float(rev_raw) == 3999.20


def test_risk_tiers_thresholds():
    assert determine_risk_tier(0.10) == "LOW"
    assert determine_risk_tier(0.29) == "LOW"
    assert determine_risk_tier(0.30) == "MEDIUM"
    assert determine_risk_tier(0.59) == "MEDIUM"
    assert determine_risk_tier(0.60) == "HIGH"
    assert determine_risk_tier(0.79) == "HIGH"
    assert determine_risk_tier(0.80) == "CRITICAL"
    assert determine_risk_tier(0.99) == "CRITICAL"


def test_reproducibility_same_seed(sample_customer, sample_plan):
    extractor = CustomerFeatureExtractor(snapshot_hours=72.0)
    t_start = sample_customer.created_at

    events = [
        BaseEvent(
            event_id="evt_01",
            event_type=EventType.TRIAL_STARTED,
            merchant_id="merch_codecraft",
            customer_id="cus_test_001",
            timestamp=t_start,
            source="trial",
        ),
    ]

    feat, _ = extractor.extract_features(sample_customer, events, sample_plan)

    m1 = ReviveRiskModel(model_type="logistic_regression", seed=42)
    m1.fit([feat, feat], [0, 1])
    score1 = m1.predict_proba([feat])[0]

    m2 = ReviveRiskModel(model_type="logistic_regression", seed=42)
    m2.fit([feat, feat], [0, 1])
    score2 = m2.predict_proba([feat])[0]

    assert score1 == score2


def test_inference_feature_construction_without_ground_truth(sample_customer, sample_plan):
    """Verify that runtime feature extraction depends ONLY on observable files and works without ground truth."""
    builder = FeatureDatasetBuilder(snapshot_hours=72.0)

    with tempfile.TemporaryDirectory() as tmp_dir:
        cust_file = os.path.join(tmp_dir, "customers.jsonl")
        plans_file = os.path.join(tmp_dir, "plans.jsonl")
        events_file = os.path.join(tmp_dir, "events.jsonl")

        with open(cust_file, "w", encoding="utf-8") as f:
            f.write(sample_customer.model_dump_json() + "\n")

        with open(plans_file, "w", encoding="utf-8") as f:
            f.write(sample_plan.model_dump_json() + "\n")

        with open(events_file, "w", encoding="utf-8") as f:
            evt = BaseEvent(
                event_id="evt_01",
                event_type=EventType.TRIAL_STARTED,
                merchant_id="merch_codecraft",
                customer_id="cus_test_001",
                timestamp=sample_customer.created_at,
                source="trial",
            )
            f.write(evt.model_dump_json() + "\n")

        # Call runtime build_observable_features without any ground_truth file parameter
        features = builder.build_observable_features(
            customers_file=cust_file,
            plans_file=plans_file,
            events_file=events_file,
        )

        assert len(features) == 1
        assert features[0]["customer_id"] == "cus_test_001"
        for forbidden in FORBIDDEN_GROUND_TRUTH_FIELDS:
            assert forbidden not in features[0]


def test_model_artifact_feature_registry_versioning(sample_customer, sample_plan):
    """Verify that model artifact includes feature_registry_version and load restores it."""
    extractor = CustomerFeatureExtractor(snapshot_hours=72.0)
    t_start = sample_customer.created_at
    events = [
        BaseEvent(
            event_id="evt_01",
            event_type=EventType.TRIAL_STARTED,
            merchant_id="merch_codecraft",
            customer_id="cus_test_001",
            timestamp=t_start,
            source="trial",
        ),
    ]

    feat, _ = extractor.extract_features(sample_customer, events, sample_plan)

    model = ReviveRiskModel(model_type="logistic_regression", seed=42)
    model.fit([feat, feat], [0, 1])

    with tempfile.TemporaryDirectory() as tmp_dir:
        model_path = os.path.join(tmp_dir, "test_model.joblib")
        model.save(model_path)

        loaded_model = ReviveRiskModel.load(model_path)
        assert hasattr(loaded_model, "feature_registry_version")
        assert loaded_model.feature_registry_version == FEATURE_REGISTRY_VERSION
        assert loaded_model.feature_registry_version == "1.0.0"
