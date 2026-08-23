"""
Configuration module for Revive Phase 5 Intervention Decision Engine.
Defines policy versions, assumption versions, recovery probability assumptions,
direct execution costs, incentive penalty assumptions, and harm penalty assumptions.
"""

from decimal import Decimal
from typing import Dict, Tuple
from pydantic import BaseModel, Field


class InterventionConfig(BaseModel):
    """Configuration and lookup parameters for Phase 5 decision engine."""

    policy_version: str = "v1.0.0"
    assumption_version: str = "v1.0.0"

    # Risk & Value Eligibility Thresholds
    min_risk_eligibility_threshold: float = 0.30
    min_diagnosis_confidence_threshold: float = 0.30
    human_review_revenue_threshold: Decimal = Decimal("2500.00")
    max_trial_extension_hours_until_expiry: float = 48.0
    cooldown_period_hours: float = 72.0

    # Deterministic Recovery Probability Assumptions (Simulation Assumptions)
    # Map: (DiagnosisCategory, InterventionAction) -> float
    recovery_probability_assumptions: Dict[Tuple[str, str], float] = Field(
        default_factory=lambda: {
            ("PAYMENT_FRICTION", "PAYMENT_RECOVERY"): 0.45,
            ("PAYMENT_FRICTION", "REMINDER"): 0.15,
            ("CHECKOUT_ABANDONMENT", "CHECKOUT_ASSISTANCE"): 0.40,
            ("CHECKOUT_ABANDONMENT", "REMINDER"): 0.15,
            ("TRIAL_EXPIRATION", "REMINDER"): 0.30,
            ("TRIAL_EXPIRATION", "TRIAL_EXTENSION"): 0.35,
            ("LOW_INTENT", "PRODUCT_GUIDANCE"): 0.25,
            ("LOW_INTENT", "REMINDER"): 0.15,
            ("LOW_INTENT", "TRIAL_EXTENSION"): 0.20,
            ("ENGAGEMENT_DECLINE", "PRODUCT_GUIDANCE"): 0.30,
            ("ENGAGEMENT_DECLINE", "REMINDER"): 0.20,
            ("MIXED_SIGNALS", "HUMAN_REVIEW"): 0.25,
        }
    )

    # Direct Execution Costs (Decimal INR)
    direct_action_costs: Dict[str, Decimal] = Field(
        default_factory=lambda: {
            "NO_ACTION": Decimal("0.00"),
            "PRODUCT_GUIDANCE": Decimal("0.00"),
            "REMINDER": Decimal("1.50"),
            "CHECKOUT_ASSISTANCE": Decimal("2.00"),
            "PAYMENT_RECOVERY": Decimal("3.00"),
            "TRIAL_EXTENSION": Decimal("5.00"),
            "HUMAN_REVIEW": Decimal("150.00"),
        }
    )

    # Incentive Penalty Assumptions (Decimal fraction of plan price or fixed INR penalty)
    incentive_penalty_fractions: Dict[str, float] = Field(
        default_factory=lambda: {
            "NO_ACTION": 0.0,
            "PRODUCT_GUIDANCE": 0.0,
            "REMINDER": 0.0,
            "CHECKOUT_ASSISTANCE": 0.0,
            "PAYMENT_RECOVERY": 0.0,
            "TRIAL_EXTENSION": 0.10,  # Configurable assumption: 10% of plan price
            "HUMAN_REVIEW": 0.0,
        }
    )

    # Harm Penalty Assumptions (Decimal INR)
    harm_penalty_assumptions: Dict[Tuple[str, str], Decimal] = Field(
        default_factory=lambda: {
            ("NO_ACTION", "NO_ACTION"): Decimal("0.00"),
            # Harm penalties for inappropriate messaging/friction
            ("LOW_INTENT", "CHECKOUT_ASSISTANCE"): Decimal("50.00"),
            ("PAYMENT_FRICTION", "PRODUCT_GUIDANCE"): Decimal("30.00"),
            ("ALREADY_CONVERTED", "REMINDER"): Decimal("500.00"),
        }
    )


DEFAULT_INTERVENTION_CONFIG = InterventionConfig()
