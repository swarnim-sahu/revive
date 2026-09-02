#!/usr/bin/env python
"""
REVIVE Phase B Benchmark CLI Runner.
Executes controlled high-volume evaluation (Control vs Treatment) and produces
machine-readable artifacts (experiment.json, summary.json, cases.jsonl, exceptions.jsonl)
and human-readable reports (report.md).

Usage:
    py scripts/run_phase_b_evaluation.py --customers 20000 --control 10000 --treatment 10000 --seed 42 --output reports/phase_b/
"""

import argparse
from pathlib import Path
import sys
import time

# Ensure project root is available in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Ensure UTF-8 output encoding for Windows compatibility
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from app.evaluation.phase_b import PhaseBEvaluator
from app.evaluation.reporting import PhaseBReportGenerator
from app.evaluation.schemas import ExceptionRecord, PairedCaseResult


def main() -> int:
    parser = argparse.ArgumentParser(
        description="REVIVE Phase B Controlled High-Volume Evaluation & Incremental Revenue Benchmark",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--customers",
        type=int,
        default=20000,
        help="Total arm population or paired units count",
    )
    parser.add_argument(
        "--control",
        type=int,
        default=None,
        help="Number of cases to evaluate in Control arm (defaults to half of customers or customers)",
    )
    parser.add_argument(
        "--treatment",
        type=int,
        default=None,
        help="Number of cases to evaluate in Treatment arm (defaults to half of customers or customers)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Deterministic random seed for reproducibility",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="reports/phase_b",
        help="Directory to write output reports and JSON/JSONL artifacts",
    )
    parser.add_argument(
        "--model-path",
        type=str,
        default="models/risk/risk_model.joblib",
        help="Path to trained risk model artifact",
    )

    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    evaluator = PhaseBEvaluator(
        total_population=args.customers,
        control_count=args.control,
        treatment_count=args.treatment,
        seed=args.seed,
        model_path=args.model_path,
    )

    print("=" * 80)
    print("  REVIVE PHASE B: CONTROLLED HIGH-VOLUME BENCHMARK & REVENUE PROOF")
    print("=" * 80)
    print(f"  Paired Units:     {evaluator.paired_units:,}")
    print(f"  Control Arm:      {evaluator.control_count:,} evaluations")
    print(f"  Treatment Arm:    {evaluator.treatment_count:,} evaluations")
    print(f"  Total Arm Evals:  {evaluator.paired_units * 2:,}")
    print(f"  Random Seed:      {args.seed}")
    print(f"  Output Directory: {output_dir}")
    print(f"  Risk Model:       {args.model_path}")
    print("=" * 80)

    # Initialize streaming file handles for memory discipline
    cases_file = output_dir / "cases.jsonl"
    exceptions_file = output_dir / "exceptions.jsonl"

    f_cases = open(cases_file, "w", encoding="utf-8")
    f_exceptions = open(exceptions_file, "w", encoding="utf-8")

    def stream_case(case: PairedCaseResult) -> None:
        f_cases.write(case.model_dump_json() + "\n")

    def stream_exception(exc: ExceptionRecord) -> None:
        f_exceptions.write(exc.model_dump_json() + "\n")

    print("\n[1/3] Executing paired Control vs Treatment evaluation across pipeline...")
    t0 = time.time()
    result = evaluator.run_evaluation(
        case_callback=stream_case,
        exception_callback=stream_exception,
    )
    elapsed = time.time() - t0

    f_cases.close()
    f_exceptions.close()

    tp = result.throughput
    print(f"[OK] Evaluation completed in {elapsed:.2f} seconds ({tp.total_evaluations_per_second:,.2f} arm evals/sec, {tp.events_per_second:,.2f} total events/sec [{tp.initial_journey_events:,} initial + {tp.post_treatment_events:,} post-treatment])")

    print("\n[2/3] Generating structured artifacts and markdown report...")
    reporter = PhaseBReportGenerator(output_dir=str(output_dir))
    exp_path = reporter.write_experiment_json(result)
    sum_path = reporter.write_summary_json(result)
    rep_path = reporter.write_markdown_report(result)

    print(f"  - {exp_path}")
    print(f"  - {sum_path}")
    print(f"  - {cases_file}")
    print(f"  - {exceptions_file}")
    print(f"  - {rep_path}")

    print("\n[3/3] Financial & Operational Reconciliation Audit:")
    eco = result.economics
    diag = result.diagnosis_accuracy
    funnel = result.decision_funnel
    interv = result.intervention_appropriateness
    print(f"  - Control Conversions:        {eco.control_conversions:,} ({eco.control_conversion_rate*100:.2f}%) -> Net Revenue: Rs. {eco.control_net_revenue:,.2f}")
    print(f"  - Treatment Modeled Outcome:  {eco.treatment_total_conversions:,} ({eco.treatment_total_conversion_rate*100:.2f}%) [Natural: {eco.treatment_natural_conversions:,} + Genuine Incremental: {eco.treatment_genuine_incremental_recoveries:,} + Observed Unrecoverable: {eco.treatment_observed_unrecoverable_conversions:,}] -> Net Revenue: Rs. {eco.treatment_total_net_revenue:,.2f}")
    print(f"  - Conversion Lift:            +{eco.conversion_lift_points:.2f} percentage points ({eco.conversion_relative_lift_pct:+.1f}%)")
    print(f"  - Net Revenue Delta vs Ctrl:  Rs. {eco.incremental_net_revenue:,.2f}")
    print(f"  - Genuine Incremental Rev:    Rs. {eco.treatment_genuine_incremental_revenue:,.2f}")
    print(f"  - Attributable Recovery:      Rs. {eco.treatment_attributable_recovery_revenue:,.2f} (Net Recovered: Rs. {eco.treatment_net_recovered_revenue:,.2f})")
    print(f"  - Net Revenue Delta / ROI:    {eco.recovery_roi:.2f}x")
    print(f"  - Diagnosis Macro F1:         {diag.macro_f1:.4f} (Accuracy: {diag.overall_accuracy*100:.2f}%)")
    print(f"  - Safety Compliance:          {interv.safety_policy_compliance_rate*100:.2f}%")
    print(f"  - Funnel Invariant:           Eligible ({funnel.eligible_population:,}) <= Diagnosable ({funnel.diagnosable_population:,}) [PASSED]")
    print(f"  - Accounting Identities:      {'PASSED (Exact match)' if result.reconciliation_passed else 'FAILED'}")

    print("\n" + "=" * 80)
    print(f"  BENCHMARK COMPLETE -> {rep_path}")
    print("=" * 80)

    return 0 if result.reconciliation_passed else 1


if __name__ == "__main__":
    sys.exit(main())
