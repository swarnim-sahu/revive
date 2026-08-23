"""
Pydantic Schema Models for Revive Phase 5 Intervention Decision Engine.
Defines bounded action taxonomy, candidate action scores, and final intervention decisions.
"""

from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class InterventionAction(str, Enum):
    """Bounded Phase 5 Intervention Action Taxonomy."""

    NO_ACTION = "NO_ACTION"
    PRODUCT_GUIDANCE = "PRODUCT_GUIDANCE"
    REMINDER = "REMINDER"
    CHECKOUT_ASSISTANCE = "CHECKOUT_ASSISTANCE"
    PAYMENT_RECOVERY = "PAYMENT_RECOVERY"
    TRIAL_EXTENSION = "TRIAL_EXTENSION"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class CandidateActionScore(BaseModel):
    """Deterministic score, cost, and expected value evaluation for a candidate action."""

    action: InterventionAction
    expected_value: Decimal = Field(..., description="Calculated Net Expected Value in INR")
    recovery_probability_assumption: float = Field(..., description="Deterministic simulation recovery probability assumption")
    direct_cost: Decimal = Field(..., description="Direct execution cost in INR")
    incentive_penalty_assumption: Decimal = Field(..., description="Configurable incentive penalty assumption in INR")
    harm_penalty_assumption: Decimal = Field(..., description="Customer friction/harm penalty assumption in INR")
    is_eligible: bool = Field(..., description="True if action passed all safety contraindication rules")
    disqualification_reason: Optional[str] = Field(None, description="Reason for safety disqualification if ineligible")


class InterventionDecision(BaseModel):
    """Complete, side-effect-free, deterministic Phase 5 intervention decision output."""

    customer_id: str
    decision_timestamp: str
    policy_version: str = Field("v1.0.0", description="Version of the intervention policy rules")
    assumption_version: str = Field("v1.0.0", description="Version of the deterministic simulation assumptions")

    # Phase 3 & 4 Input Snapshots
    risk_score: float
    risk_tier: str
    revenue_at_risk: Decimal
    diagnosis: str
    diagnosis_confidence: float
    diagnosis_actionability: str

    # Decision Engine Outputs
    eligibility_status: str = Field(..., description="ELIGIBLE, INELIGIBLE, ESCALATED, or COOLDOWN")
    selected_action: InterventionAction = Field(..., description="Selected bounded intervention action")
    expected_value: Decimal = Field(..., description="Expected net revenue recovery value of selected action")
    candidate_scores: List[CandidateActionScore] = Field(..., description="Evaluated candidate action breakdown")

    # Explanations & Auditing
    decision_reason: str = Field(..., description="Explicit human-readable explanation of action selection")
    rejection_reasons: Dict[str, str] = Field(default_factory=dict, description="Reasons competing actions were rejected")
    supporting_evidence: List[str] = Field(default_factory=list, description="Observable evidence supporting the decision")
