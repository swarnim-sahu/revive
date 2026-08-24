"""
CLI script to evaluate Revive Execution Engine (Phase 6).
Consumes Phase 5 InterventionDecisions and evaluates operational execution correctness and safety compliance.

Usage:
    python scripts/evaluate_execution.py --features data/processed/risk_features.json --model-path models/risk/risk_model.joblib
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
from app.execution.evaluation import ExecutionEvaluator


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Phase 6 Execution & Delivery Engine.")
    parser.add_argument("--features", type=str, default="data/processed/risk_features.json")
    parser.add_argument("--model-path", type=str, default="models/risk/risk_model.joblib")
    parser.add_argument("--customers-file", type=str, default="data/generated/observable/customers.jsonl")
    parser.add_argument("--plans-file", type=str, default="data/generated/observable/plans.jsonl")
    parser.add_argument("--events-file", type=str, default="data/generated/observable/events.jsonl")

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
    print(f"   REVIVE EXECUTION & WORKFLOW ENGINE EVALUATION")
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

    # 2. Execute Upstream Pipelines & Phase 6 Execution Engine
    diag_engine = DiagnosisEngine()
    interv_engine = InterventionEngine()
    exec_engine = ExecutionEngine()

    scored_customers = scorer.score_batch(feature_records)
    audit_records = []

    print(f"Executing decisions for {len(scored_customers)} customers...")
    for sc in scored_customers:
        cust = customers_map[sc.customer_id]
        plan = plans_map[sc.plan_id]
        cust_events = events_by_customer.get(sc.customer_id, [])
        f_rec = feat_map[sc.customer_id]

        diag = diag_engine.diagnose_customer(sc, cust, cust_events, plan, f_rec)
        decision = interv_engine.decide_intervention(sc, diag, plan, f_rec)
        audit_rec = exec_engine.execute_decision(decision, feature_record=f_rec)
        audit_records.append(audit_rec)

    # 3. Compute Metrics
    metrics = ExecutionEvaluator.evaluate_execution_records(audit_records, feature_records)

    print(f"\n--- OPERATIONAL EXECUTION METRICS ---")
    print(f"1. Total Decisions Processed:          {metrics['total_decisions_processed']}")
    print(f"2. Executed Count & Rate:              {metrics['executed_count']} ({metrics['executed_rate']*100:.1f}%)")
    print(f"3. Blocked Count & Rate:               {metrics['blocked_count']} ({metrics['blocked_rate']*100:.1f}%)")
    print(f"4. Escalated Count & Rate:             {metrics['escalated_count']} ({metrics['escalated_rate']*100:.1f}%)")
    print(f"5. NO_ACTION Count & Rate:             {metrics['no_action_count']} ({metrics['no_action_rate']*100:.1f}%)")
    print(f"6. Retry Budget Compliance Rate:       {metrics['retry_budget_compliance_rate']*100:.1f}%")
    print(f"7. Audit Trail Completeness Rate:      {metrics['audit_completeness_rate']*100:.1f}%")
    print(f"8. Test-Mode Isolation Rate:          {metrics['test_mode_isolation_rate']*100:.1f}%")
    print(f"9. Ground-Truth Leakage Rate:          {metrics['ground_truth_leakage_rate']*100:.1f}%")

    print(f"\n--- 5 SAMPLE EXECUTION AUDIT RECORDS ---")
    for idx in range(min(5, len(audit_records))):
        rec = audit_records[idx]
        print(f"\nExecution ID: {rec.execution_id}")
        print(f"  Customer:   {rec.customer_id}")
        print(f"  Action:     {rec.action.value}")
        print(f"  Status:     {rec.status.value}")
        print(f"  Attempts:   {rec.attempt_number}")
        print(f"  Payload ID: {rec.payload_id}")

    # 4. Leakage Verification
    print(f"\n--- LEAKAGE & SAFETY VERIFICATION ---")
    for f_rec in feature_records:
        for forbidden in FORBIDDEN_GROUND_TRUTH_FIELDS:
            assert forbidden not in f_rec, f"Leaked forbidden ground truth field '{forbidden}'!"
    print("[OK] Verified: Zero hidden ground-truth fields present during execution.")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    main()
