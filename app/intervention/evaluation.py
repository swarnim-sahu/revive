"""
Offline Evaluation Engine for Revive Phase 5 Intervention Decision Engine.
Computes the specified 10-stage decision funnel, safety compliance across S1-S5, and structured evidence-action consistency.
"""

from collections import Counter
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set
from app.diagnosis.schemas import CustomerDiagnosis, EvidenceCategory
from app.intervention.schemas import InterventionAction, InterventionDecision


class InterventionEvaluator:
    """Evaluates Phase 5 intervention decisions and computes decision funnel metrics."""

    @classmethod
    def verify_evidence_action_consistency(
        cls,
        decision: InterventionDecision,
        diagnosis: Optional[CustomerDiagnosis] = None,
    ) -> bool:
        """
        Verify that active automated actions have appropriate structured evidence grounding.
        Requires a CustomerDiagnosis with structured EvidenceCategory values.
        """
        act = decision.selected_action

        if act in {InterventionAction.NO_ACTION, InterventionAction.HUMAN_REVIEW}:
            return True

        if not diagnosis or not diagnosis.supporting_evidence:
            return False

        ev_categories = {ev.evidence_type for ev in diagnosis.supporting_evidence}

        if act == InterventionAction.PAYMENT_RECOVERY:
            return (
                EvidenceCategory.PAYMENT_FAILURE in ev_categories
                or EvidenceCategory.PAYMENT_ATTEMPT in ev_categories
            )

        if act == InterventionAction.CHECKOUT_ASSISTANCE:
            # Strictly requires CHECKOUT_STARTED
            return EvidenceCategory.CHECKOUT_STARTED in ev_categories

        if act == InterventionAction.TRIAL_EXTENSION:
            return True

        if act == InterventionAction.PRODUCT_GUIDANCE:
            return bool(
                ev_categories.intersection(
                    {
                        EvidenceCategory.SESSION_ACTIVITY,
                        EvidenceCategory.FEATURE_USAGE,
                        EvidenceCategory.PRODUCT_ACTIVITY,
                        EvidenceCategory.RECENCY_DECLINE,
                    }
                )
            )

        if act == InterventionAction.REMINDER:
            return True

        return False

    @classmethod
    def verify_safety_compliance_single(
        cls,
        decision: InterventionDecision,
        diagnosis: Optional[CustomerDiagnosis] = None,
        feature_record: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Independently verify ALL S1-S5 safety rules against a single final InterventionDecision.
        """
        act = decision.selected_action

        if act == InterventionAction.NO_ACTION:
            return True

        # Rule S1: No Double Conversion (Converted customers must NEVER receive active intervention)
        if decision.diagnosis == "ALREADY_CONVERTED":
            return False

        if act == InterventionAction.HUMAN_REVIEW:
            return True

        # Extract evidence categories
        ev_categories: Set[EvidenceCategory] = set()
        if diagnosis and diagnosis.supporting_evidence:
            ev_categories = {ev.evidence_type for ev in diagnosis.supporting_evidence}
        else:
            ev_text = " ".join(decision.supporting_evidence)
            for cat in EvidenceCategory:
                if cat.value in ev_text or cat.name in ev_text:
                    ev_categories.add(cat)

        # Rule S2: Payment Evidence Required for PAYMENT_RECOVERY
        if act == InterventionAction.PAYMENT_RECOVERY:
            has_pay_ev = (
                EvidenceCategory.PAYMENT_FAILURE in ev_categories
                or EvidenceCategory.PAYMENT_ATTEMPT in ev_categories
            )
            if not has_pay_ev:
                return False

        # Rule S3: Checkout Evidence Required for CHECKOUT_ASSISTANCE (CHECKOUT_STARTED ONLY)
        if act == InterventionAction.CHECKOUT_ASSISTANCE:
            has_chk_ev = EvidenceCategory.CHECKOUT_STARTED in ev_categories
            if not has_chk_ev:
                return False

        # Rule S4: Trial Expiry Timing Required for TRIAL_EXTENSION (expiry <= 48h)
        if act == InterventionAction.TRIAL_EXTENSION:
            if feature_record:
                hours_until_exp = feature_record.get("hours_until_trial_expiry", 999.0)
                if hours_until_exp > 48.0:
                    return False

        # Rule S5: Net Expected Value must be positive (EV > 0)
        if decision.expected_value <= Decimal("0.00"):
            return False

        return True

    @classmethod
    def evaluate_decisions(
        cls,
        decisions: List[InterventionDecision],
        diagnoses_map: Optional[Dict[str, CustomerDiagnosis]] = None,
        feature_records_map: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Compute decision funnel and policy safety compliance metrics across all decisions.
        Independently verifies S1-S5 safety rules and structured evidence-action consistency.
        """
        total_pop = len(decisions)
        at_risk_pop = sum(1 for d in decisions if d.risk_score >= 0.30)
        diagnosable_pop = sum(1 for d in decisions if d.diagnosis_actionability == "candidate")
        eligible_pop = sum(1 for d in decisions if d.eligibility_status == "ELIGIBLE")

        no_action_count = sum(1 for d in decisions if d.selected_action == InterventionAction.NO_ACTION)
        human_review_count = sum(1 for d in decisions if d.selected_action == InterventionAction.HUMAN_REVIEW)
        automated_active_count = sum(
            1
            for d in decisions
            if d.selected_action not in {InterventionAction.NO_ACTION, InterventionAction.HUMAN_REVIEW}
        )

        per_action_counts = Counter(d.selected_action.value for d in decisions)
        per_action_dist = {
            act.value: {
                "count": per_action_counts[act.value],
                "rate": round(per_action_counts[act.value] / total_pop, 4) if total_pop > 0 else 0.0,
            }
            for act in InterventionAction
        }

        # Independent Safety Policy Compliance Verification (S1-S5)
        safe_count = 0
        for d in decisions:
            diag = diagnoses_map.get(d.customer_id) if diagnoses_map else None
            feat = feature_records_map.get(d.customer_id) if feature_records_map else None
            if cls.verify_safety_compliance_single(d, diagnosis=diag, feature_record=feat):
                safe_count += 1

        safety_compliance_rate = (
            round(safe_count / total_pop, 4) if total_pop > 0 else 1.0
        )

        # Structured Evidence-Action Consistency Verification
        consistent_count = 0
        for d in decisions:
            diag = diagnoses_map.get(d.customer_id) if diagnoses_map else None
            if cls.verify_evidence_action_consistency(d, diagnosis=diag):
                consistent_count += 1

        evidence_consistency_rate = (
            round(consistent_count / total_pop, 4) if total_pop > 0 else 1.0
        )

        return {
            # 10-Stage Decision Funnel
            "total_population": total_pop,
            "at_risk_population": at_risk_pop,
            "diagnosable_actionable_population": diagnosable_pop,
            "eligible_intervention_population": eligible_pop,
            "no_action_count": no_action_count,
            "no_action_rate": round(no_action_count / total_pop, 4) if total_pop > 0 else 0.0,
            "human_review_count": human_review_count,
            "human_review_rate": round(human_review_count / total_pop, 4) if total_pop > 0 else 0.0,
            "automated_intervention_count": automated_active_count,
            "automated_intervention_rate": round(automated_active_count / total_pop, 4) if total_pop > 0 else 0.0,
            "per_action_distribution": per_action_dist,
            "safety_policy_compliance_rate": safety_compliance_rate,
            "evidence_action_consistency_rate": evidence_consistency_rate,
        }
