"""
Deterministic Eligibility Layer for Revive Phase 5 Intervention Decision Engine.
Evaluates terminal non-intervention states, human review escalation, and intervention cooldowns.
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from app.diagnosis.schemas import Actionability, CustomerDiagnosis, DiagnosisCategory
from app.risk.scoring import ScoredCustomer
from app.intervention.config import InterventionConfig
from app.intervention.schemas import InterventionAction


class EligibilityEngine:
    """Evaluates customer eligibility for Phase 5 intervention selection."""

    def __init__(self, config: InterventionConfig) -> None:
        self.config = config

    def check_eligibility(
        self,
        scored_customer: ScoredCustomer,
        diagnosis: CustomerDiagnosis,
        intervention_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[str, Optional[InterventionAction], Optional[str]]:
        """
        Evaluate customer eligibility.
        Returns Tuple[eligibility_status, forced_action, reason]:
        - eligibility_status: 'INELIGIBLE', 'ESCALATED', 'COOLDOWN', or 'ELIGIBLE'
        - forced_action: InterventionAction if non-eligible/escalated, or None if ELIGIBLE
        - reason: Human-readable explanation string
        """
        # 1. Terminal Non-Intervention Gate: Low Risk
        if scored_customer.risk_score < self.config.min_risk_eligibility_threshold:
            return (
                "INELIGIBLE",
                InterventionAction.NO_ACTION,
                f"Customer risk score ({scored_customer.risk_score:.2f}) below eligibility threshold ({self.config.min_risk_eligibility_threshold:.2f})",
            )

        # 2. Terminal Non-Intervention Gate: Already Converted
        if diagnosis.diagnosis == DiagnosisCategory.ALREADY_CONVERTED:
            return (
                "INELIGIBLE",
                InterventionAction.NO_ACTION,
                "Customer has already converted prior to prediction snapshot",
            )

        # 3. Terminal Non-Intervention Gate: Insufficient Evidence
        if diagnosis.diagnosis == DiagnosisCategory.INSUFFICIENT_EVIDENCE:
            return (
                "INELIGIBLE",
                InterventionAction.NO_ACTION,
                "Insufficient observable evidence at Tprediction to ground a specific root cause",
            )

        # 4. Terminal Non-Intervention Gate: Non-Actionable Diagnosis
        if diagnosis.actionability == Actionability.NONE:
            return (
                "INELIGIBLE",
                InterventionAction.NO_ACTION,
                "Customer diagnosis actionability is NONE",
            )

        # 5. Escalation Gate: Human Review
        # Requirement: High revenue at risk ALONE must NOT trigger human review.
        # Escalate ONLY when high revenue at risk (>= Rs. 2,500) is combined with ambiguity or review status.
        is_high_value = scored_customer.revenue_at_risk >= self.config.human_review_revenue_threshold
        is_ambiguous_or_review = (
            diagnosis.diagnosis == DiagnosisCategory.MIXED_SIGNALS
            or diagnosis.actionability == Actionability.REQUIRES_REVIEW
        )
        if is_high_value and is_ambiguous_or_review:
            return (
                "ESCALATED",
                InterventionAction.HUMAN_REVIEW,
                f"High revenue at risk (Rs. {scored_customer.revenue_at_risk}) combined with diagnostic ambiguity requires human review",
            )

        # 6. Cooldown Interface Gate
        if intervention_history:
            for record in intervention_history:
                hours_since = record.get("hours_since_last_intervention", 999.0)
                if hours_since < self.config.cooldown_period_hours:
                    return (
                        "COOLDOWN",
                        InterventionAction.NO_ACTION,
                        f"Active intervention cooldown period ({hours_since:.1f}h < {self.config.cooldown_period_hours:.1f}h) in effect",
                    )

        # 7. Customer is fully ELIGIBLE for candidate action evaluation
        return ("ELIGIBLE", None, None)
