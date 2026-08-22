"""Contains controlled domain values used across Revive."""

from enum import Enum


class EventType(str, Enum):
    """Controlled event types across the customer and recovery lifecycle."""

    CUSTOMER_CREATED = "customer_created"
    TRIAL_STARTED = "trial_started"
    TRIAL_EXPIRING = "trial_expiring"
    TRIAL_EXPIRED = "trial_expired"

    SESSION_STARTED = "session_started"
    FEATURE_USED = "feature_used"
    PRICING_VIEWED = "pricing_viewed"
    PRODUCT_ACTIVITY = "product_activity"

    CHECKOUT_STARTED = "checkout_started"
    CHECKOUT_ABANDONED = "checkout_abandoned"
    CHECKOUT_COMPLETED = "checkout_completed"

    PAYMENT_METHOD_ADDED = "payment_method_added"
    PAYMENT_ATTEMPTED = "payment_attempted"
    PAYMENT_SUCCEEDED = "payment_succeeded"
    PAYMENT_FAILED = "payment_failed"

    SUBSCRIPTION_CREATED = "subscription_created"
    SUBSCRIPTION_CANCELLED = "subscription_cancelled"
    SUBSCRIPTION_RENEWED = "subscription_renewed"

    INTERVENTION_PROPOSED = "intervention_proposed"
    POLICY_APPROVED = "policy_approved"
    POLICY_REJECTED = "policy_rejected"
    RECOVERY_ACTION_EXECUTED = "recovery_action_executed"
    RECOVERY_ACTION_FAILED = "recovery_action_failed"
    RECOVERY_SUCCEEDED = "recovery_succeeded"
    RECOVERY_ESCALATED = "recovery_escalated"


class PaymentStatus(str, Enum):
    """Lifecycle states of a payment attempt."""

    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class TrialStatus(str, Enum):
    """Lifecycle states of a customer trial."""

    ACTIVE = "active"
    EXPIRING = "expiring"
    EXPIRED = "expired"


class SubscriptionStatus(str, Enum):
    """Lifecycle states of a customer subscription."""

    ACTIVE = "active"
    CANCELLED = "cancelled"
    RENEWED = "renewed"


class InterventionType(str, Enum):
    """Bounded intervention catalogue supported by Revive."""

    NO_INTERVENTION = "no_intervention"
    TRIAL_REMINDER = "trial_reminder"
    RESUME_CHECKOUT = "resume_checkout"
    PAYMENT_RECOVERY_PROMPT = "payment_recovery_prompt"
    VALUE_REMINDER = "value_reminder"
    BOUNDED_INCENTIVE = "bounded_incentive"
    HUMAN_ESCALATION = "human_escalation"


class InterventionStatus(str, Enum):
    """Lifecycle states of an intervention."""

    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    FAILED = "failed"
    SUCCEEDED = "succeeded"
    ESCALATED = "escalated"


class PolicyDecision(str, Enum):
    """Policy authorization decision."""

    APPROVED = "approved"
    REJECTED = "rejected"


class RecoveryStatus(str, Enum):
    """Status of the overall recovery workflow."""

    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ESCALATED = "escalated"
