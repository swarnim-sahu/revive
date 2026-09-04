"""
Phase D Evaluation Runner: Real Gemini Evaluation & AI Evidence (v2.0.0).
Evaluates controlled synthetic customer evidence against Google Gemini.
Measures structured diagnosis quality against an observable expected diagnosis contract,
captures operational reliability with bounded retries and request pacing,
records real token usage, enforces governance/containment boundaries,
and writes committed evidence artifacts with full record persistence.
"""

from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score

from app.models.entities import Customer, Plan
from app.models.events import BaseEvent
from app.simulation.config import ALL_PLANS, SYNTHETIC_MERCHANT
from app.simulation.generator import DatasetGenerator
from app.risk.features import CustomerFeatureExtractor
from app.risk.model import ReviveRiskModel
from app.risk.scoring import RiskScorer, ScoredCustomer
from app.diagnosis.engine import DiagnosisEngine
from app.diagnosis.schemas import (
    Actionability,
    ConfidenceTier,
    CustomerDiagnosis,
    DiagnosisCategory,
    EvidenceCategory,
    EvidenceItem,
)
from app.intervention.engine import InterventionEngine
from app.evaluation.gemini_provider import (
    EVIDENCE_VERSION,
    PROMPT_VERSION,
    GeminiDiagnosisEvaluator,
    GeminiOutputValidator,
    build_gemini_diagnosis_prompt,
)
from app.evaluation.phase_d_schemas import (
    CANONICAL_OBSERVABLE_PRECEDENCE,
    GeminiCallResult,
    GeminiModelCallStatus,
    GeminiStructuredDiagnosis,
    PhaseDCostAccounting,
    PhaseDDemonstrationCase,
    PhaseDExecutionAuthoritySummary,
    PhaseDGeminiResponseSummary,
    PhaseDGovernanceMetrics,
    PhaseDGovernanceSummary,
    PhaseDObservabilityMetrics,
    PhaseDObservableSignalSummary,
    PhaseDOperationalMetrics,
    PhaseDPolicySummary,
    PhaseDQualityMetrics,
    PhaseDRoutingDecision,
    PhaseDEvaluationArtifact,
    PhaseDEvaluationRecord,
    PhaseDEvidenceRecord,
    ReviewMode,
)

# Root directory of the repository
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_DEMO_PATH = _REPO_ROOT / "docs" / "evidence" / "phase_d_gemini_demo.json"
_DEFAULT_HISTORICAL_PATH = _REPO_ROOT / "docs" / "evidence" / "phase_d_gemini_evaluation.json"
_DEFAULT_ARTIFACT_PATH = _DEFAULT_DEMO_PATH

# Canonical deterministic and AI review routing triggers
TRIGGER_DET_CONVERSION = "TRIGGER_DET_CONVERSION"
TRIGGER_DET_PAYMENT_FAILURE = "TRIGGER_DET_PAYMENT_FAILURE"
TRIGGER_DET_CHECKOUT_ABANDONMENT = "TRIGGER_DET_CHECKOUT_ABANDONMENT"
TRIGGER_DET_LOW_RISK = "TRIGGER_DET_LOW_RISK"
TRIGGER_DET_ENGAGEMENT_DECLINE = "TRIGGER_DET_ENGAGEMENT_DECLINE"
TRIGGER_DET_TRIAL_EXPIRATION = "TRIGGER_DET_TRIAL_EXPIRATION"
TRIGGER_DET_LOW_INTENT = "TRIGGER_DET_LOW_INTENT"
TRIGGER_DET_INSUFFICIENT_EVIDENCE = "TRIGGER_DET_INSUFFICIENT_EVIDENCE"
TRIGGER_AI_COMMERCIAL_INTENT_DIVERGENCE = "TRIGGER_AI_COMMERCIAL_INTENT_DIVERGENCE"
TRIGGER_AI_DISPARATE_ENGAGEMENT = "TRIGGER_AI_DISPARATE_ENGAGEMENT"
TRIGGER_AI_INDETERMINATE_SIGNALS = "TRIGGER_AI_INDETERMINATE_SIGNALS"

# Secret and credential redaction patterns
_SECRET_PATTERNS = [
    (re.compile(r"AIza[0-9A-Za-z\-_]{30,}", re.IGNORECASE), "[REDACTED_API_KEY]"),
    (re.compile(r"\b(bearer|api_key|authorization)[\s:=]+(?!\[REDACTED)[^\s,;\"'}\]]+", re.IGNORECASE), r"\1 [REDACTED]"),
    (re.compile(r"\b(secret|token|key)_[0-9a-zA-Z\-_]+", re.IGNORECASE), "[REDACTED_TOKEN]"),
    (re.compile(r"\b(key)=+(?!\[REDACTED)[^\s,;\"'}\]]+", re.IGNORECASE), r"\1=[REDACTED]"),
]



def sanitize_error_message(message: Optional[str]) -> Optional[str]:
    """Sanitize provider error strings to prevent leaking credentials or secrets."""
    if not message:
        return None
    sanitized = str(message)
    for pattern, repl in _SECRET_PATTERNS:
        sanitized = pattern.sub(repl, sanitized)
    return sanitized




def extract_observable_evidence(
    customer: Customer,
    plan: Plan,
    events: List[BaseEvent],
    feature_record: Dict[str, Any],
    scored_customer: ScoredCustomer,
    diagnosis_engine: Optional[DiagnosisEngine] = None,
) -> PhaseDEvidenceRecord:
    """
    Extract strictly observable journey evidence for Gemini evaluation (v2.0.0).
    Constructs observable evidence descriptions directly from observable facts.
    CRITICAL: Zero hidden simulator ground-truth fields are accessed or included here.
    """
    evts_types = {e.event_type.value for e in events}
    hours_expiry = float(feature_record.get("hours_until_trial_expiry", 999.0))
    has_failed = bool(
        feature_record.get("has_payment_failure", False) or "payment_failed" in evts_types
    )
    has_abandoned = bool(
        feature_record.get("has_checkout_abandonment", False)
        or "checkout_abandoned" in evts_types
    )
    days_inactive = float(feature_record.get("days_since_last_active", 0.0))
    has_converted = bool(
        feature_record.get("has_prior_conversion", False)
        or any(t in {"subscription_created", "payment_succeeded"} for t in evts_types)
    )

    # Compute lifetime aggregate counts from all observable events
    lifetime_total_events = len(events)
    lifetime_sessions = sum(1 for e in events if e.event_type.value == "session_started")
    lifetime_features = sum(1 for e in events if e.event_type.value == "feature_used")
    lifetime_pricing = sum(1 for e in events if e.event_type.value == "pricing_viewed")
    lifetime_checkouts = sum(1 for e in events if e.event_type.value == "checkout_started")
    lifetime_pay_attempts = sum(
        1 for e in events if e.event_type.value in {"payment_attempted", "payment_succeeded", "payment_failed"}
    )
    lifetime_pay_successes = sum(1 for e in events if e.event_type.value == "payment_succeeded")
    lifetime_pay_failures = sum(1 for e in events if e.event_type.value == "payment_failed")

    recent_events_summary = [
        {
            "event_type": e.event_type.value,
            "timestamp": e.timestamp.isoformat(),
            "payload": {k: v for k, v in e.payload.items() if not k.startswith("_")},
        }
        for e in events[-5:]
    ]

    # Build observable evidence descriptions directly from observable facts (no coupling to internal heuristics)
    observable_descs: List[str] = []
    if has_converted or lifetime_pay_successes > 0:
        observable_descs.append("Observed prior conversion or active subscription in journey history.")
    if has_failed or lifetime_pay_failures > 0:
        observable_descs.append("Observed payment failure event in journey history.")
    if has_abandoned:
        observable_descs.append("Observed explicit checkout abandonment event in journey history.")
    if (lifetime_sessions >= 3 or lifetime_features >= 3) and days_inactive >= 5.0:
        observable_descs.append(f"Inactivity gap observed: {days_inactive:.1f} days since last active.")
    if hours_expiry <= 48.0 and hours_expiry > 0:
        observable_descs.append(f"Trial expiring soon: {hours_expiry:.1f} hours remaining.")
    elif hours_expiry <= 0 and not has_converted:
        observable_descs.append("Trial period has expired.")
    if lifetime_pricing >= 3 and lifetime_checkouts == 0:
        observable_descs.append(f"Multiple pricing page views ({lifetime_pricing}) with zero checkout starts.")
    if lifetime_sessions >= 12 and lifetime_features <= 3:
        observable_descs.append(f"High session volume ({lifetime_sessions}) with low feature utilization ({lifetime_features}).")
    if lifetime_sessions <= 4 and lifetime_features <= 5 and not has_converted:
        observable_descs.append(f"Low lifetime activity volume: {lifetime_sessions} sessions, {lifetime_features} feature uses.")
    if scored_customer.risk_score >= 0.70:
        observable_descs.append(f"High churn risk score ({scored_customer.risk_score:.4f}, {scored_customer.risk_tier} tier).")
    elif scored_customer.risk_score < 0.30:
        observable_descs.append(f"Low churn risk score ({scored_customer.risk_score:.4f}, {scored_customer.risk_tier} tier).")
    else:
        observable_descs.append(f"Moderate churn risk score ({scored_customer.risk_score:.4f}, {scored_customer.risk_tier} tier).")

    return PhaseDEvidenceRecord(
        evidence_version=EVIDENCE_VERSION,
        customer_id=customer.customer_id,
        plan_name=plan.name,
        plan_price_inr=float(plan.price),
        billing_cycle=plan.billing_interval,
        risk_score=float(scored_customer.risk_score),
        risk_tier=scored_customer.risk_tier,
        revenue_at_risk=float(scored_customer.revenue_at_risk),
        hours_until_trial_expiry=hours_expiry,
        trial_active=bool(hours_expiry > 0.0 and not has_converted),
        payment_failed_observed=has_failed,
        checkout_abandonment_observed=has_abandoned,
        days_since_last_active=days_inactive,
        has_prior_conversion=has_converted,
        lifetime_event_count=lifetime_total_events,
        lifetime_session_count=lifetime_sessions,
        lifetime_feature_use_count=lifetime_features,
        lifetime_pricing_view_count=lifetime_pricing,
        lifetime_checkout_start_count=lifetime_checkouts,
        lifetime_payment_attempt_count=lifetime_pay_attempts,
        lifetime_payment_success_count=lifetime_pay_successes,
        lifetime_payment_failure_count=lifetime_pay_failures,
        recent_observable_events=recent_events_summary,
        observable_evidence_descriptions=observable_descs,
    )


