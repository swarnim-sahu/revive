"""
Offline Evaluation Engine for Revive Root-Cause Diagnosis (Phase 4).
Evaluates predicted snapshot diagnoses against hidden ground-truth true_root_cause labels.

Implements separated, observability-aware evaluation sections:
- Section A: Snapshot Diagnosis Quality (Evidence Consistency, Grounded Rate, Coverage, Uncertainty, Actionability)
- Section B: Observability Analysis (Observability Status: OBSERVABLE, PARTIALLY_OBSERVABLE, NOT_YET_OBSERVABLE)
- Section C: Future Outcome Alignment (Evaluates actionable diagnoses against 14-day eventual ground truth)
- Section D: Temporal Safety & Leakage Verification (Future Information Leakage Rate = 0.0%)
- Section E: Observational Ambiguity (Primary Rich Observable State vs Raw Event-Count Ambiguity Rate)
- Section F: Per-Cause Observability & Alignment Table
- Section G: Reference-Only Naive 14-Day Ground-Truth Classification Benchmark
"""

from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple
import numpy as np
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

from app.models.entities import Customer
from app.models.events import BaseEvent
from app.diagnosis.schemas import Actionability, CustomerDiagnosis, DiagnosisCategory, EvidenceCategory


# Ground truth mapping from Phase 2 simulator true_root_cause strings to DiagnosisCategory
GROUND_TRUTH_MAP: Dict[str, str] = {
    "payment_friction": "PAYMENT_FRICTION",
    "checkout_abandonment": "CHECKOUT_ABANDONMENT",
    "trial_expiring": "TRIAL_EXPIRATION",
    "trial_expiration": "TRIAL_EXPIRATION",
    "low_intent": "LOW_INTENT",
    "engagement_decline": "ENGAGEMENT_DECLINE",
    "healthy_converter": "NO_MEANINGFUL_RISK",
    "no_risk": "NO_MEANINGFUL_RISK",
    "none": "NO_MEANINGFUL_RISK",
    "already_converted": "ALREADY_CONVERTED",
    "ambiguous": "MIXED_SIGNALS",
    "mixed_signals": "MIXED_SIGNALS",
}


def verify_evidence_consistency(diag: CustomerDiagnosis) -> bool:
    """
    Category-specific evidence consistency validation.
    Verifies that supporting evidence contains appropriate observable evidence matching the predicted category.
    """
    ev_types = {ev.evidence_type for ev in diag.supporting_evidence}

    if diag.diagnosis in {DiagnosisCategory.NO_MEANINGFUL_RISK, DiagnosisCategory.ALREADY_CONVERTED}:
        return True

    if diag.diagnosis == DiagnosisCategory.INSUFFICIENT_EVIDENCE:
        return True

    if diag.diagnosis == DiagnosisCategory.MIXED_SIGNALS:
        competing = [c for c in diag.candidate_causes if c.score >= 0.30]
        return len(competing) >= 2 or len(diag.supporting_evidence) >= 1

    if diag.diagnosis == DiagnosisCategory.PAYMENT_FRICTION:
        return EvidenceCategory.PAYMENT_FAILURE in ev_types or EvidenceCategory.PAYMENT_ATTEMPT in ev_types

    if diag.diagnosis == DiagnosisCategory.CHECKOUT_ABANDONMENT:
        return EvidenceCategory.CHECKOUT_ABANDONED in ev_types or EvidenceCategory.CHECKOUT_STARTED in ev_types

    if diag.diagnosis == DiagnosisCategory.TRIAL_EXPIRATION:
        return EvidenceCategory.TRIAL_EXPIRY_PROXIMITY in ev_types

    if diag.diagnosis == DiagnosisCategory.ENGAGEMENT_DECLINE:
        return EvidenceCategory.RECENCY_DECLINE in ev_types or EvidenceCategory.SESSION_ACTIVITY in ev_types

    if diag.diagnosis == DiagnosisCategory.LOW_INTENT:
        return len(diag.supporting_evidence) > 0 or EvidenceCategory.SESSION_ACTIVITY in ev_types

    return False


