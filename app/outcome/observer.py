"""
Observable Customer Event Extraction & Temporal Filtering Module for Revive Phase 7.
Enforces strict temporal integrity boundaries: post_execution_events must satisfy event.timestamp > execution_timestamp.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Tuple
from app.models.enums import EventType
from app.models.events import BaseEvent


def parse_iso_timestamp(ts_str: str) -> datetime:
    """Parse an ISO 8601 timestamp string into a timezone-aware UTC datetime."""
    dt = datetime.fromisoformat(ts_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class EventObserver:
    """Filters customer events into temporal pre- and post-execution windows."""

    @classmethod
    def observe_events(
        cls,
        events: List[BaseEvent],
        execution_timestamp_str: str,
        observation_window_hours: float,
    ) -> Tuple[List[BaseEvent], List[BaseEvent], datetime, datetime]:
        """
        Partition events into pre-execution (<= execution_timestamp) and post-execution
        (execution_timestamp < timestamp <= execution_timestamp + window_hours).

        Returns:
            (pre_execution_events, post_execution_events, execution_dt, observation_end_dt)
        """
        execution_dt = parse_iso_timestamp(execution_timestamp_str)
        observation_end_dt = execution_dt + timedelta(hours=observation_window_hours)

        pre_execution_events: List[BaseEvent] = []
        post_execution_events: List[BaseEvent] = []

        for evt in events:
            evt_dt = evt.timestamp
            if evt_dt <= execution_dt:
                pre_execution_events.append(evt)
            elif execution_dt < evt_dt <= observation_end_dt:
                post_execution_events.append(evt)

        # Sort chronologically by timestamp
        pre_execution_events.sort(key=lambda e: e.timestamp)
        post_execution_events.sort(key=lambda e: e.timestamp)

        return pre_execution_events, post_execution_events, execution_dt, observation_end_dt

    @classmethod
    def is_pre_existing_conversion(cls, pre_execution_events: List[BaseEvent]) -> bool:
        """Check if customer had an active conversion/paid state BEFORE intervention execution."""
        conversion_types = {
            EventType.SUBSCRIPTION_CREATED,
            EventType.SUBSCRIPTION_RENEWED,
            EventType.PAYMENT_SUCCEEDED,
        }
        return any(evt.event_type in conversion_types for evt in pre_execution_events)

    @classmethod
    def get_post_execution_conversions(cls, post_execution_events: List[BaseEvent]) -> List[BaseEvent]:
        """Extract qualifying conversion/payment events from post-execution window."""
        conversion_types = {
            EventType.SUBSCRIPTION_CREATED,
            EventType.SUBSCRIPTION_RENEWED,
            EventType.PAYMENT_SUCCEEDED,
            EventType.CHECKOUT_COMPLETED,
        }
        return [evt for evt in post_execution_events if evt.event_type in conversion_types]

    @classmethod
    def get_post_execution_failures(cls, post_execution_events: List[BaseEvent]) -> List[BaseEvent]:
        """Extract payment/trial failure events from post-execution window."""
        failure_types = {
            EventType.PAYMENT_FAILED,
            EventType.SUBSCRIPTION_CANCELLED,
            EventType.CHECKOUT_ABANDONED,
            EventType.TRIAL_EXPIRED,
        }
        return [evt for evt in post_execution_events if evt.event_type in failure_types]
