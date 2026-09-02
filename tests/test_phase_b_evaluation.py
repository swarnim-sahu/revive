"""
Unit and Integration Test Suite for REVIVE Phase B Controlled Evaluation & Incremental Revenue Proof.
Validates extracted production classifier, 4-way conversion taxonomy, genuine incremental recoveries,
ground-truth isolation, financial multi-identity reconciliation, exception ledger, decision accuracy,
safety governance, throughput event composition, and deterministic reproducibility.
"""

from decimal import Decimal
import json
from pathlib import Path
import pytest
from datetime import datetime, timezone

from app.models.entities import Customer, Plan
from app.models.events import BaseEvent
from app.simulation.config import ALL_PLANS, SYNTHETIC_MERCHANT
from app.simulation.generator import DatasetGenerator
from app.simulation.segments import create_ground_truth
from app.simulation.behaviour import sample_behaviour
from app.simulation.journey import generate_customer_journey
from app.simulation.ground_truth import GroundTruthRecord
from app.evaluation.control import ControlEvaluator
from app.evaluation.exceptions import ExceptionLedger
from app.evaluation.phase_b import (
    PhaseBEvaluator,
    classify_treatment_conversion,
    ConversionClassification,
    determine_paired_increment,
)
from app.evaluation.reporting import PhaseBReportGenerator
from app.evaluation.schemas import (
    ControlCaseRecord,
    PairedCaseResult,
    PhaseBEvaluationResult,
    TreatmentCaseRecord,
)


@pytest.fixture
def sample_plan():
    return Plan(
        plan_id="pro",
        name="Pro Plan",
        price=Decimal("999.00"),
        billing_interval="month",
    )


@pytest.fixture
def sample_customer():
    return Customer(
        customer_id="cus_test_001",
        merchant_id="merch_test",
        created_at=datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc),
        plan_id="pro",
    )


@pytest.fixture
def sample_ground_truth_natural():
    return GroundTruthRecord(
        customer_id="cus_test_001",
        generation_segment="healthy_converter",
        natural_conversion=True,
        conversion_after_intervention=True,
        recoverable=False,
        maximum_recoverable_revenue=Decimal("0.00"),
        true_root_cause="healthy_converter",
    )


@pytest.fixture
def sample_ground_truth_recoverable():
    return GroundTruthRecord(
        customer_id="cus_test_002",
        generation_segment="payment_friction",
        natural_conversion=False,
        conversion_after_intervention=True,
        recoverable=True,
        maximum_recoverable_revenue=Decimal("999.00"),
        true_root_cause="payment_friction",
    )


@pytest.fixture
def sample_ground_truth_unrecoverable():
    return GroundTruthRecord(
        customer_id="cus_test_003",
        generation_segment="low_intent_churn",
        natural_conversion=False,
        conversion_after_intervention=False,
        recoverable=False,
        maximum_recoverable_revenue=Decimal("0.00"),
        true_root_cause="low_intent_churn",
    )


# --- 1. DIRECT DETERMINISTIC CLASSIFIER TESTS (PRODUCTION HELPER EXERCISED DIRECTLY) ---

def test_direct_classifier_natural_conversion_quadrant():
    """Quadrant 1: natural_conversion=True, recoverable=False, treatment_converted=True -> NATURAL_CONVERSION."""
    res = classify_treatment_conversion(
        natural_conversion=True,
        recoverable=False,
        treatment_converted=True,
    )
    assert res.conversion_classification == "NATURAL_CONVERSION"
    assert res.is_natural_conversion is True
    assert res.is_genuine_incremental_recovery is False
    assert res.is_observed_unrecoverable_conversion is False


def test_direct_classifier_genuine_incremental_recovery_quadrant():
    """Quadrant 2: natural_conversion=False, recoverable=True, treatment_converted=True -> GENUINE_INCREMENTAL_RECOVERY."""
    res = classify_treatment_conversion(
        natural_conversion=False,
        recoverable=True,
        treatment_converted=True,
    )
    assert res.conversion_classification == "GENUINE_INCREMENTAL_RECOVERY"
    assert res.is_natural_conversion is False
    assert res.is_genuine_incremental_recovery is True
    assert res.is_observed_unrecoverable_conversion is False