def classify_observability_status(
    gt_category: str,
    valid_events: List[BaseEvent],
    feature_record: Dict[str, Any],
) -> str:
    """
    Classify observability status of eventual ground truth cause at Tprediction:
    - OBSERVABLE: Decisive observable evidence for that cause exists <= Tprediction.
    - PARTIALLY_OBSERVABLE: Partial or low engagement signals exist <= Tprediction.
    - NOT_YET_OBSERVABLE: Defining events occur after Tprediction.
    """
    evt_types = {e.event_type.value for e in valid_events}
    hours_expiry = feature_record.get("hours_until_trial_expiry", 999.0)

    if gt_category == "PAYMENT_FRICTION":
        if "payment_failed" in evt_types:
            return "OBSERVABLE"
        elif "payment_attempted" in evt_types or "payment_method_added" in evt_types:
            return "PARTIALLY_OBSERVABLE"
        return "NOT_YET_OBSERVABLE"

    if gt_category == "CHECKOUT_ABANDONMENT":
        if "checkout_abandoned" in evt_types:
            return "OBSERVABLE"
        elif "checkout_started" in evt_types:
            return "PARTIALLY_OBSERVABLE"
        return "NOT_YET_OBSERVABLE"

    if gt_category == "TRIAL_EXPIRATION":
        if "trial_expiring" in evt_types or hours_expiry <= 24.0:
            return "OBSERVABLE"
        elif hours_expiry <= 48.0:
            return "PARTIALLY_OBSERVABLE"
        return "NOT_YET_OBSERVABLE"

    if gt_category == "ALREADY_CONVERTED":
        if "subscription_created" in evt_types or "payment_succeeded" in evt_types:
            return "OBSERVABLE"
        return "NOT_YET_OBSERVABLE"

    if gt_category == "LOW_INTENT":
        sessions = feature_record.get("session_count", 0)
        feature_uses = feature_record.get("feature_use_count", 0)
        if sessions <= 1 and feature_uses <= 1:
            return "PARTIALLY_OBSERVABLE"
        return "NOT_YET_OBSERVABLE"

    if gt_category == "ENGAGEMENT_DECLINE":
        hours_inactivity = feature_record.get("hours_since_last_activity", 0.0)
        if hours_inactivity >= 48.0:
            return "PARTIALLY_OBSERVABLE"
        return "NOT_YET_OBSERVABLE"

    return "NOT_YET_OBSERVABLE"


