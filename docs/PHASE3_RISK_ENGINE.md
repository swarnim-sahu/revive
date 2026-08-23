# REVIVE — Phase 3: Revenue Risk Engine

## Overview

Phase 3 implements the **Revenue Risk Engine**, the first decision-support component of REVIVE.
It computes observable customer risk features at a fixed decision snapshot, predicts the probability of natural conversion failure, categorizes operational risk tiers, calculates expected revenue exposure (`revenue_at_risk`), provides deterministic observable explanations, and ranks customers for priority handling.

---

## Architecture & Commands

### 1. Build Risk Features

Extracts snapshot-based observable customer features at $T = \text{trial\_start} + 72\text{h}$ (capped at trial end). Filters out post-snapshot events and excludes all hidden ground-truth fields.

```bash
python scripts/build_risk_features.py --output data/processed/risk_features.json
```

### 2. Train Risk Model

Performs a deterministic 70% train / 15% val / 15% test customer-level split (`seed=42`). Trains the primary probabilistic Logistic Regression baseline and optional Random Forest model, selects the model with the highest validation ROC-AUC score, and saves the model artifact.

```bash
python scripts/train_risk_model.py --input data/processed/risk_features.json --seed 42
```

### 3. Evaluate Risk Model

Loads the trained model artifact and evaluates predictive performance on the held-out 15% test set. Produces classification metrics, calibration analysis, Top-K recall/precision, revenue-at-risk capture, baseline comparisons, sample scored customer outputs, and deterministic evidence explanations.

```bash
python scripts/evaluate_risk_model.py --features data/processed/risk_features.json --model-path models/risk/risk_model.joblib
```

---

## Artifact Location

- **Trained Model Artifact:** `models/risk/risk_model.joblib`
- **Extracted Feature Dataset:** `data/processed/risk_features.json`

---

## Leakage Prevention

1. **Hidden-Label Leakage:** The runtime feature builder (`app/risk/features.py`) never reads or accepts `ground_truth.jsonl`. Forbidden ground-truth fields (`generation_segment`, `natural_conversion`, `conversion_after_intervention`, `recoverable`, `maximum_recoverable_revenue`, `true_root_cause`) are strictly blocked from feature vectors.
2. **Temporal Leakage:** Events with timestamps occurring after the 72h snapshot timestamp are excluded from feature construction.
3. **Outcome Leakage:** Conversion/expiration events after snapshot are excluded from inference feature vectors.

---

## Metrics & Outputs

- **Primary Model Selection Metric:** ROC-AUC
- **Evaluation Metrics:** ROC-AUC, PR-AUC, Brier Score, Precision, Recall, F1, Accuracy, Confusion Matrix, Binned Calibration Analysis.
- **Top-K Ranking Metrics:** Recall@1%, 5%, 10%; Precision@1%, 5%, 10%; RevenueAtRiskCaptured@1%, 5%, 10%.
- **Baselines Compared:** Plan Price (Baseline A), Trial Expiry Recency (Baseline B), Abandoned Checkout Heuristic (Baseline C).
- **Customer Output Schema:**
  - `customer_id`
  - `prediction_timestamp`
  - `risk_score` (0.0 to 1.0)
  - `risk_tier` (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`)
  - `plan_id`
  - `plan_price`
  - `revenue_at_risk` (`plan_price × risk_score`)
