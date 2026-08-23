"""
Core Orchestration Module for Revive Phase 5 Intervention Decision Engine.
Consumes Phase 3 risk scores and Phase 4 root-cause diagnoses to produce deterministic InterventionDecisions.
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional
from app.diagnosis.schemas import CustomerDiagnosis
from app.models.entities import Plan
from app.risk.scoring import ScoredCustomer
from app.intervention.config import DEFAULT_INTERVENTION_CONFIG, InterventionConfig
from app.intervention.eligibility import EligibilityEngine
from app.intervention.policy import PolicyEngine
from app.intervention.schemas import CandidateActionScore, InterventionAction, InterventionDecision
from app.intervention.validator import InputValidator


class InterventionEngine:
    """Core deterministic, side-effect-free intervention decision orchestrator."""

    def __init__(self, config: InterventionConfig = DEFAULT_INTERVENTION_CONFIG) -> None:
        self.config = config
        self.validator = InputValidator()
        self.eligibility_engine = EligibilityEngine(config=config)
        self.policy_engine = PolicyEngine(config=config)

    def decide_intervention(
        self,
        scored_customer: ScoredCustomer,
        diagnosis: CustomerDiagnosis,
        plan: Plan,
        feature_record: Dict[str, Any],
        intervention_history: Optional[List[Dict[str, Any]]] = None,
    ) -> InterventionDecision:
        """
        Produce a deterministic InterventionDecision for a customer.
        Reuses Phase 3 prediction timestamp and Phase 4 diagnosis without side effects.
        """
        # 1. Input Validation & Ground-Truth Leakage Check
        self.validator.validate_inputs(scored_customer, diagnosis, feature_record)

        # 2. Check Eligibility Gates
        elig_status, forced_action, forced_reason = self.eligibility_engine.check_eligibility(
            scored_customer, diagnosis, intervention_history
        )

        supporting_evidence = [ev.description for ev in diagnosis.supporting_evidence]

        # 3. Handle Non-Eligible / Escalated / Cooldown States
        if forced_action is not None:
            # Build baseline candidate scores
            baseline_candidates = [
                CandidateActionScore(
                    action=action,
                    expected_value=Decimal("0.00"),
                    recovery_probability_assumption=0.0,
                    direct_cost=self.config.direct_action_costs.get(action.value, Decimal("0.00")),
                    incentive_penalty_assumption=Decimal("0.00"),
                    harm_penalty_assumption=Decimal("0.00"),
                    is_eligible=(action == forced_action),
                    disqualification_reason=None if (action == forced_action) else forced_reason,
                )
                for action in InterventionAction
            ]

            rejection_reasons = {
                act.value: forced_reason for act in InterventionAction if act != forced_action
            }

            return InterventionDecision(
                customer_id=scored_customer.customer_id,
                decision_timestamp=scored_customer.prediction_timestamp,
                policy_version=self.config.policy_version,
                assumption_version=self.config.assumption_version,
                risk_score=scored_customer.risk_score,
                risk_tier=scored_customer.risk_tier,
                revenue_at_risk=scored_customer.revenue_at_risk,
                diagnosis=diagnosis.diagnosis.value,
                diagnosis_confidence=diagnosis.confidence,
                diagnosis_actionability=diagnosis.actionability.value,
                eligibility_status=elig_status,
                selected_action=forced_action,
                expected_value=Decimal("0.00"),
                candidate_scores=baseline_candidates,
                decision_reason=forced_reason or f"Forced action {forced_action.value} due to eligibility state",
                rejection_reasons=rejection_reasons,
                supporting_evidence=supporting_evidence,
            )

        # 4. Evaluate & Score Candidate Actions for ELIGIBLE Customers
        candidate_scores = self.policy_engine.evaluate_candidate_actions(
            scored_customer, diagnosis, plan, feature_record
        )

        # 5. Select Optimal Bounded Action
        best_candidate = self.policy_engine.select_best_action(candidate_scores)

        # Build rejection reasons for unselected candidate actions
        rejection_reasons = {}
        for candidate in candidate_scores:
            if candidate.action != best_candidate.action:
                if not candidate.is_eligible:
                    rejection_reasons[candidate.action.value] = candidate.disqualification_reason or "Disqualified by safety filter"
                elif candidate.expected_value < best_candidate.expected_value:
                    rejection_reasons[candidate.action.value] = f"Lower Expected Value (Rs. {candidate.expected_value} < Rs. {best_candidate.expected_value})"
                else:
                    rejection_reasons[candidate.action.value] = "Tie-breaker preference for selected action"

        decision_reason = (
            f"Selected action {best_candidate.action.value} with maximum Net Expected Value "
            f"Rs. {best_candidate.expected_value} (Recovery Assumption: {best_candidate.recovery_probability_assumption*100:.1f}%)"
        )

        return InterventionDecision(
            customer_id=scored_customer.customer_id,
            decision_timestamp=scored_customer.prediction_timestamp,
            policy_version=self.config.policy_version,
            assumption_version=self.config.assumption_version,
            risk_score=scored_customer.risk_score,
            risk_tier=scored_customer.risk_tier,
            revenue_at_risk=scored_customer.revenue_at_risk,
            diagnosis=diagnosis.diagnosis.value,
            diagnosis_confidence=diagnosis.confidence,
            diagnosis_actionability=diagnosis.actionability.value,
            eligibility_status="ELIGIBLE",
            selected_action=best_candidate.action,
            expected_value=best_candidate.expected_value,
            candidate_scores=candidate_scores,
            decision_reason=decision_reason,
            rejection_reasons=rejection_reasons,
            supporting_evidence=supporting_evidence,
        )