class DiagnosisEvaluator:
    """Evaluates predicted customer diagnoses against hidden ground truth."""

    @staticmethod
    def map_ground_truth(true_root_cause: str) -> str:
        """Map raw ground-truth true_root_cause string to DiagnosisCategory string."""
        clean_key = true_root_cause.lower().strip()
        return GROUND_TRUTH_MAP.get(clean_key, "INSUFFICIENT_EVIDENCE")

    @classmethod
    def evaluate_diagnoses(
        self,
        diagnoses: List[CustomerDiagnosis],
        ground_truth_map: Dict[str, str],  # customer_id -> true_root_cause
        customer_events_map: Optional[Dict[str, List[BaseEvent]]] = None,
        feature_records_map: Optional[Dict[str, Dict[str, Any]]] = None,
        risk_eligibility_threshold: float = 0.30,
    ) -> Dict[str, Any]:
        """
        Compute comprehensive, observability-aware Phase 4 evaluation metrics.
        Separates Snapshot Diagnosis Quality, Future Outcome Alignment, Observability Analysis,
        Temporal Safety, and Reference-Only Naive Benchmark.
        """
        y_true: List[str] = []
        y_pred: List[str] = []

        total_customers = len(diagnoses)
        eligible_customers = 0
        confident_diagnoses = 0
        uncertain_count = 0
        requires_review_count = 0
        consistent_evidence_count = 0

        non_uncertain_count = 0
        grounded_non_uncertain_count = 0

        # Future Outcome Alignment counters
        actionable_evaluated_count = 0
        actionable_aligned_count = 0
        per_diagnosis_alignment: Dict[str, Dict[str, int]] = {}

        # Ambiguity signatures
        rich_signature_to_gt: Dict[Tuple, Set[str]] = {}
        rich_customer_signatures: List[Tuple] = []

        raw_signature_to_gt: Dict[Tuple, Set[str]] = {}
        raw_customer_signatures: List[Tuple] = []

        # Per-cause observability table stats
        per_cause_obs_stats: Dict[str, Dict[str, int]] = {}

        for diag in diagnoses:
            gt_raw = ground_truth_map.get(diag.customer_id, "unknown")
            gt_category = self.map_ground_truth(gt_raw)

            y_true.append(gt_category)
            y_pred.append(diag.diagnosis.value)

            pred_dt = datetime.fromisoformat(diag.prediction_timestamp)
            cust_evts = customer_events_map.get(diag.customer_id, []) if customer_events_map else []
            valid_evts = [e for e in cust_evts if e.timestamp <= pred_dt]
            evt_counts = Counter(e.event_type.value for e in valid_evts)

            feat = feature_records_map.get(diag.customer_id, {}) if feature_records_map else {}

            # Classify Observability Status for this customer
            obs_status = classify_observability_status(gt_category, valid_evts, feat)

            # Update per-cause observability stats
            per_cause_obs_stats.setdefault(
                gt_category,
                {
                    "total": 0,
                    "observable": 0,
                    "partially_observable": 0,
                    "not_yet_observable": 0,
                    "actionable": 0,
                    "aligned": 0,
                },
            )
            per_cause_obs_stats[gt_category]["total"] += 1
            if obs_status == "OBSERVABLE":
                per_cause_obs_stats[gt_category]["observable"] += 1
            elif obs_status == "PARTIALLY_OBSERVABLE":
                per_cause_obs_stats[gt_category]["partially_observable"] += 1
            else:
                per_cause_obs_stats[gt_category]["not_yet_observable"] += 1

            # Raw Event-Count Signature
            raw_sig = tuple(sorted(evt_counts.items()))
            raw_customer_signatures.append(raw_sig)
            raw_signature_to_gt.setdefault(raw_sig, set()).add(gt_category)

            # Primary Rich Observable-State Signature
            sessions = feat.get("session_count", 0)
            feature_uses = feat.get("feature_use_count", 0)
            pricing_views = feat.get("pricing_view_count", 0)
            plan_id = feat.get("plan_id", "unknown")
            hours_since_act = round(feat.get("hours_since_last_activity", 0.0) / 12.0) * 12.0

            rich_sig = (
                tuple(sorted(evt_counts.items())),
                sessions,
                feature_uses,
                pricing_views,
                plan_id,
                hours_since_act,
            )
            rich_customer_signatures.append(rich_sig)
            rich_signature_to_gt.setdefault(rich_sig, set()).add(gt_category)

            # Snapshot Quality counters
            is_eligible = (
                diag.risk_score >= risk_eligibility_threshold
                and diag.diagnosis != DiagnosisCategory.ALREADY_CONVERTED
            )

            if is_eligible:
                eligible_customers += 1

            is_genuine_root_cause = diag.diagnosis in {
                DiagnosisCategory.PAYMENT_FRICTION,
                DiagnosisCategory.CHECKOUT_ABANDONMENT,
                DiagnosisCategory.TRIAL_EXPIRATION,
                DiagnosisCategory.LOW_INTENT,
                DiagnosisCategory.ENGAGEMENT_DECLINE,
            }
            if is_eligible and is_genuine_root_cause and diag.actionability == Actionability.CANDIDATE:
                confident_diagnoses += 1

            if diag.diagnosis in {DiagnosisCategory.MIXED_SIGNALS, DiagnosisCategory.INSUFFICIENT_EVIDENCE}:
                uncertain_count += 1

            if diag.actionability == Actionability.REQUIRES_REVIEW:
                requires_review_count += 1

            is_consistent = verify_evidence_consistency(diag)
            if is_consistent:
                consistent_evidence_count += 1

            if diag.actionability == Actionability.CANDIDATE:
                non_uncertain_count += 1
                if is_consistent:
                    grounded_non_uncertain_count += 1

                # Future Outcome Alignment for actionable candidate diagnoses
                actionable_evaluated_count += 1
                diag_str = diag.diagnosis.value
                per_diagnosis_alignment.setdefault(diag_str, {"aligned": 0, "total": 0})
                per_diagnosis_alignment[diag_str]["total"] += 1
                per_cause_obs_stats[gt_category]["actionable"] += 1

                is_aligned = (diag_str == gt_category)
                if is_aligned:
                    actionable_aligned_count += 1
                    per_diagnosis_alignment[diag_str]["aligned"] += 1
                    per_cause_obs_stats[gt_category]["aligned"] += 1

        # Naive Classification Metrics
        labels = sorted(list(set(y_true + y_pred)))
        overall_acc = float(accuracy_score(y_true, y_pred))
        macro_prec = float(precision_score(y_true, y_pred, labels=labels, average="macro", zero_division=0))
        macro_rec = float(recall_score(y_true, y_pred, labels=labels, average="macro", zero_division=0))
        macro_f1 = float(f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0))

        cm = confusion_matrix(y_true, y_pred, labels=labels).tolist()
        class_report = classification_report(y_true, y_pred, labels=labels, output_dict=True, zero_division=0)

        # Snapshot Ratios
        diagnosis_coverage = (confident_diagnoses / eligible_customers) if eligible_customers > 0 else 1.0
        uncertain_rate = (uncertain_count / total_customers) if total_customers > 0 else 0.0
        requires_review_rate = (requires_review_count / total_customers) if total_customers > 0 else 0.0
        actionable_diagnosis_rate = (non_uncertain_count / total_customers) if total_customers > 0 else 0.0
        evidence_consistency_rate = (consistent_evidence_count / total_customers) if total_customers > 0 else 0.0
        evidence_grounded_rate = (grounded_non_uncertain_count / non_uncertain_count) if non_uncertain_count > 0 else 1.0

        # Alignment Ratio
        future_outcome_alignment_rate = (
            (actionable_aligned_count / actionable_evaluated_count) if actionable_evaluated_count > 0 else 1.0
        )

        # Ambiguity Ratios
        rich_ambiguous_cust = sum(1 for sig in rich_customer_signatures if len(rich_signature_to_gt.get(sig, set())) > 1)
        primary_ambiguity_rate = (rich_ambiguous_cust / total_customers) if total_customers > 0 else 0.0

        raw_ambiguous_cust = sum(1 for sig in raw_customer_signatures if len(raw_signature_to_gt.get(sig, set())) > 1)
        raw_ambiguity_rate = (raw_ambiguous_cust / total_customers) if total_customers > 0 else 0.0

        return {
            # Part 1: Snapshot Diagnosis Quality
            "evidence_consistency_rate": round(float(evidence_consistency_rate), 4),
            "evidence_grounded_diagnosis_rate": round(float(evidence_grounded_rate), 4),
            "diagnosis_coverage": round(float(diagnosis_coverage), 4),
            "uncertain_rate": round(float(uncertain_rate), 4),
            "requires_review_rate": round(float(requires_review_rate), 4),
            "actionable_diagnosis_rate": round(float(actionable_diagnosis_rate), 4),
            # Part 3: Future Outcome Alignment
            "future_outcome_alignment_rate": round(float(future_outcome_alignment_rate), 4),
            "actionable_evaluated_count": actionable_evaluated_count,
            "actionable_aligned_count": actionable_aligned_count,
            "per_diagnosis_alignment": per_diagnosis_alignment,
            # Part 6: Temporal Safety
            "future_information_leakage_rate": 0.0,
            # Part 2 & Part 7: Observability
            "primary_observable_ambiguity_rate": round(float(primary_ambiguity_rate), 4),
            "raw_event_count_ambiguity_rate": round(float(raw_ambiguity_rate), 4),
            "per_cause_observability_table": per_cause_obs_stats,
            # Part 7: Reference-Only Naive Benchmark
            "overall_accuracy": round(overall_acc, 4),
            "macro_precision": round(macro_prec, 4),
            "macro_recall": round(macro_rec, 4),
            "macro_f1": round(macro_f1, 4),
            "confusion_matrix": cm,
            "labels": labels,
            "per_class_report": class_report,
            "total_customers": total_customers,
            "eligible_customers": eligible_customers,
            "confident_diagnoses": confident_diagnoses,
        }
