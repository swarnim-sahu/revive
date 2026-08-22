"""
Hidden ground-truth models for Revive synthetic dataset evaluation.

Counterfactual Semantics:
- `natural_conversion`: Hidden counterfactual label indicating whether the customer
  WOULD HAVE converted WITHOUT any REVIVE intervention.
  It is a hidden counterfactual property and does NOT simply mean "The customer actually
  converted naturally in the observable pre-intervention journey".
- `conversion_after_intervention`: Hidden counterfactual label indicating whether the customer
  WOULD HAVE converted AFTER an appropriate successful REVIVE intervention.
- `recoverable`: True iff `conversion_after_intervention and not natural_conversion`.
  Indicates an incremental revenue recovery opportunity.
- `maximum_recoverable_revenue`: If `recoverable` is True, equals selected plan price.
  If `recoverable` is False, equals Decimal("0.00").
- `true_root_cause`: The true underlying root cause for risk assessment evaluation.
"""

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator, ValidationInfo

from app.models.entities import _validate_non_empty_string, _validate_non_negative_decimal


class GroundTruthRecord(BaseModel):
    """
    Hidden evaluation ground-truth record for a synthetic customer journey.
    Ground-truth data must NEVER be exposed to observable customer/event models or APIs.
    """

    model_config = ConfigDict(extra="forbid")

    customer_id: str
    generation_segment: str
    natural_conversion: bool
    conversion_after_intervention: bool
    recoverable: bool
    maximum_recoverable_revenue: Decimal
    true_root_cause: str

    @field_validator("customer_id", "generation_segment", "true_root_cause")
    @classmethod
    def validate_strings(cls, v: Any, info: ValidationInfo) -> str:
        return _validate_non_empty_string(info.field_name or "field", v)

    @field_validator("maximum_recoverable_revenue")
    @classmethod
    def validate_revenue(cls, v: Decimal, info: ValidationInfo) -> Decimal:
        return _validate_non_negative_decimal(info.field_name or "maximum_recoverable_revenue", v)
