"""
CLI script to evaluate the trained Revive Revenue Risk Engine on held-out test set.

Usage:
    python scripts/evaluate_risk_model.py --features data/processed/risk_features.json --model-path models/risk/risk_model.joblib
"""

import argparse
import json
from pathlib import Path
import sys
from typing import Dict, List

# Ensure root directory is on sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from app.risk.evaluation import RiskModelEvaluator
from app.risk.explanations import DeterministicRiskExplainer
from app.risk.feature_registry import FORBIDDEN_GROUND_TRUTH_FIELDS
from app.risk.model import ReviveRiskModel
from app.risk.scoring import RiskScorer
from scripts.train_risk_model import train_val_test_split


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate trained Revive risk engine on held-out test set.")
    parser.add_argument("--features", type=str, default="data/processed/risk_features.json", help="Path to input features JSON")
    parser.add_argument("--model-path", type=str, default="models/risk/risk_model.joblib", help="Path to trained model artifact")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")

    args = parser.parse_args()

    model_path = Path(args.model_path)
    if not model_path.exists():
        print(f"Error: Model artifact {model_path} not found. Run scripts/train_risk_model.py first.")
        sys.exit(1)

    features_path = Path(args.features)
    if not features_path.exists():
        print(f"Error: Features file {features_path} not found. Run scripts/build_risk_features.py first.")
        sys.exit(1)

    # 1. Load model & data
    model = ReviveRiskModel.load(str(model_path))

    with open(features_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    features = data["features"]
    labels = data["labels"]

    # Perform same customer-level split
    _, _, _, _, X_te, y_te = train_val_test_split(features, labels, seed=args.seed)

    print(f"\n==================================================")
    print(f"   REVIVE REVENUE RISK ENGINE TEST EVALUATION")
    print(f"==================================================")
    print(f"Model Type:               {model.model_type}")
    print(f"Feature Registry Version: {model.feature_registry_version}")
    print(f"Test Set Size:            {len(X_te)} customers")

    # 2. Predictive Performance Metrics
    test_probs = list(model.predict_proba(X_te))
    metrics = RiskModelEvaluator.evaluate(y_te, test_probs)

    print(f"\n--- Probabilistic & Ranking Performance ---")
    print(f"ROC-AUC:            {metrics['roc_auc']:.4f}")
    print(f"PR-AUC:             {metrics['pr_auc']:.4f}")
    print(f"Brier Score:        {metrics['brier_score']:.4f}")
    print(f"\n--- Arbitrary 0.50 Threshold Metrics (Classification Cutoff) ---")
    print(f"Precision (@0.50):  {metrics['precision']:.4f}")
    print(f"Recall (@0.50):     {metrics['recall']:.4f}")
    print(f"F1 Score (@0.50):   {metrics['f1_score']:.4f}")
    print(f"Accuracy (@0.50):   {metrics['accuracy']:.4f}")
    print(f"Confusion Matrix:   TN={metrics['confusion_matrix'][0][0]}, FP={metrics['confusion_matrix'][0][1]} | FN={metrics['confusion_matrix'][1][0]}, TP={metrics['confusion_matrix'][1][1]}")
    print(f"Note: Operating at a fixed 0.50 cutoff produces high recall because predicted risk probabilities")
    print(f"      fall predominantly above 0.40. Primary business prioritization relies on revenue_at_risk ranking.")

    # 3. Calibration Analysis
    calib = RiskModelEvaluator.calibration_analysis(y_te, test_probs, n_bins=5)
    print(f"\n--- Calibration Analysis (5 Bins) ---")
    print(f"{'Bin Range':<15} | {'Count':<8} | {'Mean Pred Prob':<16} | {'Observed Failure Rate':<22}")
    print("-" * 70)
    for c_bin in calib:
        print(f"{c_bin['bin_range']:<15} | {c_bin['bin_count']:<8} | {c_bin['mean_predicted_prob']:<16.4f} | {c_bin['observed_failure_rate']:<22.4f}")

    # 4. Customer Scoring & Ranking
    scorer = RiskScorer(model)
    scored_test = scorer.score_batch(X_te)
    gt_failures_map = {f["customer_id"]: target for f, target in zip(X_te, y_te)}

    # 5. Baseline Comparison & Top-K Ranking
    baseline_eval = RiskModelEvaluator.evaluate_baselines(X_te, scored_test, gt_failures_map)

    print(f"\n--- Top-K Ranking & Baseline Comparisons (Primary Business Ranking by Revenue at Risk) ---")
    for b_name, b_results in baseline_eval.items():
        print(f"\n[{b_name.upper()}]")
        for k_label, k_metrics in b_results.items():
            print(f"  {k_label:<8}: Recall={k_metrics['recall']:.4f} | Precision={k_metrics['precision']:.4f} | Captured Rev={k_metrics['revenue_captured']:.2f} INR ({k_metrics['revenue_captured_pct']*100:.1f}%)")

    # 6. Feature Importances / Coefficients
    importances = model.get_feature_importances()
    top_importances = sorted(importances.items(), key=lambda x: abs(x[1]), reverse=True)[:10]
    print(f"\n--- Top 10 Model Feature Coefficients / Importances ---")
    for feat_name, coef_val in top_importances:
        print(f"  {feat_name:<30}: {coef_val:+.4f}")

    # 7. Sample Scored Customers & Deterministic Explanations
    print(f"\n--- Sample Scored Customers & Deterministic Explanations ---")
    sample_indices = [0, 1, 2, 3, 4]
    for idx in sample_indices:
        if idx < len(scored_test):
            sc = scored_test[idx]
            feat_rec = X_te[idx]
            reasons = DeterministicRiskExplainer.explain(feat_rec, sc.risk_score, sc.risk_tier)

            print(f"\nCustomer: {sc.customer_id}")
            print(f"  Prediction Timestamp: {sc.prediction_timestamp}")
            print(f"  Risk Score:           {sc.risk_score:.4f} ({sc.risk_tier})")
            print(f"  Plan:                 {sc.plan_id} ({sc.plan_price} INR)")
            print(f"  Revenue at Risk:      {sc.revenue_at_risk} INR")
            print(f"  Observable Reasons:")
            for r in reasons:
                print(f"    - {r}")

    # 8. Verification of Ground Truth Separation
    print(f"\n--- Leakage Verification ---")
    for feat_rec in X_te:
        for forbidden in FORBIDDEN_GROUND_TRUTH_FIELDS:
            assert forbidden not in feat_rec, f"Leaked forbidden ground truth field '{forbidden}'!"
    print("[OK] Verified: Zero hidden ground-truth fields present in inference features.")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    main()