def derive_observable_expected_diagnosis(
    evidence: PhaseDEvidenceRecord,
) -> Tuple[str, bool, Optional[str]]:
    """
    Derives the objective, observable expected diagnosis label strictly from observable evidence facts,
    following CANONICAL_OBSERVABLE_PRECEDENCE.
    Returns:
        (expected_category, is_scoreable, unscoreable_reason)
    """
    # P1: Converted / Active Paid Subscription
    if evidence.has_prior_conversion or evidence.lifetime_payment_success_count > 0:
        return ("ALREADY_CONVERTED", True, None)

    # P2: Payment Failure / Friction
    if evidence.payment_failed_observed or evidence.lifetime_payment_failure_count > 0:
        return ("PAYMENT_FRICTION", True, None)

    # P3: Checkout Abandonment (explicit event required; checkout_started alone is NOT abandonment)
    if evidence.checkout_abandonment_observed:
        return ("CHECKOUT_ABANDONMENT", True, None)

    # P4: Low Risk / No Friction (risk_score < 0.30 with no higher-precedence friction)
    if evidence.risk_score < 0.30:
        return ("NO_MEANINGFUL_RISK", True, None)

    # P5: Engagement Decline (prior activity + inactivity gap >= 5.0 days)
    if (
        (evidence.lifetime_session_count >= 3 or evidence.lifetime_feature_use_count >= 3)
        and evidence.days_since_last_active >= 5.0
    ):
        return ("ENGAGEMENT_DECLINE", True, None)

    # P6: Conflicting Signals (Mixed Signals)
    if (
        evidence.lifetime_pricing_view_count >= 3
        and evidence.lifetime_checkout_start_count == 0
        and evidence.lifetime_session_count >= 5
    ):
        return ("MIXED_SIGNALS", True, None)
    if evidence.lifetime_session_count >= 12 and evidence.lifetime_feature_use_count <= 3:
        return ("MIXED_SIGNALS", True, None)

    # P7: Low Intent (persistently minimal engagement volume)
    if (
        evidence.lifetime_session_count <= 4
        and evidence.lifetime_feature_use_count <= 5
        and evidence.lifetime_pricing_view_count <= 1
        and evidence.lifetime_checkout_start_count == 0
    ):
        return ("LOW_INTENT", True, None)

    # P8: Trial Expiring Soon (0 < hours <= 48) OR Reached Expiry with Active Engagement
    if 0.0 < evidence.hours_until_trial_expiry <= 48.0:
        return ("TRIAL_EXPIRATION", True, None)
    if (evidence.hours_until_trial_expiry <= 0.0 or not evidence.trial_active) and (
        evidence.lifetime_session_count > 4 or evidence.lifetime_feature_use_count > 5
    ):
        return ("TRIAL_EXPIRATION", True, None)

    # P9: Indeterminate / Insufficient Signals (Unscoreable)
    return ("INSUFFICIENT_EVIDENCE", False, "Insufficient distinctive observable signals")


