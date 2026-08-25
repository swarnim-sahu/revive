"""
CLI script to evaluate Revive Phase 7 Outcome Measurement & Revenue Attribution Engine across 20,000 synthetic customers.

Usage:
    python scripts/evaluate_outcomes.py --features data/processed/risk_features.json --model-path models/risk/risk_model.joblib
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
from app.diagnosis.engine import DiagnosisEngine
from app.intervention.engine import InterventionEngine
from app.execution.engine import ExecutionEngine
from app.outcome.engine import OutcomeEngine
from app.outcome.evaluation import OutcomeEvaluator


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Phase 7 Outcome Measurement & Revenue Attribution Engine.")
    parser.add_argument("--features", type=str, default="data/processed/risk_features.json")
    parser.add_argument("--model-path", type=str, default="models/risk/risk_model.joblib")
    parser.add_argument("--customers-file", type=str, default="data/generated/observable/customers.jsonl")
    parser.add_argument("--plans-file", type=str, default="data/generated/observable/plans.jsonl")
    parser.add_argument("--events-file", type=str, default="data/generated/observable/events.jsonl")
    parser.add_argument("--observation-window", type=float, default=168.0, help="Observation window in hours (default: 168.0 = 7 days)")

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
    print(f"   REVIVE OUTCOME MEASUREMENT & ATTRIBUTION EVALUATION")
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

    # 2. Execute Upstream Pipeline & Phase 7 Outcome Engine
    diag_engine = DiagnosisEngine()
    interv_engine = InterventionEngine()
    exec_engine = ExecutionEngine()
    outcome_engine = OutcomeEngine()

    scored_customers = scorer.score_batch(feature_records)
    outcome_records = []

    print(f"Processing outcomes for {len(scored_customers)} customers (Window: {args.observation_window}h)...")
    for sc in scored_customers:
        cust = customers_map[sc.customer_id]
        plan = plans_map[sc.plan_id]
        cust_events = events_by_customer.get(sc.customer_id, [])
        f_rec = feat_map[sc.customer_id]

        diag = diag_engine.diagnose_customer(sc, cust, cust_events, plan, f_rec)
        decision = interv_engine.decide_intervention(sc, diag, plan, f_rec)
        exec_record = exec_engine.execute_decision(decision, feature_record=f_rec)

        outcome_rec = outcome_engine.measure_outcome(
            execution_record=exec_record,
            decision=decision,
            customer_events=cust_events,
            plan=plan,
            observation_window_hours=args.observation_window,
        )
        outcome_records.append(outcome_rec)

    # 3. Compute Operational Metrics
    metrics = OutcomeEvaluator.evaluate_outcome_records(outcome_records, feature_records)

    print(f"\n--- OUTCOME TAXONOMY DISTRIBUTION ---")
    print(f"Total Outcomes Processed:          {metrics['total_outcomes_processed']}")
    for k, v in metrics["outcome_counts"].items():
        rate = metrics["outcome_rates"].get(k, 0.0) * 100
        print(f"  - {k:<25}: {v:>6} ({rate:>5.1f}%)")

    print(f"\n--- ATTRIBUTION LEVELS DISTRIBUTION ---")
    for k, v in metrics["attribution_counts"].items():
        rate = metrics["attribution_rates"].get(k, 0.0) * 100
        print(f"  - {k:<25}: {v:>6} ({rate:>5.1f}%)")

    print(f"\n--- REVENUE ACCOUNTING & FINANCIAL METRICS ---")
    print(f"1. Total Predicted Revenue At Risk:  INR {metrics['revenue_at_risk']:>12,.2f}")
    print(f"2. Gross Observed Revenue:           INR {metrics['gross_observed_revenue']:>12,.2f}")
    print(f"3. Attributable Revenue:             INR {metrics['attributable_revenue']:>12,.2f}")
    print(f"4. Direct Intervention Cost:         INR {metrics['intervention_cost']:>12,.2f}")
    print(f"5. Net Recovered Revenue:            INR {metrics['net_recovered_revenue']:>12,.2f}")
    print(f"6. Recovery Efficiency:              {metrics['recovery_efficiency']*100:>11.2f}%")
    print(f"7. Return On Investment (ROI):       {metrics['roi']:>12.2f}x")

    print(f"\n--- SAFETY & DATA HYGIENE ---")
    print(f"1. Audit Lineage Completeness:       {metrics['lineage_completeness_rate']*100:.1f}%")
    print(f"2. Deterministic Reproducibility:    {metrics['deterministic_reproducibility_rate']*100:.1f}%")
    print(f"3. Ground-Truth Leakage Rate:        {metrics['ground_truth_leakage_rate']*100:.1f}%")

    print(f"\n--- 5 SAMPLE OUTCOME AUDIT RECORDS ---")
    for idx in range(min(5, len(outcome_records))):
        rec = outcome_records[idx]
        print(f"\nOutcome ID: {rec.outcome_id}")
        print(f"  Customer:     {rec.customer_id}")
        print(f"  Execution ID: {rec.execution_id}")
        print(f"  Action:       {rec.action.value}")
        print(f"  Outcome:      {rec.outcome.value}")
        print(f"  Attribution:  {rec.attribution_status.value}")
        print(f"  Gross Rev:    INR {rec.gross_observed_revenue}")
        print(f"  Net Rev:      INR {rec.net_recovered_revenue}")

    # 4. Leakage Verification
    print(f"\n--- LEAKAGE VERIFICATION ---")
    for f_rec in feature_records:
        for forbidden in FORBIDDEN_GROUND_TRUTH_FIELDS:
            assert forbidden not in f_rec, f"Leaked forbidden ground truth field '{forbidden}'!"
    print("[OK] Verified: Zero hidden ground-truth fields present in runtime outcome pipeline.")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    main()
