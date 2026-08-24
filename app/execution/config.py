"""
Configuration module for Revive Phase 6 Execution & Workflow Engine.
Defines versioning, retry budgets, cooldown windows, and test-mode environment settings.
"""

from pydantic import BaseModel


class ExecutionConfig(BaseModel):
    """Configuration settings for Phase 6 execution layer."""

    policy_version: str = "v1.0.0"
    execution_version: str = "v1.0.0"

    # Execution Bounds
    max_retries: int = 2  # Total maximum attempts = 1 initial + 2 retries = 3
    cooldown_period_hours: float = 72.0
    environment: str = "TEST_MODE"  # Simulation/test mode guard

    # Fallback map for retry-exhausted or non-retryable failed actions
    # (Action -> Fallback Action)
    fallback_map: dict[str, str] = {
        "CHECKOUT_ASSISTANCE": "REMINDER",
        "PRODUCT_GUIDANCE": "NO_ACTION",
        "REMINDER": "NO_ACTION",
        "PAYMENT_RECOVERY": "HUMAN_REVIEW",
        "TRIAL_EXTENSION": "HUMAN_REVIEW",
    }


DEFAULT_EXECUTION_CONFIG = ExecutionConfig()