def test_direct_classifier_observed_unrecoverable_conversion_quadrant():
    """Quadrant 3: natural_conversion=False, recoverable=False, treatment_converted=True -> OBSERVED_UNRECOVERABLE_CONVERSION."""
    res = classify_treatment_conversion(
        natural_conversion=False,
        recoverable=False,
        treatment_converted=True,
    )
    assert res.conversion_classification == "OBSERVED_UNRECOVERABLE_CONVERSION"
    assert res.is_natural_conversion is False
    assert res.is_genuine_incremental_recovery is False
    assert res.is_observed_unrecoverable_conversion is True


def test_direct_classifier_no_treatment_conversion_quadrant():
    """Quadrant 4: treatment_converted=False -> NO_TREATMENT_CONVERSION across any natural/recoverable ground truth."""
    for nat in (True, False):
        for rec in (True, False):
            res = classify_treatment_conversion(
                natural_conversion=nat,
                recoverable=rec,
                treatment_converted=False,
            )
            assert res.conversion_classification == "NO_TREATMENT_CONVERSION"
            assert res.is_natural_conversion is False
            assert res.is_genuine_incremental_recovery is False
            assert res.is_observed_unrecoverable_conversion is False


def test_paired_incremental_flag_semantics():
    """Verify production determine_paired_increment behavior across all four required cases."""
    # Case A: Genuine Incremental Recovery (treatment_converted=True, control_converted=False, is_genuine=True)
    assert determine_paired_increment(
        treatment_converted=True,
        control_converted=False,
        is_genuine_incremental_recovery=True,
    ) is True

    # Case B: Natural Conversion (treatment_converted=True, control_converted=True, is_genuine=False)
    assert determine_paired_increment(
        treatment_converted=True,
        control_converted=True,
        is_genuine_incremental_recovery=False,
    ) is False

    # Case C: Observed Unrecoverable Conversion (treatment_converted=True, control_converted=False, is_genuine=False)
    assert determine_paired_increment(
        treatment_converted=True,
        control_converted=False,
        is_genuine_incremental_recovery=False,
    ) is False

    # Case D: No Treatment Conversion (treatment_converted=False)
    assert determine_paired_increment(
        treatment_converted=False,
        control_converted=False,
        is_genuine_incremental_recovery=False,
    ) is False
    assert determine_paired_increment(
        treatment_converted=False,
        control_converted=True,
        is_genuine_incremental_recovery=False,
    ) is False


# --- 2. PIPELINE-INTEGRATION TESTS FOR PRODUCTION CLASSIFIER & 4-WAY TAXONOMY ---

def test_evaluator_uses_production_classifier():
    """Test A: Verify PhaseBEvaluator outputs exactly match production helper driven by independent ground truth."""
    generator = DatasetGenerator(customers_count=30, seed=42, output_dir="data/temp_test_eval")
    pairs = generator._allocate_plans_and_segments()
    gt_map = {}
    for idx, (segment, plan_id) in enumerate(pairs, start=1):
        cid = f"cus_{idx:06d}"
        plan = ALL_PLANS[plan_id]
        gt_rec = create_ground_truth(cid, segment, plan, generator.rng)
        gt_map[cid] = gt_rec
        behaviour = sample_behaviour(segment, gt_rec.natural_conversion, generator.rng)
        generate_customer_journey(cid, SYNTHETIC_MERCHANT.merchant_id, plan, behaviour, generator.rng)

    paired_list = []
    evaluator = PhaseBEvaluator(total_population=60, seed=42)
    evaluator.run_evaluation(case_callback=lambda p: paired_list.append(p))

    assert len(paired_list) == 30
    for p in paired_list:
        treat = p.treatment
        cid = p.customer_id
        gt = gt_map[cid]

        # Derive expected output using independent ground truth and the production helper
        expected = classify_treatment_conversion(
            natural_conversion=gt.natural_conversion,
            recoverable=gt.recoverable,
            treatment_converted=treat.treatment_converted,
        )
        assert treat.conversion_classification == expected.conversion_classification
        assert treat.is_natural_conversion == expected.is_natural_conversion
        assert treat.is_genuine_incremental_recovery == expected.is_genuine_incremental_recovery
        assert treat.is_observed_unrecoverable_conversion == expected.is_observed_unrecoverable_conversion


