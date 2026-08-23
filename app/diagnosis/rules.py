"""
Deterministic Candidate Cause Scoring Rules for Revive Diagnosis Engine (Phase 4).
Evaluates structured evidence items against candidate root causes.
"""

from typing import Dict, List, Tuple
from app.diagnosis.config import DiagnosisConfig, DEFAULT_DIAGNOSIS_CONFIG
from app.diagnosis.schemas import CandidateCauseScore, DiagnosisCategory, EvidenceCategory, EvidenceItem


class CandidateCauseScorer:
    """Computes deterministic candidate cause scores based on observable evidence."""

    def __init__(self, config: DiagnosisConfig = DEFAULT_DIAGNOSIS_CONFIG) -> None:
        self.config = config

    def score_candidates(
        self,
        evidence_items: List[EvidenceItem],
        feature_record: Dict[str, float],
    ) -> List[CandidateCauseScore]:
        """
        Score candidate root causes:
        PAYMENT_FRICTION, CHECKOUT_ABANDONMENT, TRIAL_EXPIRATION, ENGAGEMENT_DECLINE, LOW_INTENT.
        Returns ordered list of CandidateCauseScore objects.
        """
        evidence_map = {item.evidence_type: item for item in evidence_items}

        candidates: List[CandidateCauseScore] = []

        # 1. PAYMENT_FRICTION
        candidates.append(self._score_payment_friction(evidence_items, evidence_map, feature_record))

        # 2. CHECKOUT_ABANDONMENT
        candidates.append(self._score_checkout_abandonment(evidence_items, evidence_map, feature_record))

        # 3. TRIAL_EXPIRATION
        candidates.append(self._score_trial_expiration(evidence_items, evidence_map, feature_record))

        # 4. ENGAGEMENT_DECLINE
        candidates.append(self._score_engagement_decline(evidence_items, evidence_map, feature_record))

        # 5. LOW_INTENT
        candidates.append(self._score_low_intent(evidence_items, evidence_map, feature_record))

        # Sort descending by score
        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates

    def _score_payment_friction(
        self,
        items: List[EvidenceItem],
        ev_map: Dict[EvidenceCategory, EvidenceItem],
        feat: Dict[str, float],
    ) -> CandidateCauseScore:
        """
        PAYMENT_FRICTION requires genuine payment-flow failure evidence: specifically PAYMENT_FAILURE.
        Generic checkout activity alone MUST NOT create payment friction.
        """
        score_sum = 0.0
        supporting = 0
        contradictory = 0

        payment_failures = sum(1 for it in items if it.evidence_type == EvidenceCategory.PAYMENT_FAILURE)
        if payment_failures > 0:
            score_sum += min(1.00, payment_failures * self.config.strong_weight)
            supporting += payment_failures
        else:
            return CandidateCauseScore(
                cause=DiagnosisCategory.PAYMENT_FRICTION,
                score=0.0,
                supporting_count=0,
                contradictory_count=0,
            )

        if EvidenceCategory.CONVERSION_STATE in ev_map or EvidenceCategory.PAYMENT_SUCCESS in ev_map:
            score_sum -= 0.80
            contradictory += 1

        final_score = max(0.0, min(1.0, score_sum / 1.00))
        return CandidateCauseScore(
            cause=DiagnosisCategory.PAYMENT_FRICTION,
            score=final_score,
            supporting_count=supporting,
            contradictory_count=contradictory,
        )

    def _score_checkout_abandonment(
        self,
        items: List[EvidenceItem],
        ev_map: Dict[EvidenceCategory, EvidenceItem],
        feat: Dict[str, float],
    ) -> CandidateCauseScore:
        """
        CHECKOUT_ABANDONMENT represents checkout_started followed by non-completion
        when payment failure is not the primary observable explanation.
        """
        score_sum = 0.0
        supporting = 0
        contradictory = 0

        if EvidenceCategory.PAYMENT_FAILURE in ev_map:
            # Payment failure takes precedence
            return CandidateCauseScore(
                cause=DiagnosisCategory.CHECKOUT_ABANDONMENT,
                score=0.0,
                supporting_count=0,
                contradictory_count=1,
            )

        if EvidenceCategory.CHECKOUT_ABANDONED in ev_map or EvidenceCategory.CHECKOUT_STARTED in ev_map:
            score_sum += 1.00
            supporting += 1

        if EvidenceCategory.PAYMENT_METHOD_ADDED in ev_map or EvidenceCategory.PAYMENT_ATTEMPT in ev_map:
            score_sum += 0.20
            supporting += 1

        if EvidenceCategory.CHECKOUT_COMPLETED in ev_map or EvidenceCategory.CONVERSION_STATE in ev_map:
            score_sum -= 0.80
            contradictory += 1

        final_score = max(0.0, min(1.0, score_sum / 1.20))
        return CandidateCauseScore(
            cause=DiagnosisCategory.CHECKOUT_ABANDONMENT,
            score=final_score,
            supporting_count=supporting,
            contradictory_count=contradictory,
        )

    def _score_trial_expiration(
        self,
        items: List[EvidenceItem],
        ev_map: Dict[EvidenceCategory, EvidenceItem],
        feat: Dict[str, float],
    ) -> CandidateCauseScore:
        """
        TRIAL_EXPIRATION requires genuine trial-expiry proximity evidence (<=24h remaining).
        Do not diagnose it simply because a customer is at risk.
        """
        score_sum = 0.0
        supporting = 0
        contradictory = 0

        hours_expiry = feat.get("hours_until_trial_expiry", 999.0)
        expiring_soon = feat.get("trial_expiring_soon", 0)

        if EvidenceCategory.TRIAL_EXPIRY_PROXIMITY in ev_map or hours_expiry <= 24.0 or expiring_soon == 1:
            score_sum += 1.00
            supporting += 1
        else:
            return CandidateCauseScore(
                cause=DiagnosisCategory.TRIAL_EXPIRATION,
                score=0.0,
                supporting_count=0,
                contradictory_count=0,
            )

        if EvidenceCategory.PAYMENT_FAILURE in ev_map or EvidenceCategory.CHECKOUT_ABANDONED in ev_map:
            score_sum -= 0.30
            contradictory += 1

        if EvidenceCategory.CONVERSION_STATE in ev_map:
            score_sum -= 0.80
            contradictory += 1

        final_score = max(0.0, min(1.0, score_sum / 1.00))
        return CandidateCauseScore(
            cause=DiagnosisCategory.TRIAL_EXPIRATION,
            score=final_score,
            supporting_count=supporting,
            contradictory_count=contradictory,
        )

    def _score_engagement_decline(
        self,
        items: List[EvidenceItem],
        ev_map: Dict[EvidenceCategory, EvidenceItem],
        feat: Dict[str, float],
    ) -> CandidateCauseScore:
        """
        ENGAGEMENT_DECLINE requires evidence of prior meaningful engagement
        followed by a significant recent decline/inactivity (>=48h gap). Keep distinct from LOW_INTENT.
        """
        score_sum = 0.0
        supporting = 0
        contradictory = 0

        sessions = feat.get("session_count", 0)
        feature_uses = feat.get("feature_use_count", 0)
        hours_since_activity = feat.get("hours_since_last_activity", 0.0)

        has_prior_engagement = (sessions >= 3 or feature_uses >= 3) or (
            EvidenceCategory.SESSION_ACTIVITY in ev_map and ev_map[EvidenceCategory.SESSION_ACTIVITY].strength >= 0.60
        )

        if has_prior_engagement and (hours_since_activity >= 48.0 or EvidenceCategory.RECENCY_DECLINE in ev_map):
            score_sum += 1.00
            supporting += 1
        else:
            return CandidateCauseScore(
                cause=DiagnosisCategory.ENGAGEMENT_DECLINE,
                score=0.0,
                supporting_count=0,
                contradictory_count=0,
            )

        if hours_since_activity < 24.0:
            score_sum -= 0.80
            contradictory += 1

        final_score = max(0.0, min(1.0, score_sum / 1.00))
        return CandidateCauseScore(
            cause=DiagnosisCategory.ENGAGEMENT_DECLINE,
            score=final_score,
            supporting_count=supporting,
            contradictory_count=contradictory,
        )

    def _score_low_intent(
        self,
        items: List[EvidenceItem],
        ev_map: Dict[EvidenceCategory, EvidenceItem],
        feat: Dict[str, float],
    ) -> CandidateCauseScore:
        """
        LOW_INTENT requires positive observable evidence of low usage/disengagement.
        MUST NEVER be inferred merely from absence of checkout/payment events.
        """
        score_sum = 0.0
        supporting = 0
        contradictory = 0

        sessions = feat.get("session_count", 0)
        feature_uses = feat.get("feature_use_count", 0)
        pricing_views = feat.get("pricing_view_count", 0)
        hours_since_activity = feat.get("hours_since_last_activity", 0.0)

        # Positive low usage/disengagement evidence
        if sessions <= 2 and feature_uses <= 2 and hours_since_activity >= 24.0:
            score_sum += 0.80
            supporting += 1

        if sessions <= 1:
            score_sum += 0.40
            supporting += 1

        if pricing_views == 0 and sessions <= 2:
            score_sum += 0.20
            supporting += 1

        # Contradicted by active usage (sessions >= 3 or feature_uses >= 3)
        if sessions >= 3 or feature_uses >= 3:
            score_sum -= 0.80
            contradictory += 1

        # Contradicted by checkout or payment attempts
        if EvidenceCategory.CHECKOUT_STARTED in ev_map or EvidenceCategory.PAYMENT_METHOD_ADDED in ev_map or EvidenceCategory.PAYMENT_FAILURE in ev_map:
            score_sum -= 0.80
            contradictory += 1

        final_score = max(0.0, min(1.0, score_sum / 1.20))
        return CandidateCauseScore(
            cause=DiagnosisCategory.LOW_INTENT,
            score=final_score,
            supporting_count=supporting,
            contradictory_count=contradictory,
        )
