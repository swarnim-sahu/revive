"""
Attribution Engine Module for Revive Phase 7.
Explicitly separates observed outcome, temporal association, and incremental attribution.
Never claims causal attribution unless supported by configured deterministic rules.
"""

from typing import List, Optional, Tuple
from app.models.enums import EventType
from app.models.events import BaseEvent
from app.intervention.schemas import InterventionAction
from app.execution.schemas import ExecutionAuditRecord, ExecutionStatus
from app.outcome.schemas import AttributionMethod, AttributionStatus, OutcomeType


class AttributionEngine:
    """Assigns conservative, evidence-grounded attribution levels to resolved outcomes."""

    @classmethod
    def evaluate_attribution(
        cls,
        outcome: OutcomeType,
        execution_record: ExecutionAuditRecord,
        evidence_events: List[BaseEvent],
        payment_reference: Optional[str],
    ) -> Tuple[AttributionStatus, AttributionMethod]:
        """
        Determine AttributionStatus and AttributionMethod.
        """
        # 1. Non-recovery or pre-existing outcomes are strictly unattributed
        if outcome in {
            OutcomeType.ALREADY_CONVERTED,
            OutcomeType.NOT_RECOVERED,
            OutcomeType.EXPIRED,
            OutcomeType.NO_OBSERVABLE_OUTCOME,
            OutcomeType.UNKNOWN,
        }:
            return AttributionStatus.UNATTRIBUTED, AttributionMethod.NONE

        # 2. Non-dispatched or blocked executions are unattributed
        if execution_record.status in {
            ExecutionStatus.NO_ACTION,
            ExecutionStatus.BLOCKED,
            ExecutionStatus.ESCALATED,
        }:
            return AttributionStatus.UNATTRIBUTED, AttributionMethod.NONE

        # 3. Active Executed Interventions producing RECOVERED or CONVERTED
        action = execution_record.action
        event_types = {e.event_type for e in evidence_events}

        if action == InterventionAction.PAYMENT_RECOVERY and EventType.PAYMENT_SUCCEEDED in event_types:
            return AttributionStatus.DIRECTLY_OBSERVED, AttributionMethod.DETERMINISTIC_RULES

        if action == InterventionAction.CHECKOUT_ASSISTANCE and (
            EventType.CHECKOUT_COMPLETED in event_types or EventType.PAYMENT_SUCCEEDED in event_types
        ):
            return AttributionStatus.DIRECTLY_OBSERVED, AttributionMethod.DETERMINISTIC_RULES

        if action == InterventionAction.TRIAL_EXTENSION and (
            EventType.SUBSCRIPTION_CREATED in event_types or EventType.PAYMENT_SUCCEEDED in event_types
        ):
            return AttributionStatus.ATTRIBUTION_SUPPORTED, AttributionMethod.RULE_BASED_ASSOCIATION

        if action in {InterventionAction.PRODUCT_GUIDANCE, InterventionAction.REMINDER}:
            return AttributionStatus.TEMPORALLY_ASSOCIATED, AttributionMethod.TEMPORAL_WINDOW_ASSOCIATION

        # Default fallback for active executed action producing post-intervention recovery
        return AttributionStatus.TEMPORALLY_ASSOCIATED, AttributionMethod.TEMPORAL_WINDOW_ASSOCIATION