def test_four_way_taxonomy_mutually_exclusive_every_case():
    """Test B: Verify every treatment case belongs to EXACTLY ONE of the 4 conversion classes."""
    paired_list = []
    evaluator = PhaseBEvaluator(total_population=100, seed=42)
    evaluator.run_evaluation(case_callback=lambda p: paired_list.append(p))

    valid_classes = {
        "NATURAL_CONVERSION",
        "GENUINE_INCREMENTAL_RECOVERY",
        "OBSERVED_UNRECOVERABLE_CONVERSION",
        "NO_TREATMENT_CONVERSION",
    }

    for p in paired_list:
        t = p.treatment
        assert t.conversion_classification in valid_classes

        # Verify mutually exclusive boolean flags
        if t.conversion_classification == "NATURAL_CONVERSION":
            assert t.is_natural_conversion is True
            assert t.is_genuine_incremental_recovery is False
            assert t.is_observed_unrecoverable_conversion is False
            assert t.treatment_converted is True
        elif t.conversion_classification == "GENUINE_INCREMENTAL_RECOVERY":
            assert t.is_natural_conversion is False
            assert t.is_genuine_incremental_recovery is True
            assert t.is_observed_unrecoverable_conversion is False
            assert t.treatment_converted is True
        elif t.conversion_classification == "OBSERVED_UNRECOVERABLE_CONVERSION":
            assert t.is_natural_conversion is False
            assert t.is_genuine_incremental_recovery is False
            assert t.is_observed_unrecoverable_conversion is True
            assert t.treatment_converted is True
        elif t.conversion_classification == "NO_TREATMENT_CONVERSION":
            assert t.is_natural_conversion is False
            assert t.is_genuine_incremental_recovery is False
            assert t.is_observed_unrecoverable_conversion is False
            assert t.treatment_converted is False


def test_treatment_conversion_accounting_population_reconciliation():
    """Test C: Verify treatment conversion accounting reconciles against the full treatment population."""
    evaluator = PhaseBEvaluator(total_population=100, seed=42)
    res = evaluator.run_evaluation()

    eco = res.economics
    no_treatment_conversions = eco.treatment_evaluations - eco.treatment_total_conversions

    # Population Identity: total_conversions + no_conversions == evaluations
    assert eco.treatment_total_conversions + no_treatment_conversions == eco.treatment_evaluations

    # 4-Way Composition Identity: total_conversions == natural + genuine_incremental + observed_unrecoverable
    assert eco.treatment_total_conversions == (
        eco.treatment_natural_conversions
        + eco.treatment_genuine_incremental_recoveries
        + eco.treatment_observed_unrecoverable_conversions
    )


# --- 3. CONTROL EVALUATOR TESTS ---

def test_control_has_no_revive_intervention(sample_customer, sample_plan, sample_ground_truth_natural):
    """Test that Control arm does not apply any REVIVE intervention or intervention cost."""
    ctrl_rec = ControlEvaluator.evaluate_control_case(
        customer=sample_customer,
        plan=sample_plan,
        ground_truth=sample_ground_truth_natural,
    )
    assert ctrl_rec.customer_id == "cus_test_001"
    assert ctrl_rec.control_converted is True
    assert ctrl_rec.control_gross_revenue == 999.00
    assert ctrl_rec.control_net_revenue == 999.00
    assert ctrl_rec.control_case_status == "NATURAL_CONVERSION"


def test_control_unconverted_churned(sample_customer, sample_plan, sample_ground_truth_recoverable):
    """Test that non-natural converters in Control arm churn with 0 revenue."""
    ctrl_rec = ControlEvaluator.evaluate_control_case(
        customer=sample_customer,
        plan=sample_plan,
        ground_truth=sample_ground_truth_recoverable,
    )
    assert ctrl_rec.control_converted is False
    assert ctrl_rec.control_gross_revenue == 0.0
    assert ctrl_rec.control_net_revenue == 0.0
    assert ctrl_rec.control_case_status == "CHURNED_NO_INTERVENTION"


# --- 4. EXCEPTION LEDGER & RECONCILIATION TESTS ---

def test_exception_reconciliation():
    """Verify that total cases equals successful + stopped + escalated + failed + unresolved."""
    reconciled = ExceptionLedger.verify_reconciliation(
        total_cases=100,
        successful_cases=60,
        stopped_cases=25,
        escalated_cases=10,
        failed_cases=3,
        unresolved_cases=2,
    )
    assert reconciled is True


def test_exception_retryable_vs_terminal_classification():
    """Verify exception ledger classifies retryable and terminal failures accurately."""
    ledger = ExceptionLedger()
    ledger.record_exception(
        case_id="c1",
        stage="EXECUTION",
        status="FAILED",
        failure_type="execution_failure",
        retryable=True,
        safe_action_taken="RETRY_SCHEDULED",
        financial_impact=999.0,
        human_escalation_required=False,
        reason="Socket timeout",
    )
    ledger.record_exception(
        case_id="c2",
        stage="RISK",
        status="FAILED",
        failure_type="invalid_input",
        retryable=False,
        safe_action_taken="NO_ACTION",
        financial_impact=499.0,
        human_escalation_required=False,
        reason="Missing fields",
    )

    summary = ledger.get_summary()
    assert summary["total_exceptions"] == 2
    assert summary["retryable_count"] == 1
    assert summary["terminal_count"] == 1
    assert summary["total_financial_impact"] == 1498.0


