"""
Deterministic Execution State Machine & Retry Engine for Revive Phase 6.
Evaluates state transitions, classifies failure types, enforces retry budgets, and handles fallbacks.
"""

from typing import Optional, Tuple
from app.intervention.schemas import InterventionAction
from app.execution.config import DEFAULT_EXECUTION_CONFIG, ExecutionConfig
from app.execution.schemas import ExecutionState, FailureType


class ExecutionStateMachine:
    """Manages deterministic state transitions, failure classification, and retry/fallback decisions."""

    def __init__(self, config: ExecutionConfig = DEFAULT_EXECUTION_CONFIG) -> None:
        self.config = config

    @classmethod
    def classify_failure(cls, failure_reason: Optional[str]) -> FailureType:
        """
        Deterministically classify a failure reason into RETRYABLE or NON_RETRYABLE.
        """
        if not failure_reason:
            return FailureType.NONE

        reason_lower = failure_reason.lower()

        # Retryable conditions: network timeouts, rate limits, temporary channel errors
        retryable_keywords = [
            "timeout",
            "rate_limit",
            "temporary",
            "transient",
            "channel_busy",
            "connection_reset",
            "503_service_unavailable",
        ]
        for kw in retryable_keywords:
            if kw in reason_lower:
                return FailureType.RETRYABLE

        # Default to NON_RETRYABLE for malformed payloads, rule violations, opt-outs, invalid IDs
        return FailureType.NON_RETRYABLE

    def evaluate_failure_transition(
        self,
        action: InterventionAction,
        current_attempt: int,
        failure_type: FailureType,
    ) -> Tuple[ExecutionState, Optional[InterventionAction]]:
        """
        Evaluate state transition after a dispatch failure.
        Returns Tuple[next_state, fallback_action]:
        - next_state: RETRY, RETRY_EXHAUSTED, FALLBACK, or ESCALATED
        - fallback_action: Next InterventionAction to attempt if FALLBACK state, else None
        """
        max_attempts = self.config.max_retries + 1  # 1 initial + 2 retries = 3 attempts total

        # 1. Non-Retryable Failure: Direct Fallback or Escalation
        if failure_type == FailureType.NON_RETRYABLE:
            return self._resolve_fallback_or_escalation(action)

        # 2. Retryable Failure with Remaining Retry Budget
        if failure_type == FailureType.RETRYABLE and current_attempt < max_attempts:
            return (ExecutionState.RETRY, None)

        # 3. Retryable Failure with Exhausted Retry Budget
        return self._resolve_fallback_or_escalation(action)

    def _resolve_fallback_or_escalation(
        self, action: InterventionAction
    ) -> Tuple[ExecutionState, Optional[InterventionAction]]:
        """Resolve fallback action or human escalation path for exhausted/failed actions."""
        fallback_val = self.config.fallback_map.get(action.value)

        if fallback_val and fallback_val not in {"NO_ACTION", "HUMAN_REVIEW"}:
            try:
                fallback_act = InterventionAction(fallback_val)
                return (ExecutionState.FALLBACK, fallback_act)
            except ValueError:
                pass

        return (ExecutionState.ESCALATED, None)
