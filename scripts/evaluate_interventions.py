"""
CLI script to evaluate Revive Intervention Decision Engine (Phase 5).
Consumes Phase 3 risk predictions and Phase 4 root-cause diagnoses to compute the 10-stage decision funnel.

Usage:
    python scripts/evaluate_interventions.py --features data/processed/risk_features.json --model-path models/risk/risk_model.joblib
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
from app.intervention.evaluation import InterventionEvaluator


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Phase 5 Intervention Decision Engine.")
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
    print(f"   REVIVE INTERVENTION DECISION ENGINE EVALUATION")
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

    # 2. Execute Phase 4 Diagnosis & Phase 5 Intervention Engine
    diag_engine = DiagnosisEngine()
    interv_engine = InterventionEngine()

    scored_customers = scorer.score_batch(feature_records)
    decisions = []
    diag_map = {}

    print(f"Evaluating decisions for {len(scored_customers)} customers...")
    for sc in scored_customers:
        cust = customers_map[sc.customer_id]
        plan = plans_map[sc.plan_id]
        cust_events = events_by_customer.get(sc.customer_id, [])
        f_rec = feat_map[sc.customer_id]

        diag = diag_engine.diagnose_customer(sc, cust, cust_events, plan, f_rec)
        diag_map[sc.customer_id] = diag
        decision = interv_engine.decide_intervention(sc, diag, plan, f_rec)
        decisions.append(decision)

    # 3. Compute Funnel Metrics
    metrics = InterventionEvaluator.evaluate_decisions(
        decisions, diagnoses_map=diag_map, feature_records_map=feat_map
    )

    print(f"\n--- 10-STAGE DECISION FUNNEL ---")
    print(f"1. Total Population:                   {metrics['total_population']}")
    print(f"2. At-Risk Population (Risk >= 0.30):   {metrics['at_risk_population']}")
    print(f"3. Diagnosable/Actionable Population:  {metrics['diagnosable_actionable_population']}")
    print(f"4. Eligible Intervention Population:   {metrics['eligible_intervention_population']}")
    print(f"5. NO_ACTION Count & Rate:             {metrics['no_action_count']} ({metrics['no_action_rate']*100:.1f}%)")
    print(f"6. HUMAN_REVIEW Count & Rate:          {metrics['human_review_count']} ({metrics['human_review_rate']*100:.1f}%)")
    print(f"7. Automated Intervention Count & Rate:{metrics['automated_intervention_count']} ({metrics['automated_intervention_rate']*100:.1f}%)")
    print(f"8. Safety Policy Compliance Rate:      {metrics['safety_policy_compliance_rate']*100:.1f}%")
    print(f"9. Evidence-Action Consistency Rate:   {metrics['evidence_action_consistency_rate']*100:.1f}%")

    print(f"\n--- PER-ACTION TAXONOMY DISTRIBUTION ---")
    print(f"{'Action':<22} | {'Count':<8} | {'Rate':<8}")
    print("-" * 45)
    for act_name, d_info in metrics["per_action_distribution"].items():
        print(f"{act_name:<22} | {d_info['count']:<8} | {d_info['rate']*100:.1f}%")

    # 4. Print 5 Sample Customer Decision Traces
    print(f"\n--- 5 SAMPLE DECISION TRACES ---")
    for idx in range(min(5, len(decisions))):
        d = decisions[idx]
        print(f"\nCustomer: {d.customer_id}")
        print(f"  Risk:              {d.risk_score:.2f} ({d.risk_tier}), RevAtRisk: Rs. {d.revenue_at_risk}")
        print(f"  Diagnosis:         {d.diagnosis} (Conf: {d.diagnosis_confidence:.2f}, Actionability: {d.diagnosis_actionability})")
        print(f"  Eligibility:       {d.eligibility_status}")
        print(f"  Selected Action:   {d.selected_action.value} (Net EV: Rs. {d.expected_value})")
        print(f"  Decision Reason:   {d.decision_reason}")

    # 5. Leakage Verification
    print(f"\n--- LEAKAGE & SAFETY VERIFICATION ---")
    for f_rec in feature_records:
        for forbidden in FORBIDDEN_GROUND_TRUTH_FIELDS:
            assert forbidden not in f_rec, f"Leaked forbidden ground truth field '{forbidden}'!"
    print("[OK] Verified: Zero hidden ground-truth fields present during inference.")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    main()