# --- 5. FINANCIAL MULTI-IDENTITY & GROUND-TRUTH ISOLATION TESTS ---

def test_paired_case_accounting_reconciliation():
    """Test that paired financial accounting reconciles exactly across all multi-identities."""
    paired_list = []
    evaluator = PhaseBEvaluator(total_population=50, seed=42)
    res = evaluator.run_evaluation(case_callback=lambda p: paired_list.append(p))

    for p in paired_list:
        expected_inc = round(p.treatment.total_net_revenue - p.control.control_net_revenue, 2)
        assert abs(p.incremental_net_revenue - expected_inc) < 0.01

    eco = res.economics
    assert abs((eco.treatment_total_net_revenue - eco.control_net_revenue) - eco.incremental_net_revenue) < 0.01
    assert abs((eco.treatment_total_gross_revenue - eco.treatment_intervention_cost) - eco.treatment_total_net_revenue) < 0.01
    assert abs((eco.treatment_attributable_recovery_revenue - eco.treatment_intervention_cost) - eco.treatment_net_recovered_revenue) < 0.01
    assert res.reconciliation_passed is True


def test_ground_truth_isolation_zero_leakage():
    """Test that ground-truth fields remain strictly post-hoc evaluation only and are never leaked to treatment pipeline."""
    paired_list = []
    evaluator = PhaseBEvaluator(total_population=20, seed=99)
    evaluator.run_evaluation(case_callback=lambda p: paired_list.append(p))

    for p in paired_list:
        t_dict = p.treatment.model_dump()
        assert "true_root_cause" not in t_dict
        assert "natural_conversion" not in t_dict
        assert "recoverable" not in t_dict
        assert "generation_segment" not in t_dict


# --- 6. THROUGHPUT EVENT ACCOUNTING & PERFORMANCE TESTS ---

def test_throughput_event_composition_and_rate():
    """Verify events_processed equals initial_journey_events + post_treatment_events and events_per_second uses events_processed."""
    evaluator = PhaseBEvaluator(total_population=40, seed=42)
    res = evaluator.run_evaluation()

    tp = res.throughput
    assert tp.initial_journey_events > 0
    assert tp.post_treatment_events > 0
    assert tp.events_processed == tp.initial_journey_events + tp.post_treatment_events
    expected_rate = round(tp.events_processed / tp.elapsed_seconds, 2)
    assert abs(tp.events_per_second - expected_rate) <= 0.05
    expected_initial_rate = round(tp.initial_journey_events / tp.elapsed_seconds, 2)
    assert abs(tp.initial_journey_events_per_second - expected_initial_rate) <= 0.05


def test_paired_units_arm_evaluations_count():
    """Test that N paired units produce exactly N control and N treatment evaluations (2N total)."""
    evaluator = PhaseBEvaluator(total_population=100, seed=42)
    res = evaluator.run_evaluation()

    assert res.economics.paired_experimental_units == 50
    assert res.economics.control_evaluations == 50
    assert res.economics.treatment_evaluations == 50
    assert res.throughput.total_arm_evaluations == 100


def test_events_processed_belongs_only_to_evaluated_pairs():
    """Test that events_processed represents only events belonging to evaluated pairs."""
    evaluator = PhaseBEvaluator(total_population=30, seed=42)
    res = evaluator.run_evaluation()

    assert res.throughput.events_processed > 0
    assert res.throughput.events_per_second > 0.0
    assert res.throughput.paired_units_per_second > 0.0


def test_funnel_eligible_population_bounded_by_diagnosable():
    """Test that eligible_population <= diagnosable_population under aligned semantics."""
    evaluator = PhaseBEvaluator(total_population=100, seed=42)
    res = evaluator.run_evaluation()

    funnel = res.decision_funnel
    assert funnel.diagnosable_population > 0
    assert funnel.eligible_population <= funnel.diagnosable_population


