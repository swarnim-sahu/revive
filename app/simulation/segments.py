"""
Ground-truth generation rules per segment for Revive simulation.

Counterfactual Note on Payment Friction:
A customer with `natural_conversion=True` may still have an observed `payment_failed` event
in their pre-intervention journey (e.g. temporary bank decline or processing glitch).
In that counterfactual scenario, the customer had high intent and would have converted naturally
(e.g., by retrying later or fixing details without agent intervention). Therefore, an agent
intervention would not yield incremental revenue beyond the counterfactual baseline (`recoverable=False`).
"""

from decimal import Decimal
import random
from typing import Tuple

from app.models.entities import Plan
from app.simulation.ground_truth import GroundTruthRecord


def create_ground_truth(
    customer_id: str,
    segment: str,
    plan: Plan,
    rng: random.Random,
) -> GroundTruthRecord:
    """
    Generate a hidden ground-truth record for a customer journey based on segment and plan price.
    Uses seeded `rng` for deterministic reproducibility.
    """
    p = rng.random()

    if segment == "healthy_converter":
        true_root_cause = "none"
        natural_conversion = p < 0.90  # 85-95% target
        conversion_after_intervention = True
    elif segment == "low_intent":
        true_root_cause = "low_intent"
        natural_conversion = p < 0.05  # 2-10% target
        conversion_after_intervention = p < 0.05
    elif segment == "checkout_abandoner":
        true_root_cause = "checkout_abandonment"
        if p < 0.25:  # 25% C1 naturally convertible
            natural_conversion = True
            conversion_after_intervention = True
        elif p < 0.75:  # 50% C2 recoverable
            natural_conversion = False
            conversion_after_intervention = True
        else:  # 25% C3 not recoverable
            natural_conversion = False
            conversion_after_intervention = False
    elif segment == "payment_friction":
        true_root_cause = "payment_friction"
        if p < 0.50:  # 50% D1 recoverable
            natural_conversion = False
            conversion_after_intervention = True
        elif p < 0.70:  # 20% D2 naturally convertible (would convert naturally despite failed payment attempt)
            natural_conversion = True
            conversion_after_intervention = True
        else:  # 30% D3 not recoverable
            natural_conversion = False
            conversion_after_intervention = False
    elif segment == "trial_expiring":
        true_root_cause = "trial_expiration"
        if p < 0.30:  # 30% naturally convertible
            natural_conversion = True
            conversion_after_intervention = True
        elif p < 0.70:  # 40% recoverable
            natural_conversion = False
            conversion_after_intervention = True
        else:  # 30% non-recoverable
            natural_conversion = False
            conversion_after_intervention = False
    elif segment == "high_value_at_risk":
        # Root cause mixture
        true_root_cause = rng.choice(["checkout_abandonment", "payment_friction", "trial_expiration"])
        if p < 0.25:  # 25% naturally convertible
            natural_conversion = True
            conversion_after_intervention = True
        elif p < 0.70:  # 45% recoverable
            natural_conversion = False
            conversion_after_intervention = True
        else:  # 30% non-recoverable
            natural_conversion = False
            conversion_after_intervention = False
    elif segment == "ambiguous":
        true_root_cause = "mixed_signals"
        if p < 0.20:  # 20% naturally convertible
            natural_conversion = True
            conversion_after_intervention = True
        elif p < 0.50:  # 30% recoverable
            natural_conversion = False
            conversion_after_intervention = True
        else:  # 50% non-recoverable
            natural_conversion = False
            conversion_after_intervention = False
    elif segment == "already_converted":
        true_root_cause = "already_converted"
        natural_conversion = True
        conversion_after_intervention = True
    else:
        raise ValueError(f"Unknown segment: {segment}")

    # Counterfactual recoverable rule:
    # recoverable is True iff conversion_after_intervention is True and natural_conversion is False
    recoverable = conversion_after_intervention and (not natural_conversion)
    max_rev = plan.price if recoverable else Decimal("0.00")

    return GroundTruthRecord(
        customer_id=customer_id,
        generation_segment=segment,
        natural_conversion=natural_conversion,
        conversion_after_intervention=conversion_after_intervention,
        recoverable=recoverable,
        maximum_recoverable_revenue=max_rev,
        true_root_cause=true_root_cause,
    )
