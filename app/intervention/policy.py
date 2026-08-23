"""
Policy Matrix and Expected Value Scorer for Revive Phase 5 Intervention Decision Engine.
Implements policy mapping, deterministic EV calculations, simulation assumption lookups, and tie-breaking.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple
from app.diagnosis.schemas import CustomerDiagnosis, DiagnosisCategory
from app.models.entities import Plan
from app.risk.scoring import ScoredCustomer
from app.intervention.config import InterventionConfig
from app.intervention.schemas import CandidateActionScore, InterventionAction
from app.intervention.safety import SafetyChecker


class PolicyEngine:
    """Evaluates candidate intervention actions, scores Expected Value (EV), and selects optimal action."""

    def __init__(self, config: InterventionConfig) -> None:
        self.config = config
        self.safety_checker = SafetyChecker(config=config)

    def calculate_expected_value(
        self,
        action: InterventionAction,
        scored_customer: ScoredCustomer,
        diagnosis: CustomerDiagnosis,
        plan: Plan,
    ) -> Tuple[Decimal, float, Decimal, Decimal, Decimal, bool]:
        """
        Calculate Net Expected Value (EV) for a candidate action:
        EV(a) = [P_recovery_assumption * revenue_at_risk] - C_direct - incentive_penalty_assumption - C_harm_assumption

        Returns Tuple[ev, p_rec_assumption, direct_cost, incentive_penalty, harm_penalty, has_policy_mapping]
        """
        if action == InterventionAction.NO_ACTION:
            return (Decimal("0.00"), 0.0, Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), True)

        diag_key = diagnosis.diagnosis.value
        act_key = action.value

        # Closed policy matrix check
        pair = (diag_key, act_key)
        has_policy_mapping = pair in self.config.recovery_probability_assumptions
        if not has_policy_mapping:
            direct_cost = self.config.direct_action_costs.get(act_key, Decimal("0.00"))
            return (Decimal("0.00"), 0.0, direct_cost, Decimal("0.00"), Decimal("0.00"), False)

        # 1. Deterministic Recovery Probability Assumption
        p_rec = self.config.recovery_probability_assumptions[pair]

        # Scale recovery assumption by diagnostic confidence
        p_rec_scaled = p_rec * diagnosis.confidence

        # 2. Direct Execution Cost
        direct_cost = self.config.direct_action_costs.get(act_key, Decimal("0.00"))

        # 3. Incentive Penalty Assumption (Configurable assumption: e.g. fraction of plan price)
        incentive_fraction = self.config.incentive_penalty_fractions.get(act_key, 0.0)
        incentive_penalty = (plan.price * Decimal(str(incentive_fraction))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # 4. Harm Penalty Assumption
        harm_penalty = self.config.harm_penalty_assumptions.get(pair, Decimal("0.00"))

        # Gross Expected Recovery
        rev_at_risk = scored_customer.revenue_at_risk
        gross_recovery = (rev_at_risk * Decimal(str(p_rec_scaled))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Net Expected Value
        net_ev = gross_recovery - direct_cost - incentive_penalty - harm_penalty

        return (net_ev, round(p_rec_scaled, 4), direct_cost, incentive_penalty, harm_penalty, True)

    def evaluate_candidate_actions(
        self,
        scored_customer: ScoredCustomer,
        diagnosis: CustomerDiagnosis,
        plan: Plan,
        feature_record: Dict[str, Any],
    ) -> List[CandidateActionScore]:
        """Evaluate and score all candidate actions in the Phase 5 taxonomy."""
        candidates: List[CandidateActionScore] = []

        for action in InterventionAction:
            ev, p_rec, direct_cost, inc_pen, harm_pen, has_policy = self.calculate_expected_value(
                action, scored_customer, diagnosis, plan
            )

            if not has_policy:
                is_safe = False
                disq_reason = "No policy mapping for diagnosis/action pair"
            else:
                is_safe, disq_reason = self.safety_checker.is_action_safe(
                    action, diagnosis, feature_record, ev
                )

            candidates.append(
                CandidateActionScore(
                    action=action,
                    expected_value=ev,
                    recovery_probability_assumption=p_rec,
                    direct_cost=direct_cost,
                    incentive_penalty_assumption=inc_pen,
                    harm_penalty_assumption=harm_pen,
                    is_eligible=is_safe,
                    disqualification_reason=disq_reason,
                )
            )

        return candidates

    def select_best_action(
        self, candidate_scores: List[CandidateActionScore]
    ) -> CandidateActionScore:
        """
        Select the best eligible candidate action based on maximum Expected Value (EV).
        Implements deterministic tie-breaking.
        """
        eligible_candidates = [c for c in candidate_scores if c.is_eligible]

        if not eligible_candidates:
            # Fallback to NO_ACTION if no candidates are eligible
            return next(c for c in candidate_scores if c.action == InterventionAction.NO_ACTION)

        # Sort eligible candidates by EV descending
        # Deterministic tie-breaking:
        # 1. Higher EV
        # 2. Lower Direct Cost
        # 3. Alphabetical order of action value
        sorted_candidates = sorted(
            eligible_candidates,
            key=lambda c: (-c.expected_value, c.direct_cost, c.action.value),
        )

        return sorted_candidates[0]