def route_customer_evidence(evidence: PhaseDEvidenceRecord) -> PhaseDRoutingDecision:
    """
    Deterministic AI-review router based exclusively on observable customer evidence.
    Routes to DETERMINISTIC when a clean canonical rule applies.
    Routes to AI_REVIEW when observable signals exhibit commercial intent divergence,
    disparate engagement, or multi-signal ambiguity.
    CRITICAL: Never accesses hidden ground truth, simulator segments, or post-outcome events.
    """
    sig_summary = {
        "risk_score": round(evidence.risk_score, 4),
        "risk_tier": evidence.risk_tier,
        "trial_active": evidence.trial_active,
        "hours_until_trial_expiry": evidence.hours_until_trial_expiry,
        "payment_failed_observed": evidence.payment_failed_observed,
        "checkout_abandonment_observed": evidence.checkout_abandonment_observed,
        "days_since_last_active": evidence.days_since_last_active,
        "has_prior_conversion": evidence.has_prior_conversion,
        "lifetime_sessions": evidence.lifetime_session_count,
        "lifetime_features": evidence.lifetime_feature_use_count,
        "lifetime_pricing_views": evidence.lifetime_pricing_view_count,
        "lifetime_checkout_starts": evidence.lifetime_checkout_start_count,
    }

    # 1. Deterministic Precedence 1: Prior conversion / active payment
    if evidence.has_prior_conversion or evidence.lifetime_payment_success_count > 0:
        return PhaseDRoutingDecision(
            customer_id=evidence.customer_id,
            review_mode=ReviewMode.DETERMINISTIC,
            trigger_id="TRIGGER_DET_CONVERSION",
            routing_reason="Unambiguous active subscription/conversion detected in observable payment history.",
            observable_signal_summary=sig_summary,
        )

    # 2. Deterministic Precedence 2: Payment failure observed
    if evidence.payment_failed_observed or evidence.lifetime_payment_failure_count > 0:
        return PhaseDRoutingDecision(
            customer_id=evidence.customer_id,
            review_mode=ReviewMode.DETERMINISTIC,
            trigger_id="TRIGGER_DET_PAYMENT_FAILURE",
            routing_reason="Unambiguous payment friction: observed payment failure or card decline event recorded.",
            observable_signal_summary=sig_summary,
        )

    # 3. Deterministic Precedence 3: Checkout abandonment observed
    if evidence.checkout_abandonment_observed:
        return PhaseDRoutingDecision(
            customer_id=evidence.customer_id,
            review_mode=ReviewMode.DETERMINISTIC,
            trigger_id="TRIGGER_DET_CHECKOUT_ABANDONMENT",
            routing_reason="Unambiguous checkout abandonment: customer started and explicitly abandoned checkout without payment failure.",
            observable_signal_summary=sig_summary,
        )

    # 4. Deterministic Precedence 4: Low churn risk
    if evidence.risk_score < 0.30:
        return PhaseDRoutingDecision(
            customer_id=evidence.customer_id,
            review_mode=ReviewMode.DETERMINISTIC,
            trigger_id="TRIGGER_DET_LOW_RISK",
            routing_reason="Low churn risk score (< 0.30) with no observable conversion or checkout friction.",
            observable_signal_summary=sig_summary,
        )

    # 5. Deterministic Precedence 5: Engagement decline (inactivity gap >= 5.0 days)
    if (
        (evidence.lifetime_session_count >= 3 or evidence.lifetime_feature_use_count >= 3)
        and evidence.days_since_last_active >= 5.0
    ):
        return PhaseDRoutingDecision(
            customer_id=evidence.customer_id,
            review_mode=ReviewMode.DETERMINISTIC,
            trigger_id="TRIGGER_DET_ENGAGEMENT_DECLINE",
            routing_reason="Clear engagement drop-off: active product history with inactivity gap >= 5.0 days.",
            observable_signal_summary=sig_summary,
        )

    # 6. AI_REVIEW Trigger 1: Commercial intent divergence (pricing views without checkout start)
    if (
        evidence.lifetime_pricing_view_count >= 3
        and evidence.lifetime_checkout_start_count == 0
        and evidence.lifetime_session_count >= 3
    ):
        return PhaseDRoutingDecision(
            customer_id=evidence.customer_id,
            review_mode=ReviewMode.AI_REVIEW,
            trigger_id="TRIGGER_AI_COMMERCIAL_INTENT_DIVERGENCE",
            routing_reason="Conflicting commercial intent: repeated pricing page exploration (>=3 views) without checkout initiation despite active product usage.",
            observable_signal_summary=sig_summary,
        )

    # 7. AI_REVIEW Trigger 2: Disparate engagement pattern
    if (
        evidence.risk_score >= 0.40
        and evidence.lifetime_session_count >= 6
        and evidence.lifetime_feature_use_count <= 3
        and evidence.days_since_last_active <= 3.0
    ):
        return PhaseDRoutingDecision(
            customer_id=evidence.customer_id,
            review_mode=ReviewMode.AI_REVIEW,
            trigger_id="TRIGGER_AI_DISPARATE_ENGAGEMENT",
            routing_reason="Disparate engagement pattern: frequent product sessions with minimal deep feature adoption and elevated churn risk.",
            observable_signal_summary=sig_summary,
        )

    # 8. Deterministic: Clear expiring trial with active usage
    if (0.0 < evidence.hours_until_trial_expiry <= 48.0) or (
        (evidence.hours_until_trial_expiry <= 0.0 or not evidence.trial_active)
        and (evidence.lifetime_session_count > 4 or evidence.lifetime_feature_use_count > 5)
    ):
        return PhaseDRoutingDecision(
            customer_id=evidence.customer_id,
            review_mode=ReviewMode.DETERMINISTIC,
            trigger_id="TRIGGER_DET_TRIAL_EXPIRATION",
            routing_reason="Clear expiring trial pattern: trial expiring soon or reached expiry with active product history.",
            observable_signal_summary=sig_summary,
        )

    # 9. Deterministic: Clear persistent low intent
    if (
        evidence.lifetime_session_count <= 4
        and evidence.lifetime_feature_use_count <= 5
        and evidence.lifetime_pricing_view_count <= 1
        and evidence.lifetime_checkout_start_count == 0
    ):
        return PhaseDRoutingDecision(
            customer_id=evidence.customer_id,
            review_mode=ReviewMode.DETERMINISTIC,
            trigger_id="TRIGGER_DET_LOW_INTENT",
            routing_reason="Clear persistent low intent: minimal lifetime session and feature adoption volume.",
            observable_signal_summary=sig_summary,
        )

    # 10. Fallthrough: Ordinary journey with no observable ambiguity / conflict -> DETERMINISTIC
    return PhaseDRoutingDecision(
        customer_id=evidence.customer_id,
        review_mode=ReviewMode.DETERMINISTIC,
        trigger_id=TRIGGER_DET_INSUFFICIENT_EVIDENCE,
        routing_reason="Unambiguous or unclassified journey without observable multi-signal conflict; routed to deterministic governance.",
        observable_signal_summary=sig_summary,
    )


def generate_synthetic_observable_cohort(
    sample_size: int = 100,
    seed: int = 42,
) -> List[Tuple[Customer, Plan, List[BaseEvent]]]:
    """
    Generate reproducible synthetic customer journeys for Phase D evaluation and demonstration.
    Encapsulates internal simulator data generation machinery so downstream Phase D components
    (evidence extraction, router, selector, evaluator) receive only observable customer entities.
    """
    generator = DatasetGenerator(
        customers_count=sample_size,
        seed=seed,
        output_dir=f"data/temp_phase_d_{seed}_{sample_size}",
    )
    pairs = generator._allocate_plans_and_segments()

    from app.simulation.journey import generate_customer_journey
    from app.simulation.segments import create_ground_truth
    from app.simulation.behaviour import sample_behaviour

    cohort: List[Tuple[Customer, Plan, List[BaseEvent]]] = []

    for idx, (segment, plan_id) in enumerate(pairs, start=1):
        customer_id = f"cus_{idx:06d}"
        plan = ALL_PLANS[plan_id]
        _ = generator.rng.choice([True, False])  # Sequence consistency with Phase B

        gt_rec = create_ground_truth(customer_id, segment, plan, generator.rng)
        behaviour = sample_behaviour(segment, gt_rec.natural_conversion, generator.rng)
        cus, trl, evts, pay, sub = generate_customer_journey(
            customer_id=customer_id,
            merchant_id=SYNTHETIC_MERCHANT.merchant_id,
            plan=plan,
            behaviour=behaviour,
            rng=generator.rng,
        )
        cohort.append((cus, plan, evts))

    return cohort


def select_primary_demonstration_case(
    sample_size: int = 100,
    seed: int = 42,
    snapshot_hours: float = 336.0,
) -> Tuple[Customer, Plan, List[BaseEvent], Dict[str, Any], ScoredCustomer, PhaseDEvidenceRecord, PhaseDRoutingDecision]:
    """
    Deterministically scan the controlled synthetic cohort and select the primary AI_REVIEW demonstration case.
    Applies observable-only complexity ranking across all cases routed to AI_REVIEW.
    CRITICAL: Operates strictly on observable customer journey entities; never imports or accesses hidden simulator ground truth.
    """
    cohort = generate_synthetic_observable_cohort(sample_size=sample_size, seed=seed)

    model_path = "models/risk/risk_model.joblib"
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Risk model artifact not found at '{model_path}'")
    risk_model = ReviveRiskModel.load(model_path)
    risk_scorer = RiskScorer(model=risk_model)
    feature_extractor = CustomerFeatureExtractor(snapshot_hours=snapshot_hours)
    diag_engine = DiagnosisEngine()

    candidates: List[Tuple[float, int, Customer, Plan, List[BaseEvent], Dict[str, Any], ScoredCustomer, PhaseDEvidenceRecord, PhaseDRoutingDecision]] = []

    for idx, (cus, plan, evts) in enumerate(cohort, start=1):
        feat_rec, status_str = feature_extractor.extract_features(cus, evts, plan)
        if status_str != "OK":
            continue

        scored_cust = risk_scorer.score_customer(feat_rec)
        evidence = extract_observable_evidence(cus, plan, evts, feat_rec, scored_cust, diag_engine)
        routing = route_customer_evidence(evidence)

        if routing.review_mode == ReviewMode.AI_REVIEW:
            # Observable-only complexity ranking score:
            # Rewards multi-signal complexity: repeated pricing views, feature interactions, sessions, and risk
            complexity_score = (
                (evidence.lifetime_pricing_view_count * 3.0)
                + float(evidence.lifetime_feature_use_count)
                + float(evidence.lifetime_session_count)
                + (evidence.risk_score * 10.0)
            )
            candidates.append((complexity_score, idx, cus, plan, evts, feat_rec, scored_cust, evidence, routing))

    if not candidates:
        raise RuntimeError("No candidate customer met the deterministic AI_REVIEW criteria in the generated cohort.")

    # Sort descending by complexity score, tie-breaking on deterministic cohort index ascending
    candidates.sort(key=lambda x: (-x[0], x[1]))
    _, _, best_cus, best_plan, best_evts, best_feat, best_sc, best_evidence, best_routing = candidates[0]
    return best_cus, best_plan, best_evts, best_feat, best_sc, best_evidence, best_routing


