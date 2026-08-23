"""
Observable Journey Evidence Extraction for Revive Root-Cause Diagnosis (Phase 4).
Transforms observable events into structured EvidenceItem objects while enforcing
temporal cutoff and ground-truth leakage checks.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.models.entities import Customer, Plan
from app.models.events import BaseEvent
from app.risk.feature_registry import FORBIDDEN_GROUND_TRUTH_FIELDS
from app.diagnosis.config import DiagnosisConfig, DEFAULT_DIAGNOSIS_CONFIG
from app.diagnosis.schemas import EvidenceCategory, EvidenceItem


class EvidenceExtractor:
    """Extracts structured EvidenceItem objects from observable events at prediction snapshot."""

    def __init__(self, config: DiagnosisConfig = DEFAULT_DIAGNOSIS_CONFIG) -> None:
        self.config = config

    def extract_evidence(
        self,
        customer: Customer,
        events: List[BaseEvent],
        plan: Plan,
        prediction_dt: datetime,
    ) -> List[EvidenceItem]:
        """
        Extract observable evidence items from customer state and valid events <= prediction_dt.
        Enforces strict ground-truth leakage checks on all input objects and event payloads.
        """
        # Ground truth leakage checks
        c_dict = customer.model_dump()
        for forbidden in FORBIDDEN_GROUND_TRUTH_FIELDS:
            if forbidden in c_dict:
                raise ValueError(f"Forbidden ground truth field '{forbidden}' found in customer data!")

        # Strict temporal filtering
        valid_events = [e for e in events if e.timestamp <= prediction_dt]

        for e in valid_events:
            for forbidden in FORBIDDEN_GROUND_TRUTH_FIELDS:
                if forbidden in e.payload:
                    raise ValueError(f"Forbidden ground truth field '{forbidden}' found in event payload!")

        evidence_items: List[EvidenceItem] = []

        # 1. Conversion State Check
        conversion_events = [
            e for e in valid_events
            if e.event_type.value in {"subscription_created", "payment_succeeded"}
        ]
        if conversion_events:
            first_conv = min(conversion_events, key=lambda x: x.timestamp)
            evidence_items.append(
                EvidenceItem(
                    evidence_type=EvidenceCategory.CONVERSION_STATE,
                    strength=self.config.strong_weight,
                    source_event=first_conv.event_type.value,
                    description=f"Customer converted naturally before prediction snapshot at {first_conv.timestamp.isoformat()}.",
                    observed_at=first_conv.timestamp.isoformat(),
                )
            )

        # 2. Payment Failure Evidence
        payment_failed_events = [e for e in valid_events if e.event_type.value == "payment_failed"]
        for p_evt in payment_failed_events:
            reason = p_evt.payload.get("failure_reason", "unknown_failure")
            evidence_items.append(
                EvidenceItem(
                    evidence_type=EvidenceCategory.PAYMENT_FAILURE,
                    strength=self.config.strong_weight,
                    source_event="payment_failed",
                    description=f"Payment attempt failed before prediction snapshot (reason: {reason}).",
                    observed_at=p_evt.timestamp.isoformat(),
                )
            )

        # 3. Payment Attempt Evidence
        payment_attempt_events = [e for e in valid_events if e.event_type.value == "payment_attempted"]
        if payment_attempt_events:
            last_attempt = max(payment_attempt_events, key=lambda x: x.timestamp)
            evidence_items.append(
                EvidenceItem(
                    evidence_type=EvidenceCategory.PAYMENT_ATTEMPT,
                    strength=self.config.moderate_weight,
                    source_event="payment_attempted",
                    description=f"Observed {len(payment_attempt_events)} payment attempt(s) prior to snapshot.",
                    observed_at=last_attempt.timestamp.isoformat(),
                )
            )

        # 4. Payment Method Added
        pm_added_events = [e for e in valid_events if e.event_type.value == "payment_method_added"]
        if pm_added_events:
            last_pm = max(pm_added_events, key=lambda x: x.timestamp)
            evidence_items.append(
                EvidenceItem(
                    evidence_type=EvidenceCategory.PAYMENT_METHOD_ADDED,
                    strength=self.config.moderate_weight,
                    source_event="payment_method_added",
                    description="Payment method was successfully added before snapshot.",
                    observed_at=last_pm.timestamp.isoformat(),
                )
            )

        # 5. Checkout Started Evidence
        checkout_started_events = [e for e in valid_events if e.event_type.value == "checkout_started"]
        checkout_completed_events = [e for e in valid_events if e.event_type.value == "checkout_completed"]

        if checkout_started_events:
            last_co = max(checkout_started_events, key=lambda x: x.timestamp)
            evidence_items.append(
                EvidenceItem(
                    evidence_type=EvidenceCategory.CHECKOUT_STARTED,
                    strength=self.config.moderate_weight,
                    source_event="checkout_started",
                    description="Checkout process was initiated before snapshot.",
                    observed_at=last_co.timestamp.isoformat(),
                )
            )

            if not checkout_completed_events:
                evidence_items.append(
                    EvidenceItem(
                        evidence_type=EvidenceCategory.CHECKOUT_ABANDONED,
                        strength=self.config.strong_weight,
                        source_event="checkout_started",
                        description="Checkout was initiated without a subsequent successful payment or explicit payment failure within the observable window.",
                        observed_at=last_co.timestamp.isoformat(),
                    )
                )

        if checkout_completed_events:
            last_coc = max(checkout_completed_events, key=lambda x: x.timestamp)
            evidence_items.append(
                EvidenceItem(
                    evidence_type=EvidenceCategory.CHECKOUT_COMPLETED,
                    strength=self.config.strong_weight,
                    source_event="checkout_completed",
                    description="Checkout was completed before snapshot.",
                    observed_at=last_coc.timestamp.isoformat(),
                )
            )

        # 6. Pricing Views Evidence
        pricing_view_events = [e for e in valid_events if e.event_type.value == "pricing_viewed"]
        if pricing_view_events:
            last_pv = max(pricing_view_events, key=lambda x: x.timestamp)
            evidence_items.append(
                EvidenceItem(
                    evidence_type=EvidenceCategory.PRICING_VIEW,
                    strength=self.config.weak_weight if len(pricing_view_events) == 1 else self.config.moderate_weight,
                    source_event="pricing_viewed",
                    description=f"Viewed pricing page {len(pricing_view_events)} time(s).",
                    observed_at=last_pv.timestamp.isoformat(),
                )
            )

        # 7. Engagement Evidence
        session_events = [e for e in valid_events if e.event_type.value == "session_started"]
        feature_events = [e for e in valid_events if e.event_type.value == "feature_used"]
        product_events = [e for e in valid_events if e.event_type.value == "product_activity"]

        if session_events:
            evidence_items.append(
                EvidenceItem(
                    evidence_type=EvidenceCategory.SESSION_ACTIVITY,
                    strength=self.config.moderate_weight if len(session_events) >= 3 else self.config.weak_weight,
                    source_event="session_started",
                    description=f"Recorded {len(session_events)} session(s) during trial.",
                    observed_at=max(session_events, key=lambda x: x.timestamp).timestamp.isoformat(),
                )
            )

        if feature_events:
            evidence_items.append(
                EvidenceItem(
                    evidence_type=EvidenceCategory.FEATURE_USAGE,
                    strength=self.config.moderate_weight if len(feature_events) >= 3 else self.config.weak_weight,
                    source_event="feature_used",
                    description=f"Used core features {len(feature_events)} time(s).",
                    observed_at=max(feature_events, key=lambda x: x.timestamp).timestamp.isoformat(),
                )
            )

        # 8. Recency & Inactivity Gap
        all_activity_timestamps = [
            e.timestamp for e in valid_events
            if e.event_type.value in {"session_started", "feature_used", "product_activity", "pricing_viewed"}
        ]
        if all_activity_timestamps:
            most_recent_activity = max(all_activity_timestamps)
            hours_since_activity = (prediction_dt - most_recent_activity).total_seconds() / 3600.0
            if hours_since_activity >= 48.0 and len(all_activity_timestamps) >= 2:
                evidence_items.append(
                    EvidenceItem(
                        evidence_type=EvidenceCategory.RECENCY_DECLINE,
                        strength=self.config.strong_weight if hours_since_activity >= 60.0 else self.config.moderate_weight,
                        source_event="product_activity",
                        description=f"Significant recent inactivity gap ({hours_since_activity:.1f} hours since last activity).",
                        observed_at=most_recent_activity.isoformat(),
                    )
                )

        # 9. Trial Expiry Proximity
        trial_started_evts = [e for e in valid_events if e.event_type.value == "trial_started"]
        trial_start = min((e.timestamp for e in trial_started_evts), default=customer.created_at)
        if trial_start:
            trial_end = trial_start + timedelta(days=14)
            hours_until_expiry = (trial_end - prediction_dt).total_seconds() / 3600.0
            if hours_until_expiry <= 24.0:
                evidence_items.append(
                    EvidenceItem(
                        evidence_type=EvidenceCategory.TRIAL_EXPIRY_PROXIMITY,
                        strength=self.config.strong_weight,
                        source_event="trial_expiring",
                        description=f"Trial expires within {hours_until_expiry:.1f} hours.",
                        observed_at=prediction_dt.isoformat(),
                    )
                )

        return evidence_items
