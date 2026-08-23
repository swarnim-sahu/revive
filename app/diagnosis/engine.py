"""
Main Root-Cause Diagnosis Engine for Revive (Phase 4).
Consumes Phase 3 risk output and observable customer journey events to produce
evidence-grounded diagnoses, candidate cause scores, diagnostic confidence, and actionability states.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from app.models.entities import Customer, Plan
from app.models.events import BaseEvent
from app.risk.scoring import ScoredCustomer
from app.diagnosis.config import DiagnosisConfig, DEFAULT_DIAGNOSIS_CONFIG
from app.diagnosis.evidence import EvidenceExtractor
from app.diagnosis.explanations import DiagnosisExplainer
from app.diagnosis.rules import CandidateCauseScorer
from app.diagnosis.schemas import (
    Actionability,
    CandidateCauseScore,
    ConfidenceTier,
    CustomerDiagnosis,
    DiagnosisCategory,
    EvidenceCategory,
    EvidenceItem,
)


def determine_confidence_tier(confidence: float, config: DiagnosisConfig) -> ConfidenceTier:
    """Categorize diagnostic confidence into operational confidence tiers."""
    if confidence < config.confidence_medium_threshold:
        return ConfidenceTier.LOW
    elif confidence < config.confidence_high_threshold:
        return ConfidenceTier.MEDIUM
    elif confidence < config.confidence_very_high_threshold:
        return ConfidenceTier.HIGH
    else:
        return ConfidenceTier.VERY_HIGH


class DiagnosisEngine:
    """Core deterministic root-cause diagnosis engine."""

    def __init__(self, config: DiagnosisConfig = DEFAULT_DIAGNOSIS_CONFIG) -> None:
        self.config = config
        self.evidence_extractor = EvidenceExtractor(config=config)
        self.candidate_scorer = CandidateCauseScorer(config=config)

    def diagnose_customer(
        self,
        scored_customer: ScoredCustomer,
        customer: Customer,
        events: List[BaseEvent],
        plan: Plan,
        feature_record: Dict[str, Any],
    ) -> CustomerDiagnosis:
        """
        Produce evidence-grounded root-cause diagnosis for a customer.
        Reuses Phase 3 prediction timestamp and enforces terminal eligibility states.
        """
        prediction_dt = datetime.fromisoformat(scored_customer.prediction_timestamp)

        # 1. TERMINAL STATE: Check if ALREADY_CONVERTED before prediction snapshot
        valid_events = [e for e in events if e.timestamp <= prediction_dt]
        conversion_events = [
            e for e in valid_events
            if e.event_type.value in {"subscription_created", "payment_succeeded"}
        ]
        if conversion_events:
            evidence_items = self.evidence_extractor.extract_evidence(customer, events, plan, prediction_dt)
            expl = DiagnosisExplainer.generate_explanation(
                DiagnosisCategory.ALREADY_CONVERTED, 1.0, ConfidenceTier.VERY_HIGH, evidence_items
            )
            return CustomerDiagnosis(
                customer_id=scored_customer.customer_id,
                prediction_timestamp=scored_customer.prediction_timestamp,
                risk_score=scored_customer.risk_score,
                risk_tier=scored_customer.risk_tier,
                diagnosis=DiagnosisCategory.ALREADY_CONVERTED,
                confidence=1.0,
                confidence_tier=ConfidenceTier.VERY_HIGH,
                actionability=Actionability.NONE,
                candidate_causes=[],
                supporting_evidence=evidence_items,
                explanation=expl,
            )

        # 2. TERMINAL STATE: Check if NO_MEANINGFUL_RISK (risk_score < 0.30)
        if scored_customer.risk_score < self.config.risk_eligibility_threshold:
            evidence_items = self.evidence_extractor.extract_evidence(customer, events, plan, prediction_dt)
            expl = DiagnosisExplainer.generate_explanation(
                DiagnosisCategory.NO_MEANINGFUL_RISK, 1.0, ConfidenceTier.VERY_HIGH, evidence_items
            )
            return CustomerDiagnosis(
                customer_id=scored_customer.customer_id,
                prediction_timestamp=scored_customer.prediction_timestamp,
                risk_score=scored_customer.risk_score,
                risk_tier=scored_customer.risk_tier,
                diagnosis=DiagnosisCategory.NO_MEANINGFUL_RISK,
                confidence=1.0,
                confidence_tier=ConfidenceTier.VERY_HIGH,
                actionability=Actionability.NONE,
                candidate_causes=[],
                supporting_evidence=evidence_items,
                explanation=expl,
            )

        # 3. Extract observable evidence
        evidence_items = self.evidence_extractor.extract_evidence(customer, events, plan, prediction_dt)

        if not evidence_items:
            expl = DiagnosisExplainer.generate_explanation(
                DiagnosisCategory.INSUFFICIENT_EVIDENCE, 0.0, ConfidenceTier.LOW, []
            )
            return CustomerDiagnosis(
                customer_id=scored_customer.customer_id,
                prediction_timestamp=scored_customer.prediction_timestamp,
                risk_score=scored_customer.risk_score,
                risk_tier=scored_customer.risk_tier,
                diagnosis=DiagnosisCategory.INSUFFICIENT_EVIDENCE,
                confidence=0.0,
                confidence_tier=ConfidenceTier.LOW,
                actionability=Actionability.NONE,
                candidate_causes=[],
                supporting_evidence=[],
                explanation=expl,
            )

        # 4. Score Candidate Causes
        candidates = self.candidate_scorer.score_candidates(evidence_items, feature_record)
        top_cand = candidates[0]
        second_cand = candidates[1] if len(candidates) > 1 else None

        # 5. Determine Primary Diagnosis & Ambiguity / Evidence Threshold Checks
        if top_cand.score < self.config.min_evidence_threshold:
            diag = DiagnosisCategory.INSUFFICIENT_EVIDENCE
            confidence = float(top_cand.score)
            tier = ConfidenceTier.LOW
            actionability = Actionability.NONE
        elif second_cand and (top_cand.score - second_cand.score) < self.config.ambiguity_margin:
            diag = DiagnosisCategory.MIXED_SIGNALS
            confidence = float(top_cand.score)
            tier = determine_confidence_tier(confidence, self.config)
            actionability = Actionability.REQUIRES_REVIEW
        else:
            diag = top_cand.cause
            confidence = float(top_cand.score)
            tier = determine_confidence_tier(confidence, self.config)
            actionability = Actionability.CANDIDATE if tier != ConfidenceTier.LOW else Actionability.REQUIRES_REVIEW

        expl = DiagnosisExplainer.generate_explanation(diag, confidence, tier, evidence_items)

        return CustomerDiagnosis(
            customer_id=scored_customer.customer_id,
            prediction_timestamp=scored_customer.prediction_timestamp,
            risk_score=scored_customer.risk_score,
            risk_tier=scored_customer.risk_tier,
            diagnosis=diag,
            confidence=confidence,
            confidence_tier=tier,
            actionability=actionability,
            candidate_causes=candidates,
            supporting_evidence=evidence_items,
            explanation=expl,
        )