class PhaseDEvaluator:
    """Master orchestrator for Phase D Real Gemini Evaluation (v2.0.0)."""

    def __init__(
        self,
        sample_size: int = 100,
        seed: int = 42,
        snapshot_hours: float = 336.0,
        evaluator: Optional[GeminiDiagnosisEvaluator] = None,
        enable_fallback: bool = True,
        timeout_seconds: Optional[float] = None,
        pacing_delay_seconds: Optional[float] = None,
        max_retries: Optional[int] = None,
        initial_backoff_seconds: Optional[float] = None,
    ) -> None:
        self.sample_size = sample_size
        self.seed = seed
        self.snapshot_hours = snapshot_hours
        self.evaluator = evaluator or GeminiDiagnosisEvaluator(
            timeout_seconds=timeout_seconds,
            pacing_delay_seconds=pacing_delay_seconds,
            max_retries=max_retries,
            initial_backoff_seconds=initial_backoff_seconds,
        )
        self.enable_fallback = enable_fallback
        self.diagnosis_engine = DiagnosisEngine()

    def run_evaluation(self) -> PhaseDEvaluationArtifact:
        """Run full evaluation across deterministic synthetic customer journeys."""
        run_timestamp = datetime.now(timezone.utc).isoformat()
        run_id = f"phase_d_eval_{int(time.time())}"

        cohort = generate_synthetic_observable_cohort(sample_size=self.sample_size, seed=self.seed)

        # 2. Risk Scorer and Feature Extractor
        model_path = "models/risk/risk_model.joblib"
        if os.path.exists(model_path):
            risk_model = ReviveRiskModel.load(model_path)
        else:
            raise FileNotFoundError(f"Risk model artifact not found at '{model_path}'")

        risk_scorer = RiskScorer(model=risk_model)
        feature_extractor = CustomerFeatureExtractor(snapshot_hours=self.snapshot_hours)

        records: List[PhaseDEvaluationRecord] = []
        raw_latencies: List[float] = []

        total_prompt_tokens = 0
        total_candidates_tokens = 0
        total_tokens = 0
        has_token_data = False

        for cust, plan, evts in cohort:
            cid = cust.customer_id
            feat_rec, status_str = feature_extractor.extract_features(cust, evts, plan)
            if status_str != "OK":
                continue

            scored_cust = risk_scorer.score_customer(feat_rec)

            # Build canonical observable evidence (NEVER accesses ground_truth)
            evidence = extract_observable_evidence(
                cust, plan, evts, feat_rec, scored_cust, self.diagnosis_engine
            )
            ev_hash = evidence.compute_hash()

            # Derive objective observable expected diagnosis contract strictly from observable facts
            obs_expected, is_scoreable, unscoreable_reason = derive_observable_expected_diagnosis(evidence)

            # Evaluate with Gemini
            call_res: GeminiCallResult = self.evaluator.evaluate(evidence)
            raw_latencies.append(call_res.latency_ms)

            # Track tokens
            if call_res.total_tokens is not None:
                has_token_data = True
                total_prompt_tokens += call_res.prompt_tokens or 0
                total_candidates_tokens += call_res.candidates_tokens or 0
                total_tokens += call_res.total_tokens

            # Determine fallback if enabled and call failed/unavailable
            fallback_used = False
            fallback_diag_str = None
            if call_res.status != GeminiModelCallStatus.REAL_GEMINI and self.enable_fallback:
                fallback_used = True
                det_diag = self.diagnosis_engine.diagnose_customer(
                    scored_cust, cust, evts, plan, feat_rec
                )
                fallback_diag_str = det_diag.diagnosis.value

            # Check for governance issues in model output
            unsupported_claim = False
            bypass_attempt = False
            policy_viol = False
            if call_res.raw_response_text:
                _, _, _, unsupp, bypass, viol = GeminiOutputValidator.validate(
                    call_res.raw_response_text, evidence
                )
                unsupported_claim = unsupp
                bypass_attempt = bypass
                policy_viol = viol

            # Correctness determination (against observable expected contract)
            is_correct = None
            validated_diag_val = None
            conf_val = None
            act_val = None
            rationale_val = None
            ev_used_val = []
            uncert_val = []

            if call_res.status == GeminiModelCallStatus.REAL_GEMINI and call_res.parsed_json:
                validated_diag_val = call_res.parsed_json.get("diagnosis")
                conf_val = call_res.parsed_json.get("confidence")
                act_val = call_res.parsed_json.get("actionability")
                rationale_val = call_res.parsed_json.get("rationale")
                ev_used_val = call_res.parsed_json.get("evidence_used", [])
                uncert_val = call_res.parsed_json.get("uncertainty_reasons", [])
                if is_scoreable:
                    is_correct = bool(validated_diag_val == obs_expected)

            sanitized_call_err = sanitize_error_message(call_res.error_message)
            rec_err_type = call_res.error_type if call_res.status in (GeminiModelCallStatus.MODEL_ERROR, GeminiModelCallStatus.MODEL_UNAVAILABLE) else None
            rec_err_msg = sanitized_call_err if call_res.status in (GeminiModelCallStatus.MODEL_ERROR, GeminiModelCallStatus.MODEL_UNAVAILABLE) else None
            rec_val_err = sanitized_call_err if call_res.status == GeminiModelCallStatus.SCHEMA_REJECTED else None

            rec = PhaseDEvaluationRecord(
                customer_id=cid,
                evidence_version=EVIDENCE_VERSION,
                evidence_hash=ev_hash,
                prompt_version=PROMPT_VERSION,
                model_call_status=call_res.status,
                validated_diagnosis=validated_diag_val,
                confidence=conf_val,
                actionability=act_val,
                rationale=rationale_val,
                evidence_used=ev_used_val,
                uncertainty_reasons=uncert_val,
                error_type=rec_err_type,
                error_message=rec_err_msg,
                validation_error=rec_val_err,
                unsupported_action_claim_detected=unsupported_claim,
                execution_bypass_attempt_detected=bypass_attempt,
                policy_guard_violation_detected=policy_viol,
                latency_ms=call_res.latency_ms,
                retries_attempted=call_res.retries_attempted,

                tokens=(
                    {
                        "prompt_tokens": call_res.prompt_tokens or 0,
                        "candidates_tokens": call_res.candidates_tokens or 0,
                        "total_tokens": call_res.total_tokens or 0,
                    }
                    if call_res.total_tokens is not None
                    else None
                ),
                observable_expected_diagnosis=obs_expected,
                is_scoreable=is_scoreable,
                unscoreable_reason=unscoreable_reason,
                is_correct=is_correct,
                fallback_used=fallback_used,
                fallback_diagnosis=fallback_diag_str,
            )
            records.append(rec)

        # 2. Operational Metrics Calculation & Reconciliation
        attempted = len(records)
        successful = sum(
            1 for r in records if r.model_call_status == GeminiModelCallStatus.REAL_GEMINI
        )
        schema_rejected = sum(
            1 for r in records if r.model_call_status == GeminiModelCallStatus.SCHEMA_REJECTED
        )
        model_errors = sum(
            1 for r in records if r.model_call_status == GeminiModelCallStatus.MODEL_ERROR
        )
        unavailable = sum(
            1 for r in records if r.model_call_status == GeminiModelCallStatus.MODEL_UNAVAILABLE
        )
        fallback_count = sum(1 for r in records if r.fallback_used)
        scoreable_evals = sum(1 for r in records if r.is_scoreable)
        not_scoreable_evals = sum(1 for r in records if not r.is_scoreable)
        total_retries = sum(r.retries_attempted for r in records)
        rate_limit_events = sum(1 for r in records if r.retries_attempted > 0)

        # Reconciliation: Every attempted call has exactly one terminal model call status
        reconciliation_passed = attempted == (successful + schema_rejected + model_errors + unavailable)
        reconciliation_formula = (
            "attempted == (successful + schema_rejected + model_errors + unavailable); "
            "fallback_evaluations is tracked as a secondary mitigation metric when model call is non-successful."
        )

        avg_latency = float(np.mean(raw_latencies)) if raw_latencies else 0.0
        p95_latency = float(np.percentile(raw_latencies, 95)) if len(raw_latencies) >= 20 else avg_latency
        success_rate_pct = round(100.0 * successful / attempted, 2) if attempted > 0 else 0.0

        operational_metrics = PhaseDOperationalMetrics(
            attempted_evaluations=attempted,
            successful_evaluations=successful,
            schema_rejections=schema_rejected,
            model_errors=model_errors,
            unavailable_evaluations=unavailable,
            fallback_evaluations=fallback_count,
            scoreable_evaluations=scoreable_evals,
            not_scoreable_evaluations=not_scoreable_evals,
            total_retries=total_retries,
            rate_limit_events=rate_limit_events,
            success_rate_pct=success_rate_pct,
            average_latency_ms=round(avg_latency, 2),
            p95_latency_ms=round(p95_latency, 2),
            reconciliation_passed=reconciliation_passed,
            reconciliation_formula=reconciliation_formula,
        )

        # 3. Model Diagnosis Quality Metrics Calculation (Scoreable Denominator Isolation)
        scoreable_eval_records = [
            r
            for r in records
            if r.model_call_status == GeminiModelCallStatus.REAL_GEMINI
            and r.is_scoreable
            and r.validated_diagnosis is not None
        ]
        scoreable_count = len(scoreable_eval_records)

        if scoreable_count > 0:
            y_true = [r.observable_expected_diagnosis for r in scoreable_eval_records]
            y_pred = [r.validated_diagnosis for r in scoreable_eval_records]

            acc = float(accuracy_score(y_true, y_pred))
            prec = float(precision_score(y_true, y_pred, average="macro", zero_division=0))
            rec_sc = float(recall_score(y_true, y_pred, average="macro", zero_division=0))
            f1 = float(f1_score(y_true, y_pred, average="macro", zero_division=0))

            # Per-category metrics & Confusion Matrix
            unique_labels = sorted(list(set(y_true + y_pred)))
            cm = confusion_matrix(y_true, y_pred, labels=unique_labels).tolist()

            per_cat: Dict[str, Dict[str, Any]] = {}
            for lbl in unique_labels:
                lbl_true = [1 if yt == lbl else 0 for yt in y_true]
                lbl_pred = [1 if yp == lbl else 0 for yp in y_pred]
                support = sum(lbl_true)
                p = float(precision_score(lbl_true, lbl_pred, zero_division=0))
                r = float(recall_score(lbl_true, lbl_pred, zero_division=0))
                f = float(f1_score(lbl_true, lbl_pred, zero_division=0))
                per_cat[lbl] = {
                    "support": support,
                    "precision": round(p, 4),
                    "recall": round(r, 4),
                    "f1": round(f, 4),
                }

            quality_metrics = PhaseDQualityMetrics(
                available=True,
                evaluation_basis=f"Evaluated across {scoreable_count} scoreable real Gemini diagnoses (grounded in observable evidence contract)",
                scoreable_denominator=scoreable_count,
                diagnosis_accuracy=round(acc, 4),
                macro_precision=round(prec, 4),
                macro_recall=round(rec_sc, 4),
                macro_f1=round(f1, 4),
                per_category_metrics=per_cat,
                confusion_matrix=cm,
                confusion_matrix_labels=unique_labels,
            )
        else:
            quality_metrics = PhaseDQualityMetrics(
                available=False,
                evaluation_basis=(
                    "Quality metrics unavailable: 0 scoreable real Gemini responses received "
                    f"({unavailable} unavailable, {model_errors} errors, {schema_rejected} schema rejected)."
                ),
                scoreable_denominator=0,
                diagnosis_accuracy=None,
                macro_precision=None,
                macro_recall=None,
                macro_f1=None,
                per_category_metrics={},
                confusion_matrix=[],
                confusion_matrix_labels=[],
            )

        # 4. Observability Metrics
        obs_label_dist: Dict[str, int] = {}
        for r in records:
            lbl = r.observable_expected_diagnosis
            obs_label_dist[lbl] = obs_label_dist.get(lbl, 0) + 1

        observability_metrics = PhaseDObservabilityMetrics(
            total_evaluated=attempted,
            scoreable_count=scoreable_evals,
            unscoreable_count=not_scoreable_evals,
            scoreable_rate_pct=round(100.0 * scoreable_evals / attempted, 2) if attempted > 0 else 0.0,
            observable_label_distribution=obs_label_dist,
        )

        # 5. Governance & Safety Metrics Calculation
        bypass_attempts = sum(1 for r in records if r.execution_bypass_attempt_detected)
        unsupported_claims = sum(1 for r in records if r.unsupported_action_claim_detected)
        policy_violations = sum(1 for r in records if r.policy_guard_violation_detected)

        non_compliant_records = sum(
            1
            for r in records
            if (
                r.execution_bypass_attempt_detected
                or r.unsupported_action_claim_detected
                or r.policy_guard_violation_detected
            )
        )
        compliant_records = attempted - non_compliant_records
        safety_compliance = (
            round(100.0 * compliant_records / attempted, 2)
            if attempted > 0
            else 100.0
        )
        governance_verdict = (
            "SAFETY_VERIFIED: Zero unauthorized execution claims, policy bypass attempts, or guard violations observed."
            if non_compliant_records == 0
            else "GOVERNANCE_VIOLATIONS_DETECTED"
        )

        governance_metrics = PhaseDGovernanceMetrics(
            execution_bypass_attempts_observed=bypass_attempts,
            unsupported_action_claims_observed=unsupported_claims,
            policy_guard_violations_observed=policy_violations,
            non_compliant_records_count=non_compliant_records,
            safety_compliance_rate_pct=safety_compliance,
            governance_verdict=governance_verdict,
        )

        # 6. Cost Accounting
        if has_token_data:
            cost_accounting = PhaseDCostAccounting(
                cost_data_status="PROVIDER_REPORTED_USAGE",
                prompt_tokens_sum=total_prompt_tokens,
                candidates_tokens_sum=total_candidates_tokens,
                total_tokens_sum=total_tokens,
                estimated_cost_inr=None,
                cost_basis_note="Token counts reported directly by Google Gemini API usage metadata. Currency cost not fabricated.",
            )
        else:
            cost_accounting = PhaseDCostAccounting(
                cost_data_status="COST_DATA_UNAVAILABLE",
                prompt_tokens_sum=None,
                candidates_tokens_sum=None,
                total_tokens_sum=None,
                estimated_cost_inr=None,
                cost_basis_note="Cost and token usage data unavailable because real Gemini API requests were not completed.",
            )

        # 7. Failure Summary
        failure_summary = {
            "model_unavailable_count": unavailable,
            "model_error_count": model_errors,
            "schema_rejected_count": schema_rejected,
            "fallback_used_count": fallback_count,
            "diagnostic_details": [
                {
                    "customer_id": r.customer_id,
                    "status": r.model_call_status.value,
                    "error": r.validation_error,
                }
                for r in records
                if r.model_call_status != GeminiModelCallStatus.REAL_GEMINI
            ][:10],
        }

        # 8. Overall Execution State
        if successful == attempted:
            exec_state = "REAL_GEMINI"
        elif unavailable == attempted:
            exec_state = "MODEL_UNAVAILABLE"
        elif model_errors == attempted:
            exec_state = "MODEL_ERROR"
        elif fallback_count > 0:
            exec_state = "FALLBACK_USED"
        elif successful > 0:
            exec_state = "PARTIAL_REAL_GEMINI"
        else:
            exec_state = "SCHEMA_REJECTED"

        # 9. Assemble Artifact (with complete evaluation_records persistence)
        artifact = PhaseDEvaluationArtifact(
            metadata={
                "run_id": run_id,
                "timestamp": run_timestamp,
                "dataset_name": "Phase D Gemini Evaluation Sample (100 customers, Seed 42)",
                "note": (
                    "CRITICAL PROVENANCE: This dataset is a dedicated 100-customer Phase D evaluation sample. "
                    "It is NOT the authoritative Phase B 10,000-pair benchmark."
                ),
                "sample_size": self.sample_size,
                "seed": self.seed,
                "snapshot_hours": self.snapshot_hours,
                "selection_method": "Deterministic first 100 synthetic customer units from Seed 42 generator",
            },
            model=self.evaluator.model,
            prompt_version=PROMPT_VERSION,
            evidence_version=EVIDENCE_VERSION,
            execution_state=exec_state,
            operational_metrics=operational_metrics,
            quality_metrics=quality_metrics,
            observability_metrics=observability_metrics,
            governance_metrics=governance_metrics,
            cost_accounting=cost_accounting,
            failure_summary=failure_summary,
            sample_records=[r.model_dump() for r in records[:5]],
            evaluation_records=[r.model_dump() for r in records],
        )

        return artifact


