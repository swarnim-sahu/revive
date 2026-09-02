"""
Baseline Control Evaluator for REVIVE Phase B.
Evaluates the counterfactual baseline ("What would have happened without REVIVE?").
Zero REVIVE interventions are applied. Conversion is determined strictly by hidden natural_conversion.
"""

from decimal import Decimal
from typing import Dict, List, Optional
from app.models.entities import Customer, Plan
from app.simulation.ground_truth import GroundTruthRecord
from app.evaluation.schemas import ControlCaseRecord


class ControlEvaluator:
    """Evaluates the baseline control cohort representing the un-intervened world."""

    @staticmethod
    def evaluate_control_case(
        customer: Customer,
        plan: Plan,
        ground_truth: GroundTruthRecord,
    ) -> ControlCaseRecord:
        """
        Evaluate a single control case using the post-hoc counterfactual ground truth.
        """
        case_id = f"case_ctrl_{customer.customer_id}"
        price = float(plan.price)

        if ground_truth.natural_conversion:
            converted = True
            gross_rev = price
            net_rev = price
            status = "NATURAL_CONVERSION"
        else:
            converted = False
            gross_rev = 0.0
            net_rev = 0.0
            status = "CHURNED_NO_INTERVENTION"

        return ControlCaseRecord(
            case_id=case_id,
            customer_id=customer.customer_id,
            control_converted=converted,
            control_gross_revenue=gross_rev,
            control_net_revenue=net_rev,
            control_revenue_at_risk=price,
            control_case_status=status,
        )

    @classmethod
    def evaluate_control_cohort(
        cls,
        customers: List[Customer],
        plans_map: Dict[str, Plan],
        ground_truth_map: Dict[str, GroundTruthRecord],
    ) -> List[ControlCaseRecord]:
        """Evaluate an entire batch of control customers."""
        records: List[ControlCaseRecord] = []
        for cust in customers:
            plan = plans_map[cust.plan_id]
            gt = ground_truth_map[cust.customer_id]
            records.append(cls.evaluate_control_case(cust, plan, gt))
        return records
