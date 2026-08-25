"""
Revenue Accounting & Reconciliation Module for Revive Phase 7.
Calculates gross observed revenue, attributable revenue, intervention cost, net recovered revenue,
and preserves original Phase 3/5 revenue-at-risk predictions without retrospective modification.
"""

from decimal import Decimal
from typing import List, Optional, Tuple
from app.models.entities import Plan
from app.models.events import BaseEvent
from app.intervention.schemas import InterventionDecision
from app.execution.schemas import ExecutionAuditRecord
from app.outcome.config import DEFAULT_OUTCOME_CONFIG, OutcomeConfig
from app.outcome.schemas import AttributionStatus, OutcomeType


class RevenueCalculator:
    """Computes revenue accounting components adhering strictly to Revive Constitution §16 & Phase 7 §16."""

    @classmethod
    def calculate_revenue(
        cls,
        outcome: OutcomeType,
        attribution_status: AttributionStatus,
        execution_record: ExecutionAuditRecord,
        evidence_events: List[BaseEvent],
        decision: InterventionDecision,
        plan: Optional[Plan] = None,
        config: OutcomeConfig = DEFAULT_OUTCOME_CONFIG,
    ) -> Tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
        """
        Calculate (gross_observed_revenue, attributable_revenue, intervention_cost, net_recovered_revenue, revenue_at_risk_at_decision).
        """
        revenue_at_risk = Decimal(str(decision.revenue_at_risk))

        # 1. Gross Observed Revenue
        if outcome in {OutcomeType.RECOVERED, OutcomeType.CONVERTED, OutcomeType.ALREADY_CONVERTED}:
            gross_observed = cls._extract_observed_revenue(evidence_events, plan, revenue_at_risk)
        else:
            gross_observed = Decimal("0.00")

        # 2. Attributable Revenue based on Attribution Status
        if attribution_status in {AttributionStatus.DIRECTLY_OBSERVED, AttributionStatus.ATTRIBUTION_SUPPORTED}:
            attributable = gross_observed
        elif attribution_status == AttributionStatus.TEMPORALLY_ASSOCIATED:
            multiplier = Decimal(str(config.temporally_associated_attribution_fraction))
            attributable = (gross_observed * multiplier).quantize(Decimal("0.01"))
        else:
            attributable = Decimal("0.00")

        # 3. Intervention Direct Cost
        action_name = execution_record.action.value
        cost = config.direct_action_costs.get(action_name, Decimal("0.00"))

        # 4. Net Recovered Revenue = Attributable Revenue - Intervention Cost
        net_recovered = attributable - cost

        return gross_observed, attributable, cost, net_recovered, revenue_at_risk

    @classmethod
    def _extract_observed_revenue(
        cls, evidence_events: List[BaseEvent], plan: Optional[Plan], fallback_val: Decimal
    ) -> Decimal:
        """Extract realized revenue from evidence event payloads or plan details."""
        for evt in evidence_events:
            if isinstance(evt.payload, dict):
                amt = evt.payload.get("amount") or evt.payload.get("captured_amount") or evt.payload.get("price")
                if amt is not None:
                    try:
                        return Decimal(str(amt)).quantize(Decimal("0.01"))
                    except Exception:
                        pass

        if plan is not None:
            if hasattr(plan, "price_inr") and plan.price_inr is not None:
                return Decimal(str(plan.price_inr)).quantize(Decimal("0.01"))
            if hasattr(plan, "price") and plan.price is not None:
                return Decimal(str(plan.price)).quantize(Decimal("0.01"))

        return fallback_val
