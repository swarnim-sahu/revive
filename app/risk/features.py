"""
Feature Construction and Snapshot Extraction for the Revive Revenue Risk Engine.
Enforces fixed decision snapshot (trial_start + 72h capped at trial_end), temporal filtering,
and safe ratio calculations.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.models.entities import Customer, Plan
from app.models.events import BaseEvent
from app.risk.feature_registry import FORBIDDEN_GROUND_TRUTH_FIELDS, get_inference_feature_names


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safely divide two numbers, returning `default` on zero denominator, NaN, or Inf."""
    if denominator == 0 or denominator != denominator:  # denominator is 0 or NaN
        return default
    res = numerator / denominator
    if res != res or res == float("inf") or res == float("-inf"):  # res is NaN or Inf
        return default
    return float(res)


class CustomerFeatureExtractor:
    """Extracts snapshot-based risk features from observable customer events and entities."""

    def __init__(self, snapshot_hours: float = 72.0) -> None:
        self.snapshot_hours = snapshot_hours

    def compute_prediction_timestamp(
        self,
        trial_start: datetime,
        trial_end: Optional[datetime] = None,
    ) -> datetime:
        """
        Compute fixed prediction timestamp: trial_start + 72 hours, capped at trial_end.
        """
        if trial_end is None:
            trial_end = trial_start + timedelta(days=14)
        snapshot_dt = trial_start + timedelta(hours=self.snapshot_hours)
        return min(snapshot_dt, trial_end)

    def extract_features(
        self,
        customer: Customer,
        events: List[BaseEvent],
        plan: Plan,
    ) -> Tuple[Dict[str, Any], str]:
        """
        Extract observable features for a customer at the prediction snapshot.
        Returns (feature_dict, status_string). If status != "OK", feature_dict may be empty.
        """
        # Strict ground truth leakage protection check on customer dict
        c_dict = customer.model_dump()
        for forbidden in FORBIDDEN_GROUND_TRUTH_FIELDS:
            if forbidden in c_dict:
                raise ValueError(f"Forbidden ground truth field '{forbidden}' found in customer data!")

        # Find trial start timestamp from trial_started event or customer.created_at
        trial_started_evts = [
            e for e in events if e.event_type.value == "trial_started"
        ]
        if trial_started_evts:
            trial_start = min(e.timestamp for e in trial_started_evts)
        else:
            trial_start = customer.created_at

        if trial_start is None:
            return {}, "INSUFFICIENT_DATA"

        trial_end = trial_start + timedelta(days=14)
        prediction_dt = self.compute_prediction_timestamp(trial_start, trial_end)

        # STRICT TEMPORAL FILTERING: Keep ONLY events occurring at or before prediction_dt
        valid_events = [e for e in events if e.timestamp <= prediction_dt]

        # Check for leakage in event payloads
        for e in valid_events:
            for forbidden in FORBIDDEN_GROUND_TRUTH_FIELDS:
                if forbidden in e.payload:
                    raise ValueError(f"Forbidden ground truth field '{forbidden}' found in event payload!")

        # Calculate counts
        session_count = sum(1 for e in valid_events if e.event_type.value == "session_started")
        feature_use_count = sum(1 for e in valid_events if e.event_type.value == "feature_used")
        product_activity_count = sum(1 for e in valid_events if e.event_type.value == "product_activity")

        # Unique active days
        active_dates = {
            e.timestamp.date() for e in valid_events
            if e.event_type.value in {"session_started", "feature_used", "product_activity", "pricing_viewed"}
        }
        active_days = len(active_dates)

        # Recency calculations (hours from event to prediction_dt)
        trial_age_hours = (prediction_dt - trial_start).total_seconds() / 3600.0
        hours_until_trial_expiry = max(0.0, (trial_end - prediction_dt).total_seconds() / 3600.0)

        # Fallback for recency if no event of that type occurred
        def get_recency(event_type_str: Optional[str] = None) -> float:
            if event_type_str:
                matching = [e.timestamp for e in valid_events if e.event_type.value == event_type_str]
            else:
                matching = [e.timestamp for e in valid_events]

            if not matching:
                return float(trial_age_hours)
            most_recent = max(matching)
            return max(0.0, (prediction_dt - most_recent).total_seconds() / 3600.0)

        hours_since_last_activity = get_recency(None)
        hours_since_last_session = get_recency("session_started")
        hours_since_last_feature_use = get_recency("feature_used")
        pricing_view_recency_hours = get_recency("pricing_viewed")
        checkout_start_recency_hours = get_recency("checkout_started")
        activity_recency_hours = get_recency("product_activity")

        # Commercial intent
        pricing_view_count = sum(1 for e in valid_events if e.event_type.value == "pricing_viewed")
        checkout_started = 1 if any(e.event_type.value == "checkout_started" for e in valid_events) else 0
        checkout_completed = 1 if any(e.event_type.value == "checkout_completed" for e in valid_events) else 0
        payment_method_added = 1 if any(e.event_type.value == "payment_method_added" for e in valid_events) else 0

        # Payment behaviour
        payment_attempt_count = sum(1 for e in valid_events if e.event_type.value == "payment_attempted")
        payment_success_count = sum(1 for e in valid_events if e.event_type.value == "payment_succeeded")
        payment_failure_count = sum(1 for e in valid_events if e.event_type.value == "payment_failed")
        has_payment_failure = 1 if payment_failure_count > 0 else 0

        # Trial state
        trial_expiring_soon = 1 if hours_until_trial_expiry <= 24.0 else 0

        # Derived ratios
        feature_use_per_session = safe_divide(float(feature_use_count), float(session_count))
        pricing_views_per_session = safe_divide(float(pricing_view_count), float(session_count))
        payment_failures_per_attempt = safe_divide(float(payment_failure_count), float(payment_attempt_count))

        plan_price_float = float(plan.price)

        features = {
            "customer_id": customer.customer_id,
            "prediction_timestamp": prediction_dt.isoformat(),
            "session_count": session_count,
            "feature_use_count": feature_use_count,
            "product_activity_count": product_activity_count,
            "active_days": active_days,
            "hours_since_last_activity": hours_since_last_activity,
            "hours_since_last_session": hours_since_last_session,
            "hours_since_last_feature_use": hours_since_last_feature_use,
            "pricing_view_count": pricing_view_count,
            "checkout_started": checkout_started,
            "checkout_completed": checkout_completed,
            "payment_method_added": payment_method_added,
            "payment_attempt_count": payment_attempt_count,
            "payment_success_count": payment_success_count,
            "payment_failure_count": payment_failure_count,
            "has_payment_failure": has_payment_failure,
            "trial_age_hours": trial_age_hours,
            "hours_until_trial_expiry": hours_until_trial_expiry,
            "trial_expiring_soon": trial_expiring_soon,
            "plan_id": plan.plan_id,
            "plan_price": plan_price_float,
            "feature_use_per_session": feature_use_per_session,
            "pricing_views_per_session": pricing_views_per_session,
            "payment_failures_per_attempt": payment_failures_per_attempt,
            "pricing_view_recency_hours": pricing_view_recency_hours,
            "checkout_start_recency_hours": checkout_start_recency_hours,
            "activity_recency_hours": activity_recency_hours,
        }

        return features, "OK"


