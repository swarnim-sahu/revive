"""
Generates complete customer entities, trials, payments, subscriptions, and observable event streams.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import random
from typing import List, Optional, Tuple

from app.models.entities import Customer, Payment, Plan, Subscription, Trial
from app.models.enums import (
    EventType,
    PaymentStatus,
    SubscriptionStatus,
    TrialStatus,
)
from app.models.events import BaseEvent
from app.simulation.behaviour import CustomerBehaviour


def generate_customer_journey(
    customer_id: str,
    merchant_id: str,
    plan: Plan,
    behaviour: CustomerBehaviour,
    rng: random.Random,
) -> Tuple[Customer, Trial, List[BaseEvent], Optional[Payment], Optional[Subscription]]:
    """
    Construct a complete, chronologically consistent customer journey dataset.
    Returns (Customer, Trial, list of BaseEvent, Optional[Payment], Optional[Subscription]).
    """
    events: List[BaseEvent] = []
    event_seq = 1

    # Base start timestamp (seeded)
    base_offset_sec = rng.randint(0, 7 * 86400)
    t_start = datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc) + timedelta(seconds=base_offset_sec)

    # 1. Customer
    customer = Customer(
        customer_id=customer_id,
        merchant_id=merchant_id,
        created_at=t_start,
        plan_id=plan.plan_id,
    )

    def _next_evt(evt_type: EventType, ts: datetime, source: str, payload: dict) -> BaseEvent:
        nonlocal event_seq
        evt = BaseEvent(
            event_id=f"evt_{customer_id}_{event_seq:04d}",
            event_type=evt_type,
            schema_version="1.0",
            merchant_id=merchant_id,
            customer_id=customer_id,
            timestamp=ts,
            source=source,
            payload=payload,
        )
        event_seq += 1
        return evt

    # Event 1: customer_created
    events.append(_next_evt(EventType.CUSTOMER_CREATED, t_start, "customer", {"plan_id": plan.plan_id}))

    # 2. Trial
    trial_start = t_start + timedelta(seconds=1)
    trial_end = trial_start + timedelta(days=14)
    t_curr = trial_start

    # Event 2: trial_started
    events.append(_next_evt(
        EventType.TRIAL_STARTED,
        t_curr,
        "trial",
        {"trial_id": f"trl_{customer_id}", "duration_days": 14},
    ))

    # 3. Behavioural events (sessions, feature usage, pricing views)
    total_session_seconds = int(13.5 * 86400)
    session_times = sorted([
        t_curr + timedelta(seconds=rng.randint(60, total_session_seconds))
        for _ in range(behaviour.sessions)
    ])

    features_per_session = behaviour.feature_uses // max(1, behaviour.sessions)
    pricing_per_session = behaviour.pricing_views // max(1, behaviour.sessions)

    for i, s_time in enumerate(session_times):
        sess_id = f"sess_{customer_id}_{i+1:03d}"
        events.append(_next_evt(EventType.SESSION_STARTED, s_time, "product", {"session_id": sess_id}))

        # Feature uses
        for f in range(features_per_session):
            f_time = s_time + timedelta(seconds=rng.randint(1, 300))
            events.append(_next_evt(
                EventType.FEATURE_USED,
                f_time,
                "product",
                {"session_id": sess_id, "feature_name": f"feature_{rng.randint(1, 10)}"},
            ))

        # Pricing views
        for p in range(pricing_per_session):
            p_time = s_time + timedelta(seconds=rng.randint(1, 300))
            events.append(_next_evt(
                EventType.PRICING_VIEWED,
                p_time,
                "product",
                {"session_id": sess_id, "plan_viewed": plan.plan_id},
            ))

        # General activity
        act_time = s_time + timedelta(seconds=350)
        events.append(_next_evt(
            EventType.PRODUCT_ACTIVITY,
            act_time,
            "product",
            {"session_id": sess_id, "action": "dashboard_view"},
        ))

    # Determine last activity time
    t_last = session_times[-1] if session_times else (t_curr + timedelta(hours=2))

    # 4. Checkout & Payment events
    payment_obj: Optional[Payment] = None
    subscription_obj: Optional[Subscription] = None

    if behaviour.checkout_initiated:
        t_checkout = t_last + timedelta(minutes=rng.randint(10, 60))
        events.append(_next_evt(
            EventType.CHECKOUT_STARTED,
            t_checkout,
            "checkout",
            {"plan_id": plan.plan_id, "amount": str(plan.price)},
        ))
        t_curr = t_checkout

        if behaviour.payment_method_added:
            t_pm = t_curr + timedelta(minutes=rng.randint(1, 10))
            events.append(_next_evt(
                EventType.PAYMENT_METHOD_ADDED,
                t_pm,
                "payment",
                {"method": "card"},
            ))
            t_curr = t_pm

        if behaviour.payment_attempted:
            t_pay_att = t_curr + timedelta(minutes=rng.randint(1, 5))
            pay_id = f"pay_{customer_id}"
            events.append(_next_evt(
                EventType.PAYMENT_ATTEMPTED,
                t_pay_att,
                "payment",
                {"payment_id": pay_id, "amount": str(plan.price), "method": "card"},
            ))

            if behaviour.payment_failed:
                t_pay_fail = t_pay_att + timedelta(seconds=2)
                reason = behaviour.failure_reason or "bank_declined"
                events.append(_next_evt(
                    EventType.PAYMENT_FAILED,
                    t_pay_fail,
                    "payment",
                    {"payment_id": pay_id, "failure_reason": reason},
                ))
                payment_obj = Payment(
                    payment_id=pay_id,
                    customer_id=customer_id,
                    amount=plan.price,
                    status=PaymentStatus.FAILED,
                    method="card",
                    failure_reason=reason,
                    created_at=t_pay_fail,
                )
                t_curr = t_pay_fail

            elif behaviour.payment_succeeded:
                t_pay_succ = t_pay_att + timedelta(seconds=2)
                events.append(_next_evt(
                    EventType.PAYMENT_SUCCEEDED,
                    t_pay_succ,
                    "payment",
                    {"payment_id": pay_id, "amount": str(plan.price)},
                ))
                payment_obj = Payment(
                    payment_id=pay_id,
                    customer_id=customer_id,
                    amount=plan.price,
                    status=PaymentStatus.SUCCEEDED,
                    method="card",
                    failure_reason=None,
                    created_at=t_pay_succ,
                )

                t_chk_comp = t_pay_succ + timedelta(seconds=3)
                events.append(_next_evt(
                    EventType.CHECKOUT_COMPLETED,
                    t_chk_comp,
                    "checkout",
                    {"plan_id": plan.plan_id},
                ))

                t_sub_create = t_chk_comp + timedelta(seconds=5)
                sub_id = f"sub_{customer_id}"
                events.append(_next_evt(
                    EventType.SUBSCRIPTION_CREATED,
                    t_sub_create,
                    "subscription",
                    {"subscription_id": sub_id, "plan_id": plan.plan_id, "amount": str(plan.price)},
                ))
                subscription_obj = Subscription(
                    subscription_id=sub_id,
                    customer_id=customer_id,
                    plan_id=plan.plan_id,
                    status=SubscriptionStatus.ACTIVE,
                    amount=plan.price,
                    created_at=t_sub_create,
                )
                t_curr = t_sub_create

        if behaviour.checkout_abandoned:
            t_abandon = t_curr + timedelta(minutes=rng.randint(5, 30))
            events.append(_next_evt(
                EventType.CHECKOUT_ABANDONED,
                t_abandon,
                "checkout",
                {"reason": "funnel_exit"},
            ))
            t_curr = t_abandon

    # 5. Trial expiration state & events
    if subscription_obj is not None:
        trial_status = TrialStatus.ACTIVE
    else:
        if behaviour.hours_remaining is not None and behaviour.hours_remaining <= 48:
            t_expiring = trial_end - timedelta(hours=behaviour.hours_remaining)
            if t_expiring > t_curr:
                events.append(_next_evt(
                    EventType.TRIAL_EXPIRING,
                    t_expiring,
                    "trial",
                    {"hours_remaining": behaviour.hours_remaining},
                ))
                t_curr = t_expiring

        # Trial expired
        events.append(_next_evt(
            EventType.TRIAL_EXPIRED,
            trial_end,
            "trial",
            {"trial_id": f"trl_{customer_id}"},
        ))
        trial_status = TrialStatus.EXPIRED

    trial_obj = Trial(
        trial_id=f"trl_{customer_id}",
        customer_id=customer_id,
        start_at=trial_start,
        end_at=trial_end,
        status=trial_status,
    )

    # Ensure events are chronologically sorted by timestamp
    events.sort(key=lambda x: x.timestamp)

    return customer, trial_obj, events, payment_obj, subscription_obj