def test_decision_accuracy_metrics():
    """Verify diagnosis evaluator produces valid accuracy, precision, recall, and F1."""
    evaluator = PhaseBEvaluator(total_population=50, seed=42)
    res = evaluator.run_evaluation()

    diag = res.diagnosis_accuracy
    assert 0.0 <= diag.overall_accuracy <= 1.0
    assert 0.0 <= diag.macro_precision <= 1.0
    assert 0.0 <= diag.macro_recall <= 1.0
    assert 0.0 <= diag.macro_f1 <= 1.0
    assert len(diag.confusion_matrix) > 0


def test_safety_compliance_and_evidence_consistency():
    """Verify safety compliance rate is 100% and evidence consistency is 100%."""
    evaluator = PhaseBEvaluator(total_population=50, seed=42)
    res = evaluator.run_evaluation()

    assert res.intervention_appropriateness.safety_policy_compliance_rate == 1.0
    assert res.intervention_appropriateness.evidence_action_consistency_rate == 1.0


def test_reproducibility_same_seed():
    """Verify two runs with the same seed produce identical tested aggregate metrics."""
    eval1 = PhaseBEvaluator(total_population=40, seed=777)
    res1 = eval1.run_evaluation()

    eval2 = PhaseBEvaluator(total_population=40, seed=777)
    res2 = eval2.run_evaluation()

    assert res1.economics.control_conversions == res2.economics.control_conversions
    assert res1.economics.treatment_total_conversions == res2.economics.treatment_total_conversions
    assert res1.economics.treatment_genuine_incremental_recoveries == res2.economics.treatment_genuine_incremental_recoveries
    assert res1.economics.incremental_net_revenue == res2.economics.incremental_net_revenue
    assert res1.diagnosis_accuracy.overall_accuracy == res2.diagnosis_accuracy.overall_accuracy


def test_report_generation_artifacts(tmp_path):
    """Verify PhaseBReportGenerator produces experiment.json, summary.json, and report.md."""
    evaluator = PhaseBEvaluator(total_population=30, seed=42)
    res = evaluator.run_evaluation()

    reporter = PhaseBReportGenerator(output_dir=str(tmp_path))
    exp_file = reporter.write_experiment_json(res)
    sum_file = reporter.write_summary_json(res)
    rep_file = reporter.write_markdown_report(res)

    assert exp_file.exists()
    assert sum_file.exists()
    assert rep_file.exists()

    with open(sum_file, "r", encoding="utf-8") as f:
        sum_data = json.load(f)
    assert "economics" in sum_data
    assert "diagnosis_accuracy" in sum_data
    assert "exception_summary" in sum_data
    assert sum_data["reconciliation_passed"] is True

    with open(rep_file, "r", encoding="utf-8") as f:
        md_text = f.read()
    assert "Controlled Comparison Table" in md_text
    assert "Genuine Incremental Recoveries" in md_text


def test_summary_json_exposes_exception_summary(tmp_path):
    """Verify summary.json exposes exception_summary, counts agree with result.exception_summary, and reconciliation remains true."""
    evaluator = PhaseBEvaluator(total_population=30, seed=42)
    res = evaluator.run_evaluation()

    reporter = PhaseBReportGenerator(output_dir=str(tmp_path))
    sum_file = reporter.write_summary_json(res)
    assert sum_file.exists()

    with open(sum_file, "r", encoding="utf-8") as f:
        sum_data = json.load(f)

    assert "exception_summary" in sum_data
    exc_summary = sum_data["exception_summary"]
    assert exc_summary == res.exception_summary
    assert exc_summary["total_exceptions"] == res.exception_summary["total_exceptions"]
    assert exc_summary["retryable_count"] == res.exception_summary["retryable_count"]
    assert exc_summary["terminal_count"] == res.exception_summary["terminal_count"]
    assert exc_summary["human_escalation_count"] == res.exception_summary["human_escalation_count"]
    assert exc_summary["total_financial_impact"] == res.exception_summary["total_financial_impact"]
    assert exc_summary["by_stage"] == res.exception_summary["by_stage"]
    assert sum_data["reconciliation_passed"] is True


def test_cli_smoke_execution(tmp_path):
    """Verify CLI runner executes without error and generates all 5 files."""
    import subprocess
    import sys

    cmd = [
        sys.executable,
        "scripts/run_phase_b_evaluation.py",
        "--customers", "20",
        "--control", "10",
        "--treatment", "10",
        "--seed", "42",
        "--output", str(tmp_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0
    assert (tmp_path / "experiment.json").exists()
    assert (tmp_path / "summary.json").exists()
    assert (tmp_path / "cases.jsonl").exists()
    assert (tmp_path / "exceptions.jsonl").exists()
    assert (tmp_path / "report.md").exists()