def run_demonstration(
    output_path: Optional[Path] = None,
    evaluator: Optional[GeminiDiagnosisEvaluator] = None,
    enable_fallback: bool = True,
    sample_size: int = 100,
    seed: int = 42,
    timeout_seconds: Optional[float] = None,
    pacing_delay_seconds: Optional[float] = None,
    max_retries: Optional[int] = None,
    initial_backoff_seconds: Optional[float] = None,
) -> PhaseDEvaluationArtifact:
    """
    Execute primary selective real Gemini demonstration (Phase D v3.0.0).
    Selects one controlled synthetic case via deterministic observable routing,
    invokes Gemini for structured diagnosis, validates against governance containment,
    and passes the diagnosis hypothesis to deterministic policy for authorization evaluation.
    Writes truthful demonstration artifact to docs/evidence/phase_d_gemini_demo.json.
    """
    run_timestamp = datetime.now(timezone.utc).isoformat()
    run_id = f"phase_d_demo_{int(time.time())}"

    gemini_evaluator = evaluator or GeminiDiagnosisEvaluator(
        timeout_seconds=timeout_seconds,
        pacing_delay_seconds=pacing_delay_seconds,
        max_retries=max_retries,
        initial_backoff_seconds=initial_backoff_seconds,
    )

    cus, plan, evts, feat_rec, scored_cust, evidence, routing = select_primary_demonstration_case(
        sample_size=sample_size,
        seed=seed,
    )
    ev_hash = evidence.compute_hash()

    intervention_engine = InterventionEngine()
    diag_engine = DiagnosisEngine()

    call_result: Optional[GeminiCallResult] = None
    structured_diag: Optional[GeminiStructuredDiagnosis] = None
    fallback_used = False
    fallback_diag_val: Optional[str] = None

    if routing.review_mode == ReviewMode.AI_REVIEW:
        call_result = gemini_evaluator.evaluate(evidence, routing_reason=routing.routing_reason)

        if call_result.status == GeminiModelCallStatus.REAL_GEMINI and call_result.parsed_json:
            try:
                structured_diag = GeminiStructuredDiagnosis(**call_result.parsed_json)
            except Exception:
                structured_diag = None
        elif enable_fallback:
            fallback_used = True
            det_diag = diag_engine.diagnose_customer(scored_cust, cus, evts, plan, feat_rec)
            fallback_diag_val = det_diag.diagnosis.value

    # Build deterministic policy input (CustomerDiagnosis) from model proposal or fallback
    if structured_diag is not None:
        proposed_cat = structured_diag.diagnosis
        proposed_conf = structured_diag.confidence
        proposed_act = structured_diag.actionability
        rationale_text = structured_diag.rationale
        evidence_items_list = [
            EvidenceItem(
                evidence_type=EvidenceCategory.PRODUCT_ACTIVITY,
                strength=round(proposed_conf, 2),
                description=str(e_item),
            )
            for e_item in structured_diag.evidence_used[:5]
        ] or [
            EvidenceItem(
                evidence_type=EvidenceCategory.PRODUCT_ACTIVITY,
                strength=round(proposed_conf, 2),
                description="Observable product signals supporting AI diagnosis.",
            )
        ]
        conf_tier = (
            ConfidenceTier.VERY_HIGH if proposed_conf >= 0.85
            else ConfidenceTier.HIGH if proposed_conf >= 0.70
            else ConfidenceTier.MEDIUM if proposed_conf >= 0.50
            else ConfidenceTier.LOW
        )
    else:
        # Fallback to deterministic diagnosis engine
        fallback_used = True
        det_diag = diag_engine.diagnose_customer(scored_cust, cus, evts, plan, feat_rec)

        proposed_cat = det_diag.diagnosis
        proposed_conf = det_diag.confidence
        proposed_act = det_diag.actionability
        rationale_text = det_diag.explanation
        evidence_items_list = det_diag.supporting_evidence
        conf_tier = det_diag.confidence_tier
        fallback_diag_val = det_diag.diagnosis.value

    # Evaluate deterministic intervention policy
    policy_customer_diag = CustomerDiagnosis(
        customer_id=cus.customer_id,
        prediction_timestamp=run_timestamp,
        risk_score=float(scored_cust.risk_score),
        risk_tier=scored_cust.risk_tier,
        diagnosis=proposed_cat,
        confidence=proposed_conf,
        confidence_tier=conf_tier,
        actionability=proposed_act,
        candidate_causes=[],
        supporting_evidence=evidence_items_list,
        explanation=rationale_text,
    )

    decision = intervention_engine.decide_intervention(
        scored_customer=scored_cust,
        diagnosis=policy_customer_diag,
        plan=plan,
        feature_record=feat_rec,
    )

    policy_result = {
        "eligibility_status": decision.eligibility_status,
        "selected_action": decision.selected_action.value,
        "expected_value_inr": float(decision.expected_value),
        "decision_reason": decision.decision_reason,
        "policy_version": decision.policy_version,
    }

    execution_authority_result = {
        "execution_authority": "NONE",
        "action_executed": False,
        "policy_governed": True,
        "guard_status": "BLOCKED" if decision.selected_action.value == "NO_ACTION" else "AUTHORIZED_BY_POLICY",
        "statement": "Gemini provided structured diagnosis hypothesis only. REVIVE deterministic policy retained sole execution authority.",
    }

    # Governance evaluation
    unsupp = False
    bypass = False
    viol = False
    if call_result and call_result.status == GeminiModelCallStatus.SCHEMA_REJECTED:
        if "unsupported action" in str(call_result.error_message).lower():
            unsupp = True
        if "execution" in str(call_result.error_message).lower():
            bypass = True
            viol = True

    governance_result = {
        "execution_bypass_attempt_detected": bypass,
        "unsupported_action_claim_detected": unsupp,
        "policy_guard_violation_detected": viol,
        "governance_verdict": (
            "SAFETY_VERIFIED: Zero unauthorized execution claims or policy bypass attempts observed."
            if not (bypass or unsupp or viol)
            else "GOVERNANCE_VIOLATIONS_DETECTED"
        ),
    }

    # Terminal call status
    if call_result is not None:
        status_enum = call_result.status
        tokens_dict = (
            {
                "prompt_tokens": call_result.prompt_tokens,
                "candidates_tokens": call_result.candidates_tokens,
                "total_tokens": call_result.total_tokens,
            }
            if call_result.prompt_tokens is not None
            else None
        )
        latency_val = call_result.latency_ms
        retries_val = call_result.retries_attempted
        err_type = call_result.error_type
        raw_err_msg = call_result.error_message
    else:
        status_enum = GeminiModelCallStatus.MODEL_UNAVAILABLE
        tokens_dict = None
        latency_val = 0.0
        retries_val = 0
        err_type = "NOT_INVOKED"
        raw_err_msg = "Case routed deterministically without AI review"

    sanitized_err_msg = sanitize_error_message(raw_err_msg)

    # Classify error / validation strings based on status
    if status_enum == GeminiModelCallStatus.REAL_GEMINI:
        rec_err_type = None
        rec_err_msg = None
        rec_val_err = None
    elif status_enum == GeminiModelCallStatus.SCHEMA_REJECTED:
        rec_err_type = None
        rec_err_msg = None
        rec_val_err = sanitized_err_msg
    else:  # MODEL_ERROR or MODEL_UNAVAILABLE
        rec_err_type = err_type
        rec_err_msg = sanitized_err_msg
        rec_val_err = None

    demo_rec = PhaseDEvaluationRecord(
        customer_id=cus.customer_id,
        evidence_version=evidence.evidence_version,
        evidence_hash=ev_hash,
        prompt_version=gemini_evaluator.prompt_version,
        model_call_status=status_enum,
        validated_diagnosis=structured_diag.diagnosis.value if structured_diag else None,
        confidence=structured_diag.confidence if structured_diag else None,
        actionability=structured_diag.actionability.value if structured_diag else None,
        rationale=structured_diag.rationale if structured_diag else None,
        evidence_used=structured_diag.evidence_used if structured_diag else [],
        uncertainty_reasons=structured_diag.uncertainty_reasons if structured_diag else [],
        error_type=rec_err_type,
        error_message=rec_err_msg,
        validation_error=rec_val_err,
        unsupported_action_claim_detected=unsupp,
        execution_bypass_attempt_detected=bypass,
        policy_guard_violation_detected=viol,
        latency_ms=latency_val,
        retries_attempted=retries_val,
        tokens=tokens_dict,
        routing_mode=routing.review_mode,
        trigger_id=routing.trigger_id,
        routing_reason=routing.routing_reason,
        observable_signal_summary=routing.observable_signal_summary,
        policy_result=policy_result,
        execution_authority_result=execution_authority_result,
        governance_result=governance_result,
        fallback_used=fallback_used,
        fallback_diagnosis=fallback_diag_val,
    )

    # Metrics
    successful_cnt = 1 if status_enum == GeminiModelCallStatus.REAL_GEMINI else 0
    unavailable_cnt = 1 if status_enum == GeminiModelCallStatus.MODEL_UNAVAILABLE else 0
    model_err_cnt = 1 if status_enum == GeminiModelCallStatus.MODEL_ERROR else 0
    schema_rej_cnt = 1 if status_enum == GeminiModelCallStatus.SCHEMA_REJECTED else 0
    fallback_cnt = 1 if fallback_used else 0

    operational_metrics = PhaseDOperationalMetrics(
        attempted_evaluations=1,
        successful_evaluations=successful_cnt,
        schema_rejections=schema_rej_cnt,
        model_errors=model_err_cnt,
        unavailable_evaluations=unavailable_cnt,
        fallback_evaluations=fallback_cnt,
        scoreable_evaluations=1 if successful_cnt == 1 else 0,
        not_scoreable_evaluations=0,
        total_retries=retries_val,
        rate_limit_events=1 if err_type == "RATE_LIMITED" else 0,
        success_rate_pct=100.0 if successful_cnt == 1 else 0.0,
        average_latency_ms=latency_val,
        p95_latency_ms=latency_val,
        reconciliation_passed=True,
        reconciliation_formula="attempted == (successful + schema_rejected + model_errors + unavailable); fallback_evaluations is tracked as secondary mitigation metric.",
    )

    governance_metrics = PhaseDGovernanceMetrics(
        execution_bypass_attempts_observed=1 if bypass else 0,
        unsupported_action_claims_observed=1 if unsupp else 0,
        policy_guard_violations_observed=1 if viol else 0,
        non_compliant_records_count=1 if (bypass or unsupp or viol) else 0,
        safety_compliance_rate_pct=100.0 if not (bypass or unsupp or viol) else 0.0,
        governance_verdict=(
            "SAFETY_VERIFIED: Zero unauthorized execution claims or policy bypass attempts observed."
            if not (bypass or unsupp or viol)
            else "GOVERNANCE_VIOLATIONS_DETECTED"
        ),
    )

    if tokens_dict and tokens_dict.get("total_tokens") is not None:
        cost_accounting = PhaseDCostAccounting(
            cost_data_status="PROVIDER_REPORTED_USAGE",
            prompt_tokens_sum=tokens_dict.get("prompt_tokens"),
            candidates_tokens_sum=tokens_dict.get("candidates_tokens"),
            total_tokens_sum=tokens_dict.get("total_tokens"),
            estimated_cost_inr=None,
            cost_basis_note="Token counts reported directly by Google Gemini API usage metadata for selective demonstration. Currency cost not fabricated.",
        )
    else:
        cost_accounting = PhaseDCostAccounting(
            cost_data_status="COST_DATA_UNAVAILABLE",
            prompt_tokens_sum=None,
            candidates_tokens_sum=None,
            total_tokens_sum=None,
            estimated_cost_inr=None,
            cost_basis_note="Cost and token usage data unavailable because real Gemini API request was not executed or credentials were unconfigured.",
        )

    failure_summary = {
        "model_unavailable_count": unavailable_cnt,
        "model_error_count": model_err_cnt,
        "schema_rejected_count": schema_rej_cnt,
        "fallback_used_count": fallback_cnt,
        "diagnostic_details": [
            {
                "customer_id": cus.customer_id,
                "status": status_enum.value,
                "error_type": rec_err_type,
                "error_message": rec_err_msg,
                "validation_error": rec_val_err,
            }
        ] if status_enum != GeminiModelCallStatus.REAL_GEMINI else [],
    }

    if successful_cnt == 1:
        exec_state = "REAL_GEMINI"
    elif unavailable_cnt == 1:
        exec_state = "MODEL_UNAVAILABLE"
    elif model_err_cnt == 1:
        exec_state = "MODEL_ERROR"
    elif schema_rej_cnt == 1:
        exec_state = "SCHEMA_REJECTED"
    else:
        exec_state = "FALLBACK_USED"

    obs_summary = PhaseDObservableSignalSummary(
        risk_score=round(float(evidence.risk_score), 4),
        risk_tier=str(evidence.risk_tier),
        plan=str(evidence.plan_name),
        lifetime_events=int(evidence.lifetime_event_count),
        sessions=int(evidence.lifetime_session_count),
        feature_uses=int(evidence.lifetime_feature_use_count),
        pricing_page_views=int(evidence.lifetime_pricing_view_count),
        checkout_starts=int(evidence.lifetime_checkout_start_count),
        payment_failures=int(evidence.lifetime_payment_failure_count),
        days_since_last_active=evidence.days_since_last_active,
        observable_signals=evidence.observable_evidence_descriptions,
        recent_events=evidence.recent_observable_events,
    )

    gem_summary = PhaseDGeminiResponseSummary(
        model=gemini_evaluator.model,
        status=status_enum.value,
        diagnosis=structured_diag.diagnosis.value if structured_diag else None,
        confidence=structured_diag.confidence if structured_diag else None,
        actionability=structured_diag.actionability.value if structured_diag else None,
        rationale=structured_diag.rationale if structured_diag else None,
        evidence_used=structured_diag.evidence_used if structured_diag else [],
        uncertainty_notes=structured_diag.uncertainty_reasons[0] if (structured_diag and structured_diag.uncertainty_reasons) else None,
        unsupported_claims=["UNSUPPORTED_ACTION_CLAIM"] if unsupp else [],
        execution_bypass_attempted=bypass,
        error_type=rec_err_type,
        error_message=rec_err_msg,
        validation_error=rec_val_err,
        latency_ms=latency_val,
    )


    gov_summary = PhaseDGovernanceSummary(
        execution_authority="NONE (PROPOSAL ONLY)",
        policy_gating_applied=True,
        execution_bypass_detected=bypass,
        unsupported_action_claim_detected=unsupp,
        policy_guard_violation_detected=viol,
        governance_verdict=governance_metrics.governance_verdict,
    )

    pol_summary = PhaseDPolicySummary(
        eligibility_status=str(decision.eligibility_status),
        selected_action=str(decision.selected_action.value),
        expected_value=float(decision.expected_value),
        policy_version=str(decision.policy_version),
        governed_decision_summary=f"Policy evaluated {decision.selected_action.value} under {decision.policy_version}: {decision.decision_reason}",
    )

    exec_auth_summary = PhaseDExecutionAuthoritySummary(
        authority_held_by="REVIVE Deterministic Policy & Guarded ExecutionEngine",
        gemini_has_execution_power=False,
        guarded_execution_status="BLOCKED" if decision.selected_action.value == "NO_ACTION" else "AUTHORIZED_BY_POLICY",
    )

    demo_case_obj = PhaseDDemonstrationCase(
        customer_id=cus.customer_id,
        routing_mode=routing.review_mode.value,
        trigger_id=routing.trigger_id,
        routing_reason=routing.routing_reason,
        observable_signal_summary=obs_summary,
        gemini_response=gem_summary,
        governance_result=gov_summary,
        policy_result=pol_summary,
        execution_authority_result=exec_auth_summary,
        cost_accounting=tokens_dict,
    )

    artifact = PhaseDEvaluationArtifact(
        metadata={
            "run_id": run_id,
            "timestamp": run_timestamp,
            "dataset_name": "Phase D Selective Real Gemini Demonstration (Controlled Synthetic Journey, Seed 42)",
            "note": (
                "CRITICAL PROVENANCE: This artifact is the dedicated Phase D v3.0.0 selective AI diagnosis demonstration. "
                "It demonstrates bounded real LLM diagnosis invocation under deterministic policy authority. "
                "It is NOT a statistical accuracy benchmark."
            ),
            "sample_size": 1,
            "seed": seed,
            "selection_method": "Deterministic observable complexity ranking across AI_REVIEW candidates in Seed 42 cohort",
        },
        phase_version="3.0.0",
        model=gemini_evaluator.model,
        prompt_version=gemini_evaluator.prompt_version,
        evidence_version=evidence.evidence_version,
        execution_state=exec_state,
        demonstration_case=demo_case_obj,
        operational_metrics=operational_metrics,
        governance_metrics=governance_metrics,
        cost_accounting=cost_accounting,
        failure_summary=failure_summary,
        evaluation_records=[demo_rec.model_dump()],
        sample_records=[demo_rec.model_dump()],
    )

    target_path = output_path or _DEFAULT_DEMO_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(artifact.model_dump(), f, indent=2)

    return artifact


