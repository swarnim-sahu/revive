"""
Batch Ranking and Top-K Metric Evaluation for Revive Risk Engine.
"""

from typing import Dict, List, Tuple
from app.risk.scoring import ScoredCustomer


def rank_customers(
    scored_customers: List[ScoredCustomer],
    by: str = "revenue_at_risk",
    descending: bool = True,
) -> List[ScoredCustomer]:
    """
    Rank scored customers by `revenue_at_risk` or `risk_score`.
    """
    if by == "revenue_at_risk":
        return sorted(scored_customers, key=lambda c: c.revenue_at_risk, reverse=descending)
    elif by == "risk_score":
        return sorted(scored_customers, key=lambda c: c.risk_score, reverse=descending)
    else:
        raise ValueError(f"Unsupported ranking key: {by}")


def evaluate_top_k_ranking(
    ranked_customers: List[ScoredCustomer],
    ground_truth_failures: Dict[str, int],  # customer_id -> 1 if failure, 0 if converted
    k_percents: List[float] = [1.0, 5.0, 10.0],
) -> Dict[str, Dict[str, float]]:
    """
    Evaluate Recall@K%, Precision@K%, and RevenueAtRiskCaptured@K% for given customer ranking.
    `ground_truth_failures`: Dict mapping customer_id to binary target (1 for natural conversion failure).
    """
    total_customers = len(ranked_customers)
    if total_customers == 0:
        return {}

    total_failures = sum(ground_truth_failures.get(c.customer_id, 0) for c in ranked_customers)
    total_exposed_revenue = sum(float(c.revenue_at_risk) for c in ranked_customers)

    metrics: Dict[str, Dict[str, float]] = {}

    for k_pct in k_percents:
        top_k_count = max(1, int(round(total_customers * (k_pct / 100.0))))
        top_k_customers = ranked_customers[:top_k_count]

        top_k_failures = sum(ground_truth_failures.get(c.customer_id, 0) for c in top_k_customers)
        top_k_revenue = sum(float(c.revenue_at_risk) for c in top_k_customers)

        recall_k = (top_k_failures / total_failures) if total_failures > 0 else 0.0
        precision_k = top_k_failures / top_k_count
        revenue_captured_pct = (top_k_revenue / total_exposed_revenue) if total_exposed_revenue > 0 else 0.0

        metrics[f"Top_{k_pct:.0f}%"] = {
            "top_k_count": float(top_k_count),
            "recall": round(float(recall_k), 4),
            "precision": round(float(precision_k), 4),
            "revenue_captured": round(float(top_k_revenue), 2),
            "revenue_captured_pct": round(float(revenue_captured_pct), 4),
        }

    return metrics
