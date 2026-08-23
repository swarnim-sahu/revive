"""
CLI script to train and select the Revive Revenue Risk Engine model.

Usage:
    python scripts/train_risk_model.py --input data/processed/risk_features.json --seed 42
"""

import argparse
import json
from pathlib import Path
import random
import sys
from typing import Dict, List, Tuple

# Ensure root directory is on sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from app.risk.evaluation import RiskModelEvaluator
from app.risk.model import ReviveRiskModel


def train_val_test_split(
    features: List[Dict],
    labels: List[int],
    seed: int = 42,
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
) -> Tuple[List[Dict], List[int], List[Dict], List[int], List[Dict], List[int]]:
    """
    Perform a deterministic 70% train / 15% val / 15% test split by customer ID.
    Guarantees no customer appears in multiple splits.
    """
    paired = list(zip(features, labels))
    # Sort by customer_id first for deterministic ordering before shuffle
    paired.sort(key=lambda x: x[0]["customer_id"])

    rng = random.Random(seed)
    rng.shuffle(paired)

    n_total = len(paired)
    n_train = int(round(n_total * train_ratio))
    n_val = int(round(n_total * val_ratio))

    train_data = paired[:n_train]
    val_data = paired[n_train : n_train + n_val]
    test_data = paired[n_train + n_val :]

    X_train, y_train = zip(*train_data) if train_data else ([], [])
    X_val, y_val = zip(*val_data) if val_data else ([], [])
    X_test, y_test = zip(*test_data) if test_data else ([], [])

    return list(X_train), list(y_train), list(X_val), list(y_val), list(X_test), list(y_test)


def main() -> None:
    parser = argparse.ArgumentParser(description="Train and select Revive risk prediction model.")
    parser.add_argument("--input", type=str, default="data/processed/risk_features.json", help="Path to input features JSON")
    parser.add_argument("--model-output", type=str, default="models/risk/risk_model.joblib", help="Output path for model artifact")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")

    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: input file {input_path} not found. Run scripts/build_risk_features.py first.")
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    features = data["features"]
    labels = data["labels"]

    if not labels:
        print("Error: Input dataset contains no ground-truth labels for training!")
        sys.exit(1)

    print(f"Loaded {len(features)} feature records. Splitting dataset (70/15/15, seed={args.seed})...")
    X_tr, y_tr, X_val, y_val, X_te, y_te = train_val_test_split(features, labels, seed=args.seed)

    print(f"Train size: {len(X_tr)} | Validation size: {len(X_val)} | Test size: {len(X_te)}")

    # 1. Train Primary Baseline: Logistic Regression
    print("\nTraining Logistic Regression baseline...")
    lr_model = ReviveRiskModel(model_type="logistic_regression", seed=args.seed)
    lr_model.fit(X_tr, y_tr)
    lr_val_probs = lr_model.predict_proba(X_val)
    lr_val_metrics = RiskModelEvaluator.evaluate(y_val, list(lr_val_probs))
    print(f"Logistic Regression Validation ROC-AUC: {lr_val_metrics['roc_auc']:.4f} | PR-AUC: {lr_val_metrics['pr_auc']:.4f} | Brier: {lr_val_metrics['brier_score']:.4f}")

    # 2. Train Comparison Model: Random Forest
    print("\nTraining Random Forest comparison model...")
    rf_model = ReviveRiskModel(model_type="random_forest", seed=args.seed)
    rf_model.fit(X_tr, y_tr)
    rf_val_probs = rf_model.predict_proba(X_val)
    rf_val_metrics = RiskModelEvaluator.evaluate(y_val, list(rf_val_probs))
    print(f"Random Forest Validation ROC-AUC:      {rf_val_metrics['roc_auc']:.4f} | PR-AUC: {rf_val_metrics['pr_auc']:.4f} | Brier: {rf_val_metrics['brier_score']:.4f}")

    # Model Selection using Validation ROC-AUC
    if rf_val_metrics["roc_auc"] > lr_val_metrics["roc_auc"]:
        selected_model = rf_model
        selected_name = "Random Forest"
    else:
        selected_model = lr_model
        selected_name = "Logistic Regression"

    print(f"\nSelected Model based on Validation ROC-AUC: {selected_name}")

    out_path = Path(args.model_output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    selected_model.save(str(out_path))
    print(f"Saved selected model artifact to: {out_path.resolve()}\n")


if __name__ == "__main__":
    main()
