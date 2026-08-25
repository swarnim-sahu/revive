"""
Configuration module for Revive Phase 7 Outcome Measurement & Revenue Attribution Engine.
Defines observation window standards, resolver versions, action execution costs, and attribution multipliers.
"""

from decimal import Decimal
from typing import Dict, List
from pydantic import BaseModel, Field

from app.intervention.schemas import InterventionAction


class OutcomeConfig(BaseModel):
    """Configuration parameter schema for Phase 7 Outcome Engine."""

    resolver_version: str = "v1.0.0"
    default_observation_window_hours: float = 168.0  # Default 7 days (168 hours)
    supported_observation_windows_hours: List[float] = Field(
        default_factory=lambda: [24.0, 72.0, 168.0, 336.0]  # 24h, 72h, 7d, 14d
    )

    # Direct Execution Costs matching Phase 5 InterventionConfig (Decimal INR)
    direct_action_costs: Dict[str, Decimal] = Field(
        default_factory=lambda: {
            InterventionAction.NO_ACTION.value: Decimal("0.00"),
            InterventionAction.PRODUCT_GUIDANCE.value: Decimal("0.00"),
            InterventionAction.REMINDER.value: Decimal("1.50"),
            InterventionAction.CHECKOUT_ASSISTANCE.value: Decimal("2.00"),
            InterventionAction.PAYMENT_RECOVERY.value: Decimal("3.00"),
            InterventionAction.TRIAL_EXTENSION.value: Decimal("5.00"),
            InterventionAction.HUMAN_REVIEW.value: Decimal("150.00"),
        }
    )

    # Fraction of gross observed revenue attributed for TEMPORALLY_ASSOCIATED level
    temporally_associated_attribution_fraction: float = 0.50

    # Test-mode endpoint sandbox prefix for simulated Razorpay boundary
    razorpay_simulator_target_prefix: str = "sim://revive/"


DEFAULT_OUTCOME_CONFIG = OutcomeConfig()
