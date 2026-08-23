"""
Offline Evaluation Engine for Revive Revenue Risk Engine (Phase 3).
Calculates ROC-AUC, PR-AUC, Brier Score, Precision, Recall, F1, Confusion Matrix,
Calibration Curves, Top-K metrics, and Baseline Comparisons.
"""

from typing import Any, Dict, List, Tuple
import numpy as np
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from app.risk.ranking import evaluate_top_k_ranking, rank_customers
from app.risk.scoring import ScoredCustomer


class RiskModelEvaluator:
    """Evaluates trained risk model predictions against ground truth labels."""

    @staticmethod
    def evaluate(
        y_true: List[int],
        y_prob: List[float],
        threshold: float = 0.50,
    ) -> Dict[str, Any]:
        """
        Compute standard classification and calibration metrics.
        `y_true`: 1 for conversion_failure, 0 for natural_conversion.
        `y_prob`: predicted risk scores.
        """
        y_true_arr = np.array(y_true, dtype=int)
        y_prob_arr = np.array(y_prob, dtype=float)

        roc_auc = float(roc_auc_score(y_true_arr, y_prob_arr))
        pr_auc = float(average_precision_score(y_true_arr, y_prob_arr))
        brier = float(brier_score_loss(y_true_arr, y_prob_arr))

        y_pred = (y_prob_arr >= threshold).astype(int)

        prec = float(precision_score(y_true_arr, y_pred, zero_division=0))
        rec = float(recall_score(y_true_arr, y_pred, zero_division=0))
        f1 = float(f1_score(y_true_arr, y_pred, zero_division=0))
        acc = float(accuracy_score(y_true_arr, y_pred))
        cm = confusion_matrix(y_true_arr, y_pred).tolist()

        return {
            "roc_auc": round(roc_auc, 4),
            "pr_auc": round(pr_auc, 4),
            "brier_score": round(brier, 4),
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1_score": round(f1, 4),
            "accuracy": round(acc, 4),
            "confusion_matrix": cm,
            "operating_threshold": threshold,
        }

    @staticmethod
    def calibration_analysis(
        y_true: List[int],
        y_prob: List[float],
        n_bins: int = 5,
    ) -> List[Dict[str, float]]:
        """
        Divide predictions into equal-width bins and compare mean predicted probability to observed failure rate.
        """
        y_true_arr = np.array(y_true)
        y_prob_arr = np.array(y_prob)

        bins = np.linspace(0.0, 1.0, n_bins + 1)
        calibration_results = []

        for i in range(n_bins):
            low, high = bins[i], bins[i + 1]
            mask = (y_prob_arr >= low) & (y_prob_arr < high if i < n_bins - 1 else y_prob_arr <= high)
            bin_size = int(np.sum(mask))

            if bin_size > 0:
                mean_pred = float(np.mean(y_prob_arr[mask]))
                observed_rate = float(np.mean(y_true_arr[mask]))
            else:
                mean_pred = 0.0
                observed_rate = 0.0

            calibration_results.append({
                "bin_range": f"{low:.2f}-{high:.2f}",
                "bin_count": bin_size,
                "mean_predicted_prob": round(mean_pred, 4),
                "observed_failure_rate": round(observed_rate, 4),
            })

        return calibration_results

    @staticmethod
    def evaluate_baselines(
        feature_records: List[Dict[str, Any]],
        scored_customers: List[ScoredCustomer],
        ground_truth_failures: Dict[str, int],
        k_percents: List[float] = [1.0, 5.0, 10.0],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Compare model ranking quality against simple non-ML baselines:
        - Model: rank by revenue_at_risk
        - Baseline A: rank by plan_price
        - Baseline B: rank by hours_until_trial_expiry (fewest remaining hours first)
        - Baseline C: rank by checkout_started == 1 AND checkout_completed == 0
        """
        # 1. Model ranking
        model_ranked = rank_customers(scored_customers, by="revenue_at_risk", descending=True)
        model_top_k = evaluate_top_k_ranking(model_ranked, ground_truth_failures, k_percents)

        # Map customer_id -> feature record
        feat_map = {f["customer_id"]: f for f in feature_records}

        # 2. Baseline A: rank by plan_price
        baseline_a = sorted(scored_customers, key=lambda c: float(c.plan_price), reverse=True)
        base_a_top_k = evaluate_top_k_ranking(baseline_a, ground_truth_failures, k_percents)

        # 3. Baseline B: rank by hours_until_trial_expiry ascending
        baseline_b = sorted(
            scored_customers,
            key=lambda c: feat_map[c.customer_id]["hours_until_trial_expiry"]
        )
        base_b_top_k = evaluate_top_k_ranking(baseline_b, ground_truth_failures, k_percents)

        # 4. Baseline C: checkout_started == 1 and checkout_completed == 0
        def _base_c_score(c: ScoredCustomer) -> float:
            f = feat_map[c.customer_id]
            is_abandoned = (f["checkout_started"] == 1 and f["checkout_completed"] == 0)
            return (1.0 if is_abandoned else 0.0, float(c.plan_price))

        baseline_c = sorted(scored_customers, key=_base_c_score, reverse=True)
        base_c_top_k = evaluate_top_k_ranking(baseline_c, ground_truth_failures, k_percents)

        return {
            "revive_risk_model": model_top_k,
            "baseline_a_plan_price": base_a_top_k,
            "baseline_b_trial_expiry": base_b_top_k,
            "baseline_c_checkout_abandoned": base_c_top_k,
        }
