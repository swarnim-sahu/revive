"""
CLI script to evaluate Revive Phase 8 AI Intelligence Layer across 20,000 synthetic customers.
Compares deterministic Phase 4 baseline against AI-assisted analysis and measures grounding, schema validity, fallback rates, and leakage.

Usage:
    python scripts/evaluate_ai.py --features data/processed/risk_features.json --model-path models/risk/risk_model.joblib
"""

import argparse
import json
from pathlib import Path
import sys
from typing import Dict, List

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from app.models.entities import Customer, Plan
from app.models.events import BaseEvent
from app.risk.feature_registry import FORBIDDEN_GROUND_TRUTH_FIELDS
from app.risk.model import ReviveRiskModel
from app.risk.scoring import RiskScorer
from app.ai.config import AIConfig
from app.ai.evaluation import AIEvaluator
from app.ai.service import AIService


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Phase 8 AI Intelligence Layer.")
    parser.add_argument("--features", type=str, default="data/processed/risk_features.json")
    parser.add_argument("--model-path", type=str, default="models/risk/risk_model.joblib")
    parser.add_argument("--customers-file", type=str, default="data/generated/observable/customers.jsonl")
    parser.add_argument("--plans-file", type=str, default="data/generated/observable/plans.jsonl")
    parser.add_argument("--events-file", type=str, default="data/generated/observable/events.jsonl")
    parser.add_argument("--provider", type=str, default="mock", help="AI Provider ('mock' or 'gemini')")

    args = parser.parse_args()

    model_path = Path(args.model_path)
    if not model_path.exists():
        print(f"Error: Risk model {model_path} not found. Run Phase 3 first.")
        sys.exit(1)

    features_path = Path(args.features)
    if not features_path.exists():
        print(f"Error: Features file {features_path} not found. Run Phase 3 first.")
        sys.exit(1)

    print(f"\n==================================================")
    print(f"   REVIVE PHASE 8 — AI INTELLIGENCE LAYER EVALUATION")
    print(f"==================================================")

    # 1. Load Phase 3 model & observable dataset
    risk_model = ReviveRiskModel.load(str(model_path))
    scorer = RiskScorer(risk_model)

    with open(features_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    feature_records = data["features"]
    feat_map = {f["customer_id"]: f for f in feature_records}

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

    # 2. Execute AI Analysis Service Across Customers
    config = AIConfig(provider=args.provider, test_mode=(args.provider == "mock"))
    ai_service = AIService(config=config)

    scored_customers = scorer.score_batch(feature_records)
    ai_results = []

    print(f"Executing AI analysis for {len(scored_customers)} customers (Provider: {args.provider})...")
    for sc in scored_customers:
        cust = customers_map[sc.customer_id]
        plan = plans_map[sc.plan_id]
        cust_events = events_by_customer.get(sc.customer_id, [])
        f_rec = feat_map[sc.customer_id]

        res = ai_service.analyze_and_diagnose(sc, cust, cust_events, plan, f_rec)
        ai_results.append(res)

    # 3. Compute Metrics
    metrics = AIEvaluator.evaluate_ai_results(ai_results, feature_records)

    print(f"\n--- AI PERFORMANCE & QUALITY METRICS ---")
    print(f"Total Evaluations Processed:       {metrics['total_evaluations']}")
    print(f"Structured Schema Validity Rate:   {metrics['schema_validity_rate']*100:.1f}%")
    print(f"Evidence Grounding Accuracy Rate:  {metrics['grounding_accuracy_rate']*100:.1f}%")
    print(f"Unsupported Claim Rate:            {metrics['unsupported_claim_rate']*100:.1f}%")
    print(f"Deterministic Fallback Rate:       {metrics['fallback_rate']*100:.1f}%")
    print(f"Raw AI Proposal Agreement (vs P4): {metrics['ai_proposal_agreement_rate']*100:.1f}%")
    print(f"Final System Agreement (vs P4):    {metrics['final_diagnosis_agreement_rate']*100:.1f}%")
    print(f"Average AI Analysis Latency:       {metrics['average_latency_ms']:.2f} ms")

    print(f"\n--- DIAGNOSIS DISTRIBUTIONS ---")
    print("Raw AI Proposal Distribution:")
    for k, v in metrics["raw_ai_proposal_distribution"].items():
        print(f"  - {k:<25}: {v:>6} ({v/metrics['total_evaluations']*100:>5.1f}%)")
    print("\nP4 Baseline Diagnosis Distribution:")
    for k, v in metrics["p4_baseline_diagnosis_distribution"].items():
        print(f"  - {k:<25}: {v:>6} ({v/metrics['total_evaluations']*100:>5.1f}%)")
    print("\nFinal System Diagnosis Distribution:")
    for k, v in metrics["final_system_diagnosis_distribution"].items():
        print(f"  - {k:<25}: {v:>6} ({v/metrics['total_evaluations']*100:>5.1f}%)")

    print(f"\n--- AGREEMENT DEBUG ---")
    print(f"\nRaw AI Proposal:")
    print(f"  agreements: {metrics['ai_proposal_agreements']}")
    print(f"  comparisons: {metrics['ai_proposal_comparisons']}")
    print(f"  rate: {metrics['ai_proposal_agreement_rate']*100:.1f}%")
    print(f"\nFinal System:")
    print(f"  agreements: {metrics['final_agreements']}")
    print(f"  total: {metrics['total_evaluations']}")
    print(f"  rate: {metrics['final_diagnosis_agreement_rate']*100:.1f}%")
    print(f"\nFallback:")
    print(f"  fallbacks: {metrics['fallbacks_count']}")
    print(f"  total: {metrics['total_evaluations']}")
    print(f"  rate: {metrics['fallback_rate']*100:.1f}%")

    print(f"\n--- 10 REPRESENTATIVE CUSTOMER COMPARISONS ---")
    print(f"{'Customer ID':<15} | {'AI Candidate':<22} | {'P4 Baseline':<22} | {'Final Diagnosis':<22} | {'Fallback'}")
    print("-" * 95)
    for idx in range(min(10, len(ai_results))):
        res = ai_results[idx]
        ai_cand = res.analysis.diagnosis_candidate.value if res.analysis else "N/A"
        p4_base = res.fallback_diagnosis.diagnosis.value if res.fallback_diagnosis else "N/A"
        final_d = res.final_diagnosis.diagnosis.value
        fallback_str = str(res.metadata.fallback_used)
        print(f"{res.metadata.customer_id:<15} | {ai_cand:<22} | {p4_base:<22} | {final_d:<22} | {fallback_str}")

    print(f"\n--- SAFETY & DATA HYGIENE ---")
    print(f"Ground-Truth Leakage Rate:        {metrics['ground_truth_leakage_rate']*100:.1f}%")

    print(f"\n--- 5 SAMPLE AI AUDIT METADATA RECORDS ---")
    for idx in range(min(5, len(ai_results))):
        meta = ai_results[idx].metadata
        final_d = ai_results[idx].final_diagnosis
        print(f"\nAnalysis ID: {meta.analysis_id}")
        print(f"  Customer:           {meta.customer_id}")
        print(f"  Status:             {meta.status.value}")
        print(f"  Validation Status:  {meta.validation_status}")
        print(f"  Fallback Used:      {meta.fallback_used}")
        print(f"  Diagnosis:          {final_d.diagnosis.value}")
        print(f"  Confidence:         {final_d.confidence:.2f}")

    # 4. Leakage Verification
    print(f"\n--- LEAKAGE VERIFICATION ---")
    for f_rec in feature_records:
        for forbidden in FORBIDDEN_GROUND_TRUTH_FIELDS:
            assert forbidden not in f_rec, f"Leaked forbidden ground truth field '{forbidden}'!"
    print("[OK] Verified: Zero hidden ground-truth fields present in runtime AI pipeline.")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    main()
