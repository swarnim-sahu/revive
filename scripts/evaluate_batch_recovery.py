"""
REVIVE Phase 9 — Batch Recovery Evaluation & Evidence Script.
Executes deterministic batch evaluation across synthetic customer journeys.
Prints formatted aggregate metrics, risk distribution, policy actions, EV recovery rates,
Phase 7 measured recovery, and optional JSON execution output.

Usage:
    py scripts/evaluate_batch_recovery.py --customers 100 --seed 42
    py scripts/evaluate_batch_recovery.py --customers 500 --output results/batch_recovery.json
"""

import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, os.path.abspath("."))

from app.evaluation.batch import BatchRecoveryEvaluator


def print_cli_report(res: dict) -> None:
    agg = res["aggregate_metrics"]
    risk_dist = res["risk_distribution"]
    diag_dist = res["diagnosis_distribution"]
    ai_dist = res["ai_status_distribution"]
    act_dist = res["action_distribution"]
    outcome_dist = res.get("outcome_distribution", {})
    attr_dist = res.get("attribution_distribution", {})

    print("=" * 60)
    print("REVIVE — BATCH RECOVERY EVALUATION REPORT")
    print("=" * 60)

    print("\nDataset")
    print("-------")
    print(f"Customers evaluated:       {agg.get('total_customers', 0)}")
    print(f"Events processed:          {agg.get('total_events', 0)}")
    print(f"Customers w/ pay failures: {agg.get('customers_with_payment_failures', 0)}")

    print("\nRisk Tiers")
    print("----------")
    print(f"Critical:                  {risk_dist.get('CRITICAL', 0)}")
    print(f"High:                      {risk_dist.get('HIGH', 0)}")
    print(f"Medium:                    {risk_dist.get('MEDIUM', 0)}")
    print(f"Low:                       {risk_dist.get('LOW', 0)}")
    print(f"Average risk score:        {agg.get('average_risk_score', 0.0):.4f}")
    print(f"Average revenue at risk:   INR {agg.get('average_revenue_at_risk', 0.0):.2f}")

    print("\nDiagnosis Breakdown")
    print("-------------------")
    print(f"PAYMENT_FRICTION:          {diag_dist.get('PAYMENT_FRICTION', 0)}")
    print(f"Actionable diagnoses:      {agg.get('actionable_diagnosis_count', 0)}")
    print(f"Non-actionable diagnoses:  {agg.get('non_actionable_diagnosis_count', 0)}")
    for d, cnt in diag_dist.items():
        if d != "PAYMENT_FRICTION":
            print(f"  - {d:23s}: {cnt}")

    print("\nAI Layer Performance (Mock Provider)")
    print("-----------------------------------")
    print(f"AI success count:          {agg.get('ai_success_count', 0)}")
    print(f"Fallbacks triggered:       {agg.get('ai_fallback_count', 0)}")
    print(f"Average AI confidence:     {agg.get('average_ai_confidence', 0.0):.4f}")

    print("\nPolicy & Governance")
    print("-------------------")
    print(f"Eligible customers:        {agg.get('eligible_customers', 0)}")
    print(f"Ineligible customers:      {agg.get('ineligible_customers', 0)}")

    print("\nSelected Actions Taxonomy")
    print("-------------------------")
    for act, cnt in act_dist.items():
        print(f"{act:26s}: {cnt}")

    print("\nEXPECTED RECOVERY (Phase 5 Policy Prediction)")
    print("----------------------------------------------")
    print(f"Total revenue at risk:     INR {agg.get('total_revenue_at_risk', 0.0):.2f}")
    print(f"Total expected recovery:   INR {agg.get('total_expected_recovery_value', 0.0):.2f}")
    print(f"Expected recovery rate:    {agg.get('expected_recovery_rate_pct', 0.0):.2f}%")

    print("\nMEASURED RECOVERY (Phase 7 Realized & Attributed)")
    print("-------------------------------------------------")
    print(f"Gross observed revenue:    INR {agg.get('total_gross_observed_revenue', 0.0):.2f}")
    print(f"Attributable revenue:      INR {agg.get('total_attributable_revenue', 0.0):.2f}")
    print(f"Intervention cost:         INR {agg.get('total_intervention_cost', 0.0):.2f}")
    print(f"Net recovered revenue:     INR {agg.get('total_net_recovered_revenue', 0.0):.2f}")
    print(f"Measured recovery rate:    {agg.get('measured_recovery_rate_pct', 0.0):.2f}%")
    print(f"Recovered customers:       {agg.get('recovered_customer_count', 0)}")

    print("\nOutcome Distribution:")
    for out, cnt in outcome_dist.items():
        print(f"  - {out:23s}: {cnt}")

    print("\nAttribution Distribution:")
    for attr, cnt in attr_dist.items():
        print(f"  - {attr:23s}: {cnt}")

    print("\nExecution Engine (Mock Razorpay Dispatch)")
    print("-----------------------------------------")
    print(f"Execution candidates:      {agg.get('execution_candidates', 0)}")
    print(f"Successful executions:     {agg.get('simulated_successful_executions', 0)}")
    print(f"Failed executions:         {agg.get('simulated_failed_executions', 0)}")
    print(f"Blocked executions:        {agg.get('blocked_executions', 0)}")
    print(f"Duplicates prevented:      {agg.get('duplicates_prevented', 0)}")

    print("\n" + "=" * 60)
    print("BATCH EVALUATION COMPLETE")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="REVIVE Batch Recovery Evaluator Script")
    parser.add_argument("--customers", type=int, default=100, help="Number of synthetic customers to evaluate")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducible generation")
    parser.add_argument("--snapshot-hours", type=float, default=336.0, help="Snapshot evaluation window in hours (default 336.0 = 14 days)")
    parser.add_argument("--output", type=str, default=None, help="Optional JSON file output path")
    args = parser.parse_args()

    evaluator = BatchRecoveryEvaluator(
        customers_count=args.customers,
        seed=args.seed,
        snapshot_hours=args.snapshot_hours,
    )
    result = evaluator.evaluate()
    res_dict = result.to_dict()

    print_cli_report(res_dict)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(res_dict, f, indent=2)
        print(f"\n[OK] Wrote batch evaluation report to '{out_path}'")


if __name__ == "__main__":
    main()
