"""
Unit tests for Revive domain models, events, entities, and enums.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest
from pydantic import ValidationError

from app.models.entities import (
    Customer,
    Intervention,
    Merchant,
    Payment,
    Plan,
    Subscription,
    Trial,
)
from app.models.enums import (
    EventType,
    InterventionStatus,
    InterventionType,
    PaymentStatus,
    PolicyDecision,
    RecoveryStatus,
    SubscriptionStatus,
    TrialStatus,
)
from app.models.events import BaseEvent


# --- EVENT TESTS ---

def test_valid_base_event_is_accepted():
    now = datetime.now(timezone.utc)
    event = BaseEvent(
        event_id="EVT_001",
        event_type=EventType.CHECKOUT_ABANDONED,
        merchant_id="MERCH_01",
        customer_id="CUS_10482",
        timestamp=now,
        source="checkout",
        payload={"cart_value": 4999, "items": ["pro_plan"]},
    )
    assert event.event_id == "EVT_001"
    assert event.event_type == EventType.CHECKOUT_ABANDONED
    assert event.schema_version == "1.0"
    assert event.merchant_id == "MERCH_01"
    assert event.customer_id == "CUS_10482"
    assert event.timestamp == now
    assert event.source == "checkout"
    assert event.payload == {"cart_value": 4999, "items": ["pro_plan"]}


def test_event_type_is_validated():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        BaseEvent(
            event_id="EVT_002",
            event_type="invalid_event_type",  # type: ignore
            merchant_id="MERCH_01",
            customer_id="CUS_10482",
            timestamp=now,
            source="checkout",
        )


def test_empty_event_id_is_rejected():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        BaseEvent(
            event_id="   ",
            event_type=EventType.TRIAL_STARTED,
            merchant_id="MERCH_01",
            customer_id="CUS_10482",
            timestamp=now,
            source="trial",
        )


def test_empty_merchant_id_is_rejected():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        BaseEvent(
            event_id="EVT_003",
            event_type=EventType.TRIAL_STARTED,
            merchant_id="",
            customer_id="CUS_10482",
            timestamp=now,
            source="trial",
        )


def test_empty_customer_id_is_rejected():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        BaseEvent(
            event_id="EVT_004",
            event_type=EventType.TRIAL_STARTED,
            merchant_id="MERCH_01",
            customer_id="",
            timestamp=now,
            source="trial",
        )


def test_empty_source_is_rejected():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        BaseEvent(
            event_id="EVT_005",
            event_type=EventType.TRIAL_STARTED,
            merchant_id="MERCH_01",
            customer_id="CUS_10482",
            timestamp=now,
            source="",
        )


def test_invalid_timestamp_is_rejected():
    # Naive timestamp should be rejected
    naive_dt = datetime(2026, 8, 23, 10, 0, 0)
    with pytest.raises(ValidationError):
        BaseEvent(
            event_id="EVT_006",
            event_type=EventType.TRIAL_STARTED,
            merchant_id="MERCH_01",
            customer_id="CUS_10482",
            timestamp=naive_dt,
            source="trial",
        )

    # Invalid timestamp string should be rejected
    with pytest.raises(ValidationError):
        BaseEvent(
            event_id="EVT_007",
            event_type=EventType.TRIAL_STARTED,
            merchant_id="MERCH_01",
            customer_id="CUS_10482",
            timestamp="not-a-date",  # type: ignore
            source="trial",
        )


def test_payload_must_be_a_dictionary():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        BaseEvent(
            event_id="EVT_008",
            event_type=EventType.TRIAL_STARTED,
            merchant_id="MERCH_01",
            customer_id="CUS_10482",
            timestamp=now,
            source="trial",
            payload=["item1", "item2"],  # type: ignore
        )


# --- ENTITY TESTS ---

def test_valid_merchant():
    merchant = Merchant(
        merchant_id="MERCH_01",
        name="Acme SaaS",
        currency="INR",
        timezone="Asia/Kolkata",
    )
    assert merchant.merchant_id == "MERCH_01"
    assert merchant.name == "Acme SaaS"
    assert merchant.currency == "INR"
    assert merchant.timezone == "Asia/Kolkata"


def test_valid_customer():
    now = datetime.now(timezone.utc)
    customer = Customer(
        customer_id="CUS_10482",
        merchant_id="MERCH_01",
        created_at=now,
        plan_id="PLAN_PRO",
    )
    assert customer.customer_id == "CUS_10482"
    assert customer.merchant_id == "MERCH_01"
    assert customer.created_at == now
    assert customer.plan_id == "PLAN_PRO"


def test_valid_plan():
    plan = Plan(
        plan_id="PLAN_PRO",
        name="Pro Plan",
        price=Decimal("4999.00"),
        currency="INR",
        billing_interval="month",
    )
    assert plan.plan_id == "PLAN_PRO"
    assert plan.price == Decimal("4999.00")
    assert isinstance(plan.price, Decimal)


def test_negative_plan_price_is_rejected():
    with pytest.raises(ValidationError):
        Plan(
            plan_id="PLAN_PRO",
            name="Pro Plan",
            price=Decimal("-10.00"),
            currency="INR",
            billing_interval="month",
        )


def test_valid_trial():
    start = datetime.now(timezone.utc)
    end = start + timedelta(days=14)
    trial = Trial(
        trial_id="TRL_001",
        customer_id="CUS_10482",
        start_at=start,
        end_at=end,
        status=TrialStatus.ACTIVE,
    )
    assert trial.trial_id == "TRL_001"
    assert trial.status == TrialStatus.ACTIVE
    assert trial.end_at > trial.start_at


def test_trial_end_must_be_after_start():
    start = datetime.now(timezone.utc)
    end = start - timedelta(hours=1)
    with pytest.raises(ValidationError):
        Trial(
            trial_id="TRL_002",
            customer_id="CUS_10482",
            start_at=start,
            end_at=end,
            status=TrialStatus.ACTIVE,
        )


def test_valid_subscription():
    now = datetime.now(timezone.utc)
    sub = Subscription(
        subscription_id="SUB_001",
        customer_id="CUS_10482",
        plan_id="PLAN_PRO",
        status=SubscriptionStatus.ACTIVE,
        amount=Decimal("4999.00"),
        created_at=now,
    )
    assert sub.subscription_id == "SUB_001"
    assert sub.amount == Decimal("4999.00")
    assert isinstance(sub.amount, Decimal)


def test_negative_subscription_amount_is_rejected():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        Subscription(
            subscription_id="SUB_002",
            customer_id="CUS_10482",
            plan_id="PLAN_PRO",
            status=SubscriptionStatus.ACTIVE,
            amount=Decimal("-4999.00"),
            created_at=now,
        )


def test_valid_payment():
    now = datetime.now(timezone.utc)
    payment = Payment(
        payment_id="PAY_001",
        customer_id="CUS_10482",
        amount=Decimal("4999.00"),
        status=PaymentStatus.SUCCEEDED,
        method="card",
        created_at=now,
    )
    assert payment.payment_id == "PAY_001"
    assert payment.amount == Decimal("4999.00")
    assert payment.status == PaymentStatus.SUCCEEDED
    assert payment.failure_reason is None


def test_negative_payment_amount_is_rejected():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        Payment(
            payment_id="PAY_002",
            customer_id="CUS_10482",
            amount=Decimal("-100.00"),
            status=PaymentStatus.FAILED,
            method="card",
            created_at=now,
        )


def test_valid_intervention():
    now = datetime.now(timezone.utc)
    intervention = Intervention(
        intervention_id="INT_001",
        customer_id="CUS_10482",
        action=InterventionType.RESUME_CHECKOUT,
        status=InterventionStatus.EXECUTED,
        expected_value=Decimal("2140.00"),
        actual_revenue=Decimal("4999.00"),
        created_at=now,
    )
    assert intervention.intervention_id == "INT_001"
    assert intervention.action == InterventionType.RESUME_CHECKOUT
    assert intervention.expected_value == Decimal("2140.00")
    assert intervention.actual_revenue == Decimal("4999.00")


def test_negative_expected_value_is_rejected():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        Intervention(
            intervention_id="INT_002",
            customer_id="CUS_10482",
            action=InterventionType.RESUME_CHECKOUT,
            status=InterventionStatus.PROPOSED,
            expected_value=Decimal("-1.00"),
            created_at=now,
        )


def test_negative_actual_revenue_is_rejected():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        Intervention(
            intervention_id="INT_003",
            customer_id="CUS_10482",
            action=InterventionType.RESUME_CHECKOUT,
            status=InterventionStatus.SUCCEEDED,
            expected_value=Decimal("100.00"),
            actual_revenue=Decimal("-50.00"),
            created_at=now,
        )


# --- ENUM TESTS ---

def test_invalid_enum_values_are_rejected():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        Payment(
            payment_id="PAY_003",
            customer_id="CUS_10482",
            amount=Decimal("100.00"),
            status="invalid_status",  # type: ignore
            method="card",
            created_at=now,
        )

    with pytest.raises(ValidationError):
        Trial(
            trial_id="TRL_003",
            customer_id="CUS_10482",
            start_at=now,
            end_at=now + timedelta(days=7),
            status="unknown_trial_status",  # type: ignore
        )

    with pytest.raises(ValidationError):
        Subscription(
            subscription_id="SUB_003",
            customer_id="CUS_10482",
            plan_id="PLAN_PRO",
            status="bad_status",  # type: ignore
            amount=Decimal("100.00"),
            created_at=now,
        )

    with pytest.raises(ValidationError):
        Intervention(
            intervention_id="INT_004",
            customer_id="CUS_10482",
            action="invalid_action",  # type: ignore
            status=InterventionStatus.PROPOSED,
            expected_value=Decimal("100.00"),
            created_at=now,
        )
