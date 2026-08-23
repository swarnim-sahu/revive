"""
Input Validation Module for Revive Phase 5 Intervention Decision Engine.
Strictly verifies that no forbidden ground-truth fields or future events leak into runtime decision logic.
"""

from typing import Any, Dict
from app.risk.feature_registry import FORBIDDEN_GROUND_TRUTH_FIELDS
from app.risk.scoring import ScoredCustomer
from app.diagnosis.schemas import CustomerDiagnosis


class InputValidator:
    """Validates inputs to InterventionEngine to guarantee zero ground-truth leakage."""

    @staticmethod
    def validate_inputs(
        scored_customer: ScoredCustomer,
        diagnosis: CustomerDiagnosis,
        feature_record: Dict[str, Any],
    ) -> None:
        """
        Assert that zero forbidden ground-truth fields leak into feature records or diagnosis objects.
        Raises ValueError if ground-truth leakage is detected.
        """
        # Check feature record keys
        for forbidden in FORBIDDEN_GROUND_TRUTH_FIELDS:
            if forbidden in feature_record:
                raise ValueError(
                    f"Ground-truth leakage violation: Forbidden field '{forbidden}' found in feature_record during Phase 5 inference!"
                )

        # Ensure customer ID consistency
        if scored_customer.customer_id != diagnosis.customer_id:
            raise ValueError(
                f"Customer ID mismatch: scored_customer ({scored_customer.customer_id}) != diagnosis ({diagnosis.customer_id})"
            )
