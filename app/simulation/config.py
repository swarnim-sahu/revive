"""Configuration constants and distribution helpers for Revive synthetic simulation."""

from decimal import Decimal
from typing import Dict, List

from app.models.entities import Merchant, Plan


# --- SYNTHETIC MERCHANT ---
SYNTHETIC_MERCHANT = Merchant(
    merchant_id="merch_codecraft",
    name="CodeCraft Pro",
    currency="INR",
    timezone="Asia/Kolkata",
)


# --- SUBSCRIPTION PLANS ---
PLAN_STARTER = Plan(
    plan_id="starter",
    name="Starter Plan",
    price=Decimal("999.00"),
    currency="INR",
    billing_interval="month",
)

PLAN_PRO = Plan(
    plan_id="pro",
    name="Pro Plan",
    price=Decimal("4999.00"),
    currency="INR",
    billing_interval="month",
)

PLAN_BUSINESS = Plan(
    plan_id="business",
    name="Business Plan",
    price=Decimal("9999.00"),
    currency="INR",
    billing_interval="month",
)

ALL_PLANS: Dict[str, Plan] = {
    PLAN_STARTER.plan_id: PLAN_STARTER,
    PLAN_PRO.plan_id: PLAN_PRO,
    PLAN_BUSINESS.plan_id: PLAN_BUSINESS,
}


# --- TARGET PLAN PERCENTAGES ---
TARGET_PLAN_PERCENTAGES = {
    "starter": 0.50,   # 50% (10,000 for 20k)
    "pro": 0.35,       # 35% (7,000 for 20k)
    "business": 0.15,  # 15% (3,000 for 20k)
}


# --- TARGET SEGMENT PERCENTAGES ---
TARGET_SEGMENT_PERCENTAGES = {
    "healthy_converter": 0.20,   # 20% (4,000 for 20k)
    "low_intent": 0.20,          # 20% (4,000 for 20k)
    "checkout_abandoner": 0.15,  # 15% (3,000 for 20k)
    "payment_friction": 0.12,    # 12% (2,400 for 20k)
    "trial_expiring": 0.10,      # 10% (2,000 for 20k)
    "high_value_at_risk": 0.08,  # 8%  (1,600 for 20k)
    "ambiguous": 0.10,           # 10% (2,000 for 20k)
    "already_converted": 0.05,   # 5%  (1,000 for 20k)
}


def calculate_counts(total: int, proportions: Dict[str, float]) -> Dict[str, int]:
    """
    Calculate exact integer counts per key for a target total based on proportions.
    Ensures that the sum of counts exactly equals `total`.
    """
    counts: Dict[str, int] = {}
    current_sum = 0
    keys = list(proportions.keys())
    for key in keys[:-1]:
        cnt = int(round(total * proportions[key]))
        counts[key] = cnt
        current_sum += cnt
    counts[keys[-1]] = total - current_sum
    return counts
