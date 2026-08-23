"""
Explicit Feature Registry for the Revive Revenue Risk Engine.
Defines every feature name, source, data type, description, and inference eligibility.
"""

from dataclasses import dataclass
from typing import Dict, List

FEATURE_REGISTRY_VERSION = "1.0.0"


@dataclass(frozen=True)
class FeatureDefinition:
    """Metadata specification for a model feature."""

    name: str
    source: str
    type: str  # "integer", "float", "boolean", "categorical"
    description: str
    allowed_at_inference: bool


# Registry of all features allowed for model training and inference
FEATURE_REGISTRY: Dict[str, FeatureDefinition] = {
    "session_count": FeatureDefinition(
        name="session_count",
        source="observable events",
        type="integer",
        description="Number of session_started events at or before prediction timestamp",
        allowed_at_inference=True,
    ),
    "feature_use_count": FeatureDefinition(
        name="feature_use_count",
        source="observable events",
        type="integer",
        description="Number of feature_used events at or before prediction timestamp",
        allowed_at_inference=True,
    ),
    "product_activity_count": FeatureDefinition(
        name="product_activity_count",
        source="observable events",
        type="integer",
        description="Number of product_activity events at or before prediction timestamp",
        allowed_at_inference=True,
    ),
    "active_days": FeatureDefinition(
        name="active_days",
        source="observable events",
        type="integer",
        description="Number of unique calendar days with activity at or before prediction timestamp",
        allowed_at_inference=True,
    ),
    "hours_since_last_activity": FeatureDefinition(
        name="hours_since_last_activity",
        source="observable events",
        type="float",
        description="Hours from most recent activity to prediction timestamp",
        allowed_at_inference=True,
    ),
    "hours_since_last_session": FeatureDefinition(
        name="hours_since_last_session",
        source="observable events",
        type="float",
        description="Hours from most recent session to prediction timestamp",
        allowed_at_inference=True,
    ),
    "hours_since_last_feature_use": FeatureDefinition(
        name="hours_since_last_feature_use",
        source="observable events",
        type="float",
        description="Hours from most recent feature use to prediction timestamp",
        allowed_at_inference=True,
    ),
    "pricing_view_count": FeatureDefinition(
        name="pricing_view_count",
        source="observable events",
        type="integer",
        description="Number of pricing_viewed events at or before prediction timestamp",
        allowed_at_inference=True,
    ),
    "checkout_started": FeatureDefinition(
        name="checkout_started",
        source="observable events",
        type="boolean",
        description="1 if checkout_started event exists at or before prediction timestamp, else 0",
        allowed_at_inference=True,
    ),
    "checkout_completed": FeatureDefinition(
        name="checkout_completed",
        source="observable events",
        type="boolean",
        description="1 if checkout_completed event exists at or before prediction timestamp, else 0",
        allowed_at_inference=True,
    ),
    "payment_method_added": FeatureDefinition(
        name="payment_method_added",
        source="observable events",
        type="boolean",
        description="1 if payment_method_added event exists at or before prediction timestamp, else 0",
        allowed_at_inference=True,
    ),
    "payment_attempt_count": FeatureDefinition(
        name="payment_attempt_count",
        source="observable events",
        type="integer",
        description="Number of payment_attempted events at or before prediction timestamp",
        allowed_at_inference=True,
    ),
    "payment_success_count": FeatureDefinition(
        name="payment_success_count",
        source="observable events",
        type="integer",
        description="Number of payment_succeeded events at or before prediction timestamp",
        allowed_at_inference=True,
    ),
    "payment_failure_count": FeatureDefinition(
        name="payment_failure_count",
        source="observable events",
        type="integer",
        description="Number of payment_failed events at or before prediction timestamp",
        allowed_at_inference=True,
    ),
    "has_payment_failure": FeatureDefinition(
        name="has_payment_failure",
        source="observable events",
        type="boolean",
        description="1 if payment_failure_count > 0 at or before prediction timestamp, else 0",
        allowed_at_inference=True,
    ),
    "trial_age_hours": FeatureDefinition(
        name="trial_age_hours",
        source="observable entities",
        type="float",
        description="Hours elapsed from trial start to prediction timestamp",
        allowed_at_inference=True,
    ),
    "hours_until_trial_expiry": FeatureDefinition(
        name="hours_until_trial_expiry",
        source="observable entities",
        type="float",
        description="Hours remaining from prediction timestamp until trial expiry",
        allowed_at_inference=True,
    ),
    "trial_expiring_soon": FeatureDefinition(
        name="trial_expiring_soon",
        source="observable entities",
        type="boolean",
        description="1 if hours_until_trial_expiry <= 24.0, else 0",
        allowed_at_inference=True,
    ),
    "plan_id": FeatureDefinition(
        name="plan_id",
        source="observable entities",
        type="categorical",
        description="Subscription plan identifier (starter, pro, business)",
        allowed_at_inference=True,
    ),
    "plan_price": FeatureDefinition(
        name="plan_price",
        source="observable entities",
        type="float",
        description="Monthly price of the selected plan",
        allowed_at_inference=True,
    ),
    "feature_use_per_session": FeatureDefinition(
        name="feature_use_per_session",
        source="derived",
        type="float",
        description="feature_use_count / session_count (safe zero-denominator handling)",
        allowed_at_inference=True,
    ),
    "pricing_views_per_session": FeatureDefinition(
        name="pricing_views_per_session",
        source="derived",
        type="float",
        description="pricing_view_count / session_count (safe zero-denominator handling)",
        allowed_at_inference=True,
    ),
    "payment_failures_per_attempt": FeatureDefinition(
        name="payment_failures_per_attempt",
        source="derived",
        type="float",
        description="payment_failure_count / payment_attempt_count (safe zero-denominator handling)",
        allowed_at_inference=True,
    ),
    "pricing_view_recency_hours": FeatureDefinition(
        name="pricing_view_recency_hours",
        source="derived",
        type="float",
        description="Hours from most recent pricing_viewed to prediction timestamp",
        allowed_at_inference=True,
    ),
    "checkout_start_recency_hours": FeatureDefinition(
        name="checkout_start_recency_hours",
        source="derived",
        type="float",
        description="Hours from most recent checkout_started to prediction timestamp",
        allowed_at_inference=True,
    ),
    "activity_recency_hours": FeatureDefinition(
        name="activity_recency_hours",
        source="derived",
        type="float",
        description="Hours from most recent product activity to prediction timestamp",
        allowed_at_inference=True,
    ),
}

FORBIDDEN_GROUND_TRUTH_FIELDS = {
    "generation_segment",
    "natural_conversion",
    "conversion_after_intervention",
    "recoverable",
    "maximum_recoverable_revenue",
    "true_root_cause",
}


def get_inference_feature_names() -> List[str]:
    """Return an ordered list of feature names that are allowed for inference."""
    return [
        feat.name
        for feat in FEATURE_REGISTRY.values()
        if feat.allowed_at_inference
    ]
