"""
Customer Risk Scoring and Exposure Calculation for Revive (Phase 3).
Produces probability risk score, deterministic risk tier, and revenue at risk.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, field_validator, ValidationInfo

from app.models.entities import _validate_non_empty_string, _validate_non_negative_decimal
from app.risk.model import ReviveRiskModel


def determine_risk_tier(risk_score: float) -> str:
    """
    Categorize risk_score into deterministic operational risk tiers.
    LOW: risk_score < 0.30
    MEDIUM: 0.30 <= risk_score < 0.60
    HIGH: 0.60 <= risk_score < 0.80
    CRITICAL: risk_score >= 0.80
    """
    if risk_score < 0.30:
        return "LOW"
    elif risk_score < 0.60:
        return "MEDIUM"
    elif risk_score < 0.80:
        return "HIGH"
    else:
        return "CRITICAL"


class ScoredCustomer(BaseModel):
    """Output risk prediction record for a customer."""

    model_config = ConfigDict(extra="forbid")

    customer_id: str
    prediction_timestamp: str
    risk_score: float
    risk_tier: str
    plan_id: str
    plan_price: Decimal
    revenue_at_risk: Decimal

    @field_validator("customer_id", "prediction_timestamp", "risk_tier", "plan_id")
    @classmethod
    def validate_strings(cls, v: Any, info: ValidationInfo) -> str:
        return _validate_non_empty_string(info.field_name or "field", v)

    @field_validator("risk_score")
    @classmethod
    def validate_risk_score(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError("risk_score must be between 0.0 and 1.0")
        return v

    @field_validator("plan_price", "revenue_at_risk")
    @classmethod
    def validate_money(cls, v: Decimal, info: ValidationInfo) -> Decimal:
        return _validate_non_negative_decimal(info.field_name or "money", v)


class RiskScorer:
    """Computes customer risk predictions using a trained ReviveRiskModel."""

    def __init__(self, model: ReviveRiskModel) -> None:
        self.model = model

    def score_customer(self, feature_record: Dict[str, Any]) -> ScoredCustomer:
        """Score a single customer feature record."""
        scores = self.score_batch([feature_record])
        return scores[0]

    def score_batch(self, feature_records: List[Dict[str, Any]]) -> List[ScoredCustomer]:
        """Score a batch of customer feature records."""
        if not feature_records:
            return []

        risk_scores = self.model.predict_proba(feature_records)

        results: List[ScoredCustomer] = []
        for feat, score_val in zip(feature_records, risk_scores):
            # Clamp float to exactly [0.0, 1.0] to avoid float precision edge cases
            clamped_score = float(max(0.0, min(1.0, score_val)))
            tier = determine_risk_tier(clamped_score)

            price_dec = Decimal(str(feat["plan_price"]))
            # Revenue at Risk = plan_price * risk_score
            rev_at_risk_raw = price_dec * Decimal(str(round(clamped_score, 6)))
            rev_at_risk = rev_at_risk_raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            results.append(
                ScoredCustomer(
                    customer_id=feat["customer_id"],
                    prediction_timestamp=feat["prediction_timestamp"],
                    risk_score=round(clamped_score, 4),
                    risk_tier=tier,
                    plan_id=feat["plan_id"],
                    plan_price=price_dec.quantize(Decimal("0.01")),
                    revenue_at_risk=rev_at_risk,
                )
            )

        return results