class FeatureDatasetBuilder:
    """Builds a complete dataset of observable risk features from stored JSONL files."""

    def __init__(self, snapshot_hours: float = 72.0) -> None:
        self.extractor = CustomerFeatureExtractor(snapshot_hours=snapshot_hours)

    def build_observable_features(
        self,
        customers_file: str,
        plans_file: str,
        events_file: str,
    ) -> List[Dict[str, Any]]:
        """
        Build runtime/inference feature records.
        DEPENDS EXCLUSIVELY ON OBSERVABLE DATA: customers.jsonl, plans.jsonl, events.jsonl.
        No parameter for ground_truth_file exists in this runtime path.
        """
        plans_map: Dict[str, Plan] = {}
        with open(plans_file, "r", encoding="utf-8") as f:
            for line in f:
                p_dict = json.loads(line)
                plans_map[p_dict["plan_id"]] = Plan(**p_dict)

        customers_list: List[Customer] = []
        with open(customers_file, "r", encoding="utf-8") as f:
            for line in f:
                c_dict = json.loads(line)
                customers_list.append(Customer(**c_dict))

        events_by_customer: Dict[str, List[BaseEvent]] = {}
        with open(events_file, "r", encoding="utf-8") as f:
            for line in f:
                e_dict = json.loads(line)
                evt = BaseEvent(**e_dict)
                events_by_customer.setdefault(evt.customer_id, []).append(evt)

        feature_records: List[Dict[str, Any]] = []
        for customer in customers_list:
            plan = plans_map[customer.plan_id]
            cust_events = events_by_customer.get(customer.customer_id, [])

            feat_dict, status = self.extractor.extract_features(customer, cust_events, plan)
            if status == "OK":
                feature_records.append(feat_dict)

        return feature_records

    def load_training_labels(self, ground_truth_file: str) -> Dict[str, int]:
        """
        Load hidden ground truth labels for offline training/evaluation ONLY.
        Maps customer_id -> conversion_failure target (1 if not natural_conversion else 0).
        """
        gt_target_map: Dict[str, int] = {}
        with open(ground_truth_file, "r", encoding="utf-8") as f:
            for line in f:
                gt_dict = json.loads(line)
                natural_conv = gt_dict["natural_conversion"]
                gt_target_map[gt_dict["customer_id"]] = 1 if not natural_conv else 0
        return gt_target_map

    def load_and_build(
        self,
        customers_file: str,
        plans_file: str,
        events_file: str,
        ground_truth_file: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], Optional[List[int]]]:
        """
        Offline helper for build_risk_features.py pipeline.
        Builds observable features and optionally pairs them with training labels.
        """
        features = self.build_observable_features(customers_file, plans_file, events_file)

        labels: Optional[List[int]] = None
        if ground_truth_file and Path(ground_truth_file).exists():
            gt_map = self.load_training_labels(ground_truth_file)
            labels = [gt_map[f["customer_id"]] for f in features if f["customer_id"] in gt_map]

        return features, labels
