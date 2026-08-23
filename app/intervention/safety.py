"""
Safety & Contraindications Filter for Revive Phase 5 Intervention Decision Engine.
Enforces hard safety rules (S1-S5) to prevent inappropriate or harmful customer interventions.
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from app.diagnosis.schemas import CustomerDiagnosis, DiagnosisCategory, EvidenceCategory
from app.intervention.config import InterventionConfig
from app.intervention.schemas import InterventionAction


class SafetyChecker:
    """Enforces safety rules S1-S5 against candidate intervention actions."""

    def __init__(self, config: InterventionConfig) -> None:
        self.config = config

    def is_action_safe(
        self,
        action: InterventionAction,
        diagnosis: CustomerDiagnosis,
        feature_record: Dict[str, Any],
        expected_value: Decimal,
    ) -> Tuple[bool, Optional[str]]:
        """
        Check whether candidate action satisfies safety contraindication rules.
        Returns Tuple[is_safe, disqualification_reason]:
        - is_safe: True if action is allowed
        - disqualification_reason: String explaining safety violation if not allowed
        """
        # NO_ACTION is always safe
        if action == InterventionAction.NO_ACTION:
            return (True, None)

        # HUMAN_REVIEW is always safe
        if action == InterventionAction.HUMAN_REVIEW:
            return (True, None)

        ev_types = {ev.evidence_type for ev in diagnosis.supporting_evidence}

        # Rule S1: No Double Conversion (Never intervene for ALREADY_CONVERTED)
        if diagnosis.diagnosis == DiagnosisCategory.ALREADY_CONVERTED:
            return (False, "Rule S1 Violation: Cannot perform active intervention for ALREADY_CONVERTED customer")

        # Rule S2: Payment Evidence Required for PAYMENT_RECOVERY
        if action == InterventionAction.PAYMENT_RECOVERY:
            has_pay_ev = (
                EvidenceCategory.PAYMENT_FAILURE in ev_types
                or EvidenceCategory.PAYMENT_ATTEMPT in ev_types
            )
            if not has_pay_ev:
                return (False, "Rule S2 Violation: PAYMENT_RECOVERY requires observable payment failure or attempt evidence")

        # Rule S3: Checkout Evidence Required for CHECKOUT_ASSISTANCE
        if action == InterventionAction.CHECKOUT_ASSISTANCE:
            has_chk_ev = EvidenceCategory.CHECKOUT_STARTED in ev_types
            if not has_chk_ev:
                return (False, "Rule S3 Violation: CHECKOUT_ASSISTANCE requires observable checkout started evidence")

        # Rule S4: Trial Expiry Timing Required for TRIAL_EXTENSION
        if action == InterventionAction.TRIAL_EXTENSION:
            hours_until_exp = feature_record.get("hours_until_trial_expiry", 999.0)
            if hours_until_exp > self.config.max_trial_extension_hours_until_expiry:
                return (
                    False,
                    f"Rule S4 Violation: TRIAL_EXTENSION forbidden when trial expiry is > {self.config.max_trial_extension_hours_until_expiry}h away (current: {hours_until_exp:.1f}h)",
                )

        # Rule S5: Positive Net Expected Value Required
        if expected_value <= Decimal("0.00"):
            return (False, f"Rule S5 Violation: Net Expected Value (Rs. {expected_value}) is non-positive")

        return (True, None)
