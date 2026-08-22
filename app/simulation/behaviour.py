"""
Sampling behavioural features per segment for Revive customer simulation.
"""

from dataclasses import dataclass
import random
from typing import Optional


@dataclass
class CustomerBehaviour:
    """Non-deterministic observable behavioural traits for a synthetic customer."""

    sessions: int
    feature_uses: int
    pricing_views: int
    checkout_initiated: bool
    payment_method_added: bool
    checkout_abandoned: bool
    payment_attempted: bool
    payment_succeeded: bool
    payment_failed: bool
    failure_reason: Optional[str]
    hours_remaining: Optional[int]
    checkout_completed: bool
    subscription_created: bool


def sample_behaviour(
    segment: str,
    natural_conversion: bool,
    rng: random.Random,
) -> CustomerBehaviour:
    """
    Sample behavioural features for a customer journey based on segment and seeded rng.
    Introduces natural overlap between segments without leaking ground truth labels into observables.
    """
    if segment == "healthy_converter":
        sessions = rng.randint(8, 25)
        feature_uses = rng.randint(10, 50)
        pricing_views = rng.randint(1, 5)
        checkout_initiated = rng.random() < 0.95
        payment_method_added = checkout_initiated and (rng.random() < 0.90)

        # A healthy converter with natural_conversion=True naturally converts in observable journey.
        # A healthy converter with natural_conversion=False does not convert in pre-intervention observable journey.
        if natural_conversion and checkout_initiated:
            payment_attempted = True
            payment_succeeded = True
            payment_failed = False
            failure_reason = None
            checkout_abandoned = False
            checkout_completed = True
            subscription_created = True
        else:
            payment_attempted = payment_method_added and (rng.random() < 0.80)
            payment_succeeded = False
            payment_failed = payment_attempted
            failure_reason = "temporary_processing_failure" if payment_failed else None
            checkout_completed = False
            subscription_created = False
            checkout_abandoned = checkout_initiated and not payment_failed
        hours_remaining = None

    elif segment == "low_intent":
        sessions = rng.randint(0, 4)
        feature_uses = rng.randint(0, 5)
        pricing_views = rng.randint(0, 1)
        checkout_initiated = rng.random() < 0.05
        payment_method_added = checkout_initiated and (rng.random() < 0.10)
        payment_attempted = False
        payment_succeeded = False
        payment_failed = False
        failure_reason = None
        checkout_abandoned = False
        checkout_completed = False
        subscription_created = False
        hours_remaining = None

    elif segment == "checkout_abandoner":
        sessions = rng.randint(8, 30)
        feature_uses = rng.randint(15, 60)
        pricing_views = rng.randint(2, 6)
        checkout_initiated = True
        payment_method_added = rng.random() < 0.75
        payment_attempted = False
        payment_succeeded = False
        payment_failed = False
        failure_reason = None
        checkout_abandoned = True
        checkout_completed = False
        subscription_created = False
        hours_remaining = rng.randint(1, 48)

    elif segment == "payment_friction":
        sessions = rng.randint(8, 30)
        feature_uses = rng.randint(15, 60)
        pricing_views = rng.randint(2, 6)
        checkout_initiated = True
        payment_method_added = True
        payment_attempted = True
        payment_succeeded = False
        payment_failed = True
        failure_reason = rng.choice([
            "bank_declined",
            "insufficient_funds",
            "payment_method_error",
            "temporary_processing_failure",
        ])
        checkout_abandoned = False
        checkout_completed = False
        subscription_created = False
        hours_remaining = rng.randint(1, 48)

    elif segment == "trial_expiring":
        sessions = rng.randint(6, 25)
        feature_uses = rng.randint(10, 50)
        pricing_views = rng.randint(1, 5)
        hours_remaining = rng.randint(1, 24)
        checkout_initiated = rng.random() < 0.40
        payment_method_added = checkout_initiated and (rng.random() < 0.50)
        payment_attempted = False
        payment_succeeded = False
        payment_failed = False
        failure_reason = None
        checkout_abandoned = checkout_initiated and (rng.random() < 0.50)
        checkout_completed = False
        subscription_created = False

    elif segment == "high_value_at_risk":
        sessions = rng.randint(10, 30)
        feature_uses = rng.randint(20, 70)
        pricing_views = rng.randint(2, 6)
        hours_remaining = rng.randint(1, 48)
        checkout_initiated = rng.random() < 0.70
        payment_method_added = checkout_initiated and (rng.random() < 0.80)

        # Mixture of checkout abandonment or payment friction
        if checkout_initiated and rng.random() < 0.45:
            payment_attempted = True
            payment_failed = True
            payment_succeeded = False
            failure_reason = rng.choice([
                "bank_declined",
                "insufficient_funds",
                "payment_method_error",
                "temporary_processing_failure",
            ])
            checkout_abandoned = False
        elif checkout_initiated:
            payment_attempted = False
            payment_failed = False
            payment_succeeded = False
            failure_reason = None
            checkout_abandoned = True
        else:
            payment_attempted = False
            payment_failed = False
            payment_succeeded = False
            failure_reason = None
            checkout_abandoned = False

        checkout_completed = False
        subscription_created = False

    elif segment == "ambiguous":
        # Conflicting signals
        subtype = rng.choice([1, 2, 3, 4])
        if subtype == 1:
            sessions = rng.randint(15, 25)
            feature_uses = rng.randint(1, 3)  # high sessions, low feature use
            pricing_views = rng.randint(1, 3)
            checkout_initiated = False
        elif subtype == 2:
            sessions = rng.randint(5, 12)
            feature_uses = rng.randint(10, 20)
            pricing_views = rng.randint(4, 8)  # high pricing views, no checkout
            checkout_initiated = False
        elif subtype == 3:
            sessions = rng.randint(2, 4)
            feature_uses = rng.randint(2, 5)
            pricing_views = rng.randint(1, 2)
            checkout_initiated = True  # low activity, but started checkout long ago
        else:
            sessions = rng.randint(12, 20)
            feature_uses = rng.randint(20, 40)
            pricing_views = 0  # high feature usage, 0 pricing views
            checkout_initiated = False

        payment_method_added = checkout_initiated and (rng.random() < 0.40)
        payment_attempted = False
        payment_succeeded = False
        payment_failed = False
        failure_reason = None
        checkout_abandoned = checkout_initiated
        checkout_completed = False
        subscription_created = False
        hours_remaining = rng.randint(1, 36)

    elif segment == "already_converted":
        sessions = rng.randint(8, 25)
        feature_uses = rng.randint(10, 50)
        pricing_views = rng.randint(1, 5)
        checkout_initiated = True
        payment_method_added = True
        payment_attempted = True
        payment_succeeded = True
        payment_failed = False
        failure_reason = None
        checkout_abandoned = False
        checkout_completed = True
        subscription_created = True
        hours_remaining = None

    else:
        raise ValueError(f"Unknown segment: {segment}")

    return CustomerBehaviour(
        sessions=sessions,
        feature_uses=feature_uses,
        pricing_views=pricing_views,
        checkout_initiated=checkout_initiated,
        payment_method_added=payment_method_added,
        checkout_abandoned=checkout_abandoned,
        payment_attempted=payment_attempted,
        payment_succeeded=payment_succeeded,
        payment_failed=payment_failed,
        failure_reason=failure_reason,
        hours_remaining=hours_remaining,
        checkout_completed=checkout_completed,
        subscription_created=subscription_created,
    )