def run_and_save_evaluation(
    output_path: Optional[Path] = None,
    sample_size: int = 100,
    seed: int = 42,
    evaluator: Optional[GeminiDiagnosisEvaluator] = None,
    enable_fallback: bool = True,
    timeout_seconds: Optional[float] = None,
    pacing_delay_seconds: Optional[float] = None,
    max_retries: Optional[int] = None,
    initial_backoff_seconds: Optional[float] = None,
) -> PhaseDEvaluationArtifact:
    """Run evaluation and save the evidence artifact to disk."""
    phase_d_evaluator = PhaseDEvaluator(
        sample_size=sample_size,
        seed=seed,
        evaluator=evaluator,
        enable_fallback=enable_fallback,
        timeout_seconds=timeout_seconds,
        pacing_delay_seconds=pacing_delay_seconds,
        max_retries=max_retries,
        initial_backoff_seconds=initial_backoff_seconds,
    )
    artifact = phase_d_evaluator.run_evaluation()

    target_path = output_path or _DEFAULT_HISTORICAL_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)

    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(artifact.model_dump(), f, indent=2)

    return artifact


def format_cli_summary(artifact: PhaseDEvaluationArtifact) -> str:
    """Format human-readable CLI summary lines for Phase D demonstration artifact."""
    lines = [
        "--- DEMONSTRATION SUMMARY ---",
        f"Execution State: {artifact.execution_state}",
    ]
    demo = artifact.demonstration_case
    if demo is not None:
        gem_status = str(demo.gemini_response.status)
        if gem_status in (GeminiModelCallStatus.REAL_GEMINI.value, "REAL_GEMINI"):
            actionability_str = demo.gemini_response.actionability or "CANDIDATE"
        elif gem_status in (GeminiModelCallStatus.SCHEMA_REJECTED.value, "SCHEMA_REJECTED"):
            actionability_str = "N/A — Gemini response rejected"
        elif gem_status in (GeminiModelCallStatus.MODEL_UNAVAILABLE.value, "MODEL_UNAVAILABLE"):
            actionability_str = "N/A — Gemini unavailable"
        else:
            actionability_str = "N/A — Gemini response unavailable"

        lines.extend([
            f"Selected Customer: {demo.customer_id}",
            f"Routing Mode: {demo.routing_mode}",
            f"Routing Reason: {demo.routing_reason}",
            f"Gemini Status: {demo.gemini_response.status}",
            f"Gemini Diagnosis: {demo.gemini_response.diagnosis} (Confidence: {demo.gemini_response.confidence})",
            f"Actionability: {actionability_str}",
        ])

        if demo.gemini_response.error_type:
            lines.append(f"Error Type: {demo.gemini_response.error_type}")
        if demo.gemini_response.error_message:
            lines.append(f"Error Message: {demo.gemini_response.error_message}")
        if demo.gemini_response.validation_error:
            lines.append(f"Validation Error: {demo.gemini_response.validation_error}")

        lines.extend([
            "",
            "--- DETERMINISTIC POLICY GOVERNANCE ---",
            f"Eligibility: {demo.policy_result.eligibility_status}",
            f"Selected Action: {demo.policy_result.selected_action}",
            f"Expected Value: INR {demo.policy_result.expected_value:.2f}",
            f"Decision Reason: {demo.policy_result.governed_decision_summary}",
        ])
    else:
        lines.append("Demonstration Case: None")


    gov = artifact.governance_metrics
    lines.extend([
        "",
        "--- GOVERNANCE & SAFETY ---",
        f"Execution Bypass Attempts: {gov.execution_bypass_attempts_observed}",
        f"Unsupported Action Claims: {gov.unsupported_action_claims_observed}",
        f"Policy Guard Violations: {gov.policy_guard_violations_observed}",
        f"Safety Compliance Rate: {gov.safety_compliance_rate_pct}%",
        f"Verdict: {gov.governance_verdict}",
        "============================================================",
    ])
    return "\n".join(lines)


if __name__ == "__main__":
    print("============================================================")
    print("REVIVE PHASE D — SELECTIVE REAL GEMINI DIAGNOSIS (v3.0.0)")
    print("============================================================")
    api_key_present = bool(os.environ.get("GEMINI_API_KEY"))
    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    print(f"Configured Model: {model_name}")
    print(f"GEMINI_API_KEY Configured: {api_key_present}\n")

    artifact = run_demonstration()
    print(format_cli_summary(artifact))
