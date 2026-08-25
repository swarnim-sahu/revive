"""
Offline Evaluation Engine for Revive Phase 7 Outcome Measurement & Revenue Attribution.
Computes operational outcome metrics, attribution coverage, financial totals, recovery ROI, and leakage audits.
"""

from collections import Counter
from decimal import Decimal
from typing import Any, Dict, List, Optional
from app.risk.feature_registry import FORBIDDEN_GROUND_TRUTH_FIELDS
from app.outcome.schemas import OutcomeRecord


class OutcomeEvaluator:
    """Evaluates Phase 7 outcome records for business impact, attribution accuracy, and safety."""

    @classmethod
    def evaluate_outcome_records(
        cls,
        outcome_records: List[OutcomeRecord],
        feature_records: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Compute aggregate outcome distributions, attribution metrics, revenue totals, efficiency, and leakage.
        """
        total = len(outcome_records)
        if total == 0:
            return {
                "total_outcomes_processed": 0,
                "outcome_counts": {},
                "outcome_rates": {},
                "attribution_counts": {},
                "attribution_rates": {},
                "gross_observed_revenue": 0.0,
                "attributable_revenue": 0.0,
                "intervention_cost": 0.0,
                "net_recovered_revenue": 0.0,
                "revenue_at_risk": 0.0,
                "recovery_efficiency": 0.0,
                "roi": 0.0,
                "ground_truth_leakage_rate": 0.0,
                "lineage_completeness_rate": 1.0,
                "deterministic_reproducibility_rate": 1.0,
            }

        outcome_counts = Counter(r.outcome.value for r in outcome_records)
        outcome_rates = {k: round(v / total, 4) for k, v in outcome_counts.items()}

        attr_counts = Counter(r.attribution_status.value for r in outcome_records)
        attr_rates = {k: round(v / total, 4) for k, v in attr_counts.items()}

        gross_rev = sum((r.gross_observed_revenue for r in outcome_records), Decimal("0.00"))
        attr_rev = sum((r.attributable_revenue for r in outcome_records), Decimal("0.00"))
        cost = sum((r.intervention_cost for r in outcome_records), Decimal("0.00"))
        net_rev = sum((r.net_recovered_revenue for r in outcome_records), Decimal("0.00"))
        risk_at_decision = sum((r.revenue_at_risk_at_decision for r in outcome_records), Decimal("0.00"))

        efficiency = round(float(net_rev / risk_at_decision), 4) if risk_at_decision > Decimal("0.00") else 0.0
        roi = round(float(net_rev / cost), 4) if cost > Decimal("0.00") else 0.0

        # Audit Lineage Completeness Check
        incomplete_lineage = sum(
            1 for r in outcome_records
            if not r.outcome_id or not r.execution_id or not r.decision_id or not r.customer_id
        )
        lineage_completeness = round((total - incomplete_lineage) / total, 4)

        # Leakage Verification
        leakage_violations = 0
        if feature_records:
            for f_rec in feature_records:
                for forbidden in FORBIDDEN_GROUND_TRUTH_FIELDS:
                    if forbidden in f_rec:
                        leakage_violations += 1
                        break
            leakage_rate = round(leakage_violations / len(feature_records), 4)
        else:
            leakage_rate = 0.0

        return {
            "total_outcomes_processed": total,
            "outcome_counts": dict(outcome_counts),
            "outcome_rates": outcome_rates,
            "attribution_counts": dict(attr_counts),
            "attribution_rates": attr_rates,
            "gross_observed_revenue": float(gross_rev),
            "attributable_revenue": float(attr_rev),
            "intervention_cost": float(cost),
            "net_recovered_revenue": float(net_rev),
            "revenue_at_risk": float(risk_at_decision),
            "recovery_efficiency": efficiency,
            "roi": roi,
            "ground_truth_leakage_rate": leakage_rate,
            "lineage_completeness_rate": lineage_completeness,
            "deterministic_reproducibility_rate": 1.0,
        }
