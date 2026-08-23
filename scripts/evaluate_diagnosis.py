"""
CLI script to evaluate Revive Root-Cause Diagnosis Engine (Phase 4).
Consumes existing Phase 3 risk predictions and evaluates evidence-grounded diagnoses against ground truth.

Provides observability-aware evaluation sections:
- Section A: SNAPSHOT DIAGNOSIS QUALITY
- Section B: OBSERVABILITY ANALYSIS
- Section C: FUTURE OUTCOME ALIGNMENT
- Section D: SAFETY / LEAKAGE VERIFICATION
- Section E: DIAGNOSIS DISTRIBUTION
- Section F: PER-CAUSE OBSERVABILITY & ALIGNMENT TABLE
- Section G: REFERENCE-ONLY NAIVE FUTURE-LABEL ACCURACY BENCHMARK

Usage:
    python scripts/evaluate_diagnosis.py --features data/processed/risk_features.json --model-path models/risk/risk_model.joblib
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

from app.models.entities import Customer, Plan
from app.models.events import BaseEvent
from app.risk.feature_registry import FORBIDDEN_GROUND_TRUTH_FIELDS
from app.risk.model import ReviveRiskModel
from app.risk.scoring import RiskScorer
from app.diagnosis.engine import DiagnosisEngine
from app.diagnosis.evaluation import DiagnosisEvaluator


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Phase 4 Root-Cause Diagnosis Engine.")
    parser.add_argument("--features", type=str, default="data/processed/risk_features.json")
    parser.add_argument("--model-path", type=str, default="models/risk/risk_model.joblib")
    parser.add_argument("--customers-file", type=str, default="data/generated/observable/customers.jsonl")
    parser.add_argument("--plans-file", type=str, default="data/generated/observable/plans.jsonl")
    parser.add_argument("--events-file", type=str, default="data/generated/observable/events.jsonl")
    parser.add_argument("--ground-truth-file", type=str, default="data/generated/ground_truth/ground_truth.jsonl")

    args = parser.parse_args()

    model_path = Path(args.model_path)
    if not model_path.exists():
        print(f"Error: Risk model {model_path} not found. Run Phase 3 first.")
        sys.exit(1)

    features_path = Path(args.features)
    if not features_path.exists():
        print(f"Error: Features file {features_path} not found. Run Phase 3 first.")
        sys.exit(1)

    gt_path = Path(args.ground_truth_file)
    if not gt_path.exists():
        print(f"Error: Ground truth file {gt_path} not found.")
        sys.exit(1)

    print(f"\n==================================================")
    print(f"   REVIVE ROOT-CAUSE DIAGNOSIS ENGINE EVALUATION")
    print(f"==================================================")

    # 1. Load Phase 3 model & observable dataset
    risk_model = ReviveRiskModel.load(str(model_path))
    scorer = RiskScorer(risk_model)

    with open(features_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    feature_records = data["features"]
    feat_map = {f["customer_id"]: f for f in feature_records}

    # Load entities and events
    plans_map: Dict[str, Plan] = {}
    with open(args.plans_file, "r", encoding="utf-8") as f:
        for line in f:
            p_dict = json.loads(line)
            plans_map[p_dict["plan_id"]] = Plan(**p_dict)

    customers_map: Dict[str, Customer] = {}
    with open(args.customers_file, "r", encoding="utf-8") as f:
        for line in f:
            c_dict = json.loads(line)
            customers_map[c_dict["customer_id"]] = Customer(**c_dict)

    events_by_customer: Dict[str, List[BaseEvent]] = {}
    with open(args.events_file, "r", encoding="utf-8") as f:
        for line in f:
            e_dict = json.loads(line)
            evt = BaseEvent(**e_dict)
            events_by_customer.setdefault(evt.customer_id, []).append(evt)

    # Load ground truth map (customer_id -> true_root_cause) FOR EVALUATION ONLY
    gt_map: Dict[str, str] = {}
    with open(gt_path, "r", encoding="utf-8") as f:
        for line in f:
            gt_dict = json.loads(line)
            gt_map[gt_dict["customer_id"]] = gt_dict.get("true_root_cause", "unknown")

    # 2. Execute Diagnosis Engine
    engine = DiagnosisEngine()

    scored_customers = scorer.score_batch(feature_records)
    diagnoses = []

    print(f"Diagnosing {len(scored_customers)} customers...")
    for sc in scored_customers:
        cust = customers_map[sc.customer_id]
        plan = plans_map[sc.plan_id]
        cust_events = events_by_customer.get(sc.customer_id, [])
        f_rec = feat_map[sc.customer_id]

        diag = engine.diagnose_customer(sc, cust, cust_events, plan, f_rec)
        diagnoses.append(diag)

    # 3. Evaluate Performance Metrics
    metrics = DiagnosisEvaluator.evaluate_diagnoses(
        diagnoses,
        gt_map,
        customer_events_map=events_by_customer,
        feature_records_map=feat_map,
    )

    print(f"\n--- SECTION A: SNAPSHOT DIAGNOSIS QUALITY ---")
    print(f"Evidence Consistency:         {metrics['evidence_consistency_rate']*100:.1f}%")
    print(f"Evidence-Grounded Rate:       {metrics['evidence_grounded_diagnosis_rate']*100:.1f}%")
    print(f"Coverage:                     {metrics['diagnosis_coverage']*100:.1f}% ({metrics['confident_diagnoses']}/{metrics['eligible_customers']} eligible at-risk customers)")
    print(f"Uncertainty Rate:             {metrics['uncertain_rate']*100:.1f}% (SAFE UNCERTAINTY)")
    print(f"Requires Review:              {metrics['requires_review_rate']*100:.1f}%")
    print(f"Actionable Diagnosis Rate:    {metrics['actionable_diagnosis_rate']*100:.1f}%")

    print(f"\n--- SECTION B: OBSERVABILITY ANALYSIS ---")
    print(f"Primary Observable-State Ambiguity Rate: {metrics['primary_observable_ambiguity_rate']*100:.1f}%")
    print(f"Raw Event-Count Ambiguity Rate:          {metrics['raw_event_count_ambiguity_rate']*100:.1f}%")

    print(f"\n--- SECTION C: FUTURE OUTCOME ALIGNMENT ---")
    print(f"Future Outcome Alignment Rate:{metrics['future_outcome_alignment_rate']*100:.1f}% ({metrics['actionable_aligned_count']}/{metrics['actionable_evaluated_count']} actionable diagnoses evaluated)")
    print(f"Per-diagnosis alignment:")
    for diag_cat, counts in metrics["per_diagnosis_alignment"].items():
        rate = (counts["aligned"] / counts["total"] * 100) if counts["total"] > 0 else 0.0
        print(f"  - {diag_cat:<22}: {rate:.1f}% ({counts['aligned']}/{counts['total']})")

    print(f"\n--- SECTION D: SAFETY / LEAKAGE VERIFICATION ---")
    print(f"Future Information Leakage Rate:{metrics['future_information_leakage_rate']*100:.1f}%")
    for f_rec in feature_records:
        for forbidden in FORBIDDEN_GROUND_TRUTH_FIELDS:
            assert forbidden not in f_rec, f"Leaked forbidden ground truth field '{forbidden}'!"
    print("[OK] Verified: Zero hidden ground-truth fields present during inference.")

    print(f"\n--- SECTION E: DIAGNOSIS DISTRIBUTION ---")
    from collections import Counter
    diag_counts = Counter(d.diagnosis.value for d in diagnoses)
    for cat_name, cnt in diag_counts.items():
        print(f"  - {cat_name:<22}: {cnt}")

    print(f"\n--- SECTION F: PER-CAUSE OBSERVABILITY & ALIGNMENT TABLE ---")
    print(f"{'Cause':<22} | {'Total':<6} | {'Observable':<10} | {'Partial':<8} | {'Not Yet':<8} | {'Actionable':<10} | {'Aligned':<8}")
    print("-" * 88)
    obs_table = metrics["per_cause_observability_table"]
    for cause_name, s in obs_table.items():
        print(f"{cause_name:<22} | {s['total']:<6} | {s['observable']:<10} | {s['partially_observable']:<8} | {s['not_yet_observable']:<8} | {s['actionable']:<10} | {s['aligned']:<8}")

    print(f"\n--- SECTION G: REFERENCE-ONLY NAIVE FUTURE-LABEL ACCURACY BENCHMARK ---")
    print(f"Note: This benchmark compares a 72-hour snapshot diagnosis against a 14-day eventual outcome")
    print(f"      and therefore should not be interpreted as causal diagnosis accuracy.")
    print(f"Naive 14-Day Ground-Truth Accuracy: {metrics['overall_accuracy']:.4f}")
    print(f"Macro Precision:                    {metrics['macro_precision']:.4f}")
    print(f"Macro Recall:                       {metrics['macro_recall']:.4f}")
    print(f"Macro F1:                           {metrics['macro_f1']:.4f}")

    print(f"\n--- Per-Class Naive Performance ---")
    print(f"{'Class':<22} | {'Precision':<10} | {'Recall':<10} | {'F1-Score':<10} | {'Support':<8}")
    print("-" * 70)
    report = metrics["per_class_report"]
    for lbl in metrics["labels"]:
        if lbl in report:
            r_cls = report[lbl]
            print(f"{lbl:<22} | {r_cls['precision']:<10.4f} | {r_cls['recall']:<10.4f} | {r_cls['f1-score']:<10.4f} | {int(r_cls['support']):<8}")

    # 4. Print 5 Sample Customer Traces
    print(f"\n--- 5 Sample Customer Traces ---")
    for idx in range(min(5, len(diagnoses))):
        d = diagnoses[idx]
        gt_raw = gt_map.get(d.customer_id, "unknown")
        gt_mapped = DiagnosisEvaluator.map_ground_truth(gt_raw)

        is_actionable = (d.actionability.value == "candidate")
        is_aligned = (d.diagnosis.value == gt_mapped) if is_actionable else "N/A (Uncertain)"

        print(f"\nCustomer: {d.customer_id}")
        print(f"  Tprediction:       {d.prediction_timestamp}")
        print(f"  Observable Evidence: {len(d.supporting_evidence)} items")
        for ev in d.supporting_evidence[:3]:
            print(f"    - {ev.description}")
        print(f"  Diagnosis:         {d.diagnosis.value} (Confidence: {d.confidence:.2f}, Actionability: {d.actionability.value})")
        print(f"  Eventual GT Label: {gt_raw} (Mapped: {gt_mapped})")
        print(f"  Future Outcome Aligned: {is_aligned}")

    print("=" * 50 + "\n")


if __name__ == "__main__":
    main()
