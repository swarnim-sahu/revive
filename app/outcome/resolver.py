"""
Outcome Resolver Module for Revive Phase 7 Engine.
Determines canonical OutcomeType deterministically from observable event evidence and execution records.
Enforces pre-existing conversion protection (ALREADY_CONVERTED) and conservative unknown handling.
"""

from datetime import datetime
from typing import List, Optional, Tuple
from app.models.enums import EventType
from app.models.events import BaseEvent
from app.execution.schemas import ExecutionAuditRecord, ExecutionStatus
from app.outcome.schemas import OutcomeType
from app.outcome.observer import EventObserver, parse_iso_timestamp


class OutcomeResolver:
    """Deterministic, side-effect-free resolver for canonical Phase 7 outcomes."""

    @classmethod
    def resolve_outcome(
        cls,
        execution_record: ExecutionAuditRecord,
        pre_execution_events: List[BaseEvent],
        post_execution_events: List[BaseEvent],
        execution_dt: datetime,
        observation_end_dt: datetime,
        measurement_timestamp_str: str,
    ) -> Tuple[OutcomeType, float, List[BaseEvent], Optional[str]]:
        """
        Deterministically resolve OutcomeType, confidence score, evidence events, and payment reference.
        """
        measurement_dt = parse_iso_timestamp(measurement_timestamp_str)

        # 1. Pre-existing outcome protection (§9)
        if EventObserver.is_pre_existing_conversion(pre_execution_events):
            pre_conv_events = [
                e for e in pre_execution_events
                if e.event_type in {EventType.SUBSCRIPTION_CREATED, EventType.SUBSCRIPTION_RENEWED, EventType.PAYMENT_SUCCEEDED}
            ]
            payment_ref = cls._extract_payment_reference(pre_conv_events)
            return OutcomeType.ALREADY_CONVERTED, 1.0, pre_conv_events, payment_ref

        # 2. Non-dispatched / Ineligible / Escalated execution check
        post_conversions = EventObserver.get_post_execution_conversions(post_execution_events)
        post_failures = EventObserver.get_post_execution_failures(post_execution_events)

        if execution_record.status in {ExecutionStatus.NO_ACTION, ExecutionStatus.BLOCKED, ExecutionStatus.ESCALATED}:
            if post_conversions:
                payment_ref = cls._extract_payment_reference(post_conversions)
                return OutcomeType.CONVERTED, 1.0, post_conversions, payment_ref

            expired_events = [e for e in post_execution_events if e.event_type == EventType.TRIAL_EXPIRED]
            if expired_events:
                return OutcomeType.EXPIRED, 1.0, expired_events, None

            if measurement_dt >= observation_end_dt or len(post_execution_events) > 0:
                return OutcomeType.NOT_RECOVERED, 0.8, post_failures or post_execution_events, None

            return OutcomeType.NO_OBSERVABLE_OUTCOME, 0.5, [], None

        # 3. Active Intervention Execution (ExecutionStatus.EXECUTED)
        if post_conversions:
            # Successfully recovered/converted post-intervention!
            payment_ref = cls._extract_payment_reference(post_conversions)
            if not payment_ref and execution_record.payload_id:
                payment_ref = f"pay_ref_{execution_record.payload_id}"

            confidence = 1.0 if payment_ref else 0.90
            return OutcomeType.RECOVERED, confidence, post_conversions, payment_ref

        expired_events = [e for e in post_execution_events if e.event_type == EventType.TRIAL_EXPIRED]
        if expired_events:
            return OutcomeType.EXPIRED, 1.0, expired_events, None

        if post_failures:
            return OutcomeType.NOT_RECOVERED, 1.0, post_failures, None

        # 4. No events observed inside observation window
        if measurement_dt >= observation_end_dt:
            # Observation window has closed without conversion
            return OutcomeType.NOT_RECOVERED, 0.80, [], None

        # Observation window still open and no events observed yet
        return OutcomeType.NO_OBSERVABLE_OUTCOME, 0.50, [], None

    @classmethod
    def _extract_payment_reference(cls, events: List[BaseEvent]) -> Optional[str]:
        """Extract authoritative payment or subscription identifier from event payload."""
        for evt in events:
            if not isinstance(evt.payload, dict):
                continue
            for key in ("payment_id", "payment_reference", "razorpay_payment_id", "subscription_id", "checkout_id"):
                val = evt.payload.get(key)
                if val and isinstance(val, str) and val.strip():
                    return val.strip()
        return None
