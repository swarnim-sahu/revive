"""
READ-ONLY MANUAL BEHAVIORAL TEST — REVIVE PHASE 5 INTERVENTION DECISION ENGINE

Exercises the real InterventionEngine.decide_intervention execution path across
behavioral scenarios S1-S8 and asserts actual behavioral invariants.

Usage:
    python scripts/manual_test_phase5.py
"""

from decimal import Decimal
from typing import Any, Dict
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.models.entities import Plan
from app.risk.scoring import ScoredCustomer
from app.risk.feature_registry import FORBIDDEN_GROUND_TRUTH_FIELDS
from app.diagnosis.schemas import (
    Actionability,
    ConfidenceTier,
    CustomerDiagnosis,
    DiagnosisCategory,
    EvidenceCategory,
    EvidenceItem,
)
from app.intervention.config import DEFAULT_INTERVENTION_CONFIG
from app.intervention.engine import InterventionEngine
from app.intervention.evaluation import InterventionEvaluator
from app.intervention.schemas import InterventionAction, InterventionDecision


def make_test_plan() -> Plan:
    return Plan(
        plan_id="pro",
        name="Pro Plan",
        price=Decimal("4999.00"),
        currency="INR",
        billing_interval="month",
    )


def make_scored_customer(
    customer_id: str = "cus_manual_001",
    risk_score: float = 0.80,
    revenue_at_risk: Decimal = Decimal("3999.20"),
) -> ScoredCustomer:
    return ScoredCustomer(
        customer_id=customer_id,
        prediction_timestamp="2026-08-04T10:00:00+00:00",
        risk_score=risk_score,
        risk_tier="CRITICAL" if risk_score >= 0.80 else "MEDIUM",
        plan_id="pro",
        plan_price=Decimal("4999.00"),
        revenue_at_risk=revenue_at_risk,
    )


def assert_no_ground_truth_leakage(feature_record: Dict[str, Any]) -> None:
    for forbidden in FORBIDDEN_GROUND_TRUTH_FIELDS:
        assert (
            forbidden not in feature_record
        ), f"Ground-truth leakage detected: field '{forbidden}' found in feature_record!"


def check_test_result(test_name: str, passed: bool, details: str = "") -> bool:
    status = "[PASS]" if passed else "[FAIL]"
    print(f"{status} {test_name}")
    if details:
        print(f"       Details: {details}")
    return passed


def main() -> None:
    print("=" * 70)
    print("  REVIVE PHASE 5 — REAL BEHAVIORAL MANUAL SANITY TEST")
    print("=" * 70)

    engine = InterventionEngine()
    plan = make_test_plan()
    results = []

    # ---------------------------------------------------------------
    # S1 — VALID LOW-INTENT CASE
    # ---------------------------------------------------------------
    print("\n--- Scenario S1: Valid LOW_INTENT Case ---")
    sc = make_scored_customer("cus_s1", risk_score=0.80, revenue_at_risk=Decimal("800.80"))
    ev_item = EvidenceItem(
        evidence_type=EvidenceCategory.SESSION_ACTIVITY,
        strength=1.0,
        description="Recorded 1 session during trial period",
    )
    diag = CustomerDiagnosis(
        customer_id=sc.customer_id,
        prediction_timestamp=sc.prediction_timestamp,
        risk_score=sc.risk_score,
        risk_tier=sc.risk_tier,
        diagnosis=DiagnosisCategory.LOW_INTENT,
        confidence=1.0,
        confidence_tier=ConfidenceTier.VERY_HIGH,
        actionability=Actionability.CANDIDATE,
        candidate_causes=[],
        supporting_evidence=[ev_item],
        explanation="Low product intent",
    )
    feat = {"hours_until_trial_expiry": 100.0}
    assert_no_ground_truth_leakage(feat)

    decision_s1 = engine.decide_intervention(sc, diag, plan, feat)
    s1_ok = (
        decision_s1.selected_action == InterventionAction.PRODUCT_GUIDANCE
        and decision_s1.eligibility_status == "ELIGIBLE"
        and decision_s1.expected_value > Decimal("0.00")
        and len(decision_s1.supporting_evidence) > 0
        and InterventionEvaluator.verify_safety_compliance_single(decision_s1, diagnosis=diag, feature_record=feat)
        and InterventionEvaluator.verify_evidence_action_consistency(decision_s1, diagnosis=diag)
    )
    results.append(
        check_test_result(
            "S1: Valid LOW_INTENT produces PRODUCT_GUIDANCE with positive EV & 100% safety",
            s1_ok,
            f"Action={decision_s1.selected_action.value}, Status={decision_s1.eligibility_status}, EV=Rs.{decision_s1.expected_value}",
        )
    )

    # ---------------------------------------------------------------
    # S2 — ALREADY CONVERTED
    # ---------------------------------------------------------------
    print("\n--- Scenario S2: ALREADY_CONVERTED ---")
    sc = make_scored_customer("cus_s2")
    diag = CustomerDiagnosis(
        customer_id=sc.customer_id,
        prediction_timestamp=sc.prediction_timestamp,
        risk_score=sc.risk_score,
        risk_tier=sc.risk_tier,
        diagnosis=DiagnosisCategory.ALREADY_CONVERTED,
        confidence=1.0,
        confidence_tier=ConfidenceTier.VERY_HIGH,
        actionability=Actionability.NONE,
        candidate_causes=[],
        supporting_evidence=[],
        explanation="Customer already converted before snapshot",
    )
    feat = {}
    assert_no_ground_truth_leakage(feat)

    decision_s2 = engine.decide_intervention(sc, diag, plan, feat)
    s2_ok = (
        decision_s2.selected_action == InterventionAction.NO_ACTION
        and decision_s2.eligibility_status == "INELIGIBLE"
        and decision_s2.expected_value == Decimal("0.00")
        and InterventionEvaluator.verify_safety_compliance_single(decision_s2, diagnosis=diag, feature_record=feat)
    )
    results.append(
        check_test_result(
            "S2: ALREADY_CONVERTED strictly produces NO_ACTION and INELIGIBLE status",
            s2_ok,
            f"Action={decision_s2.selected_action.value}, Status={decision_s2.eligibility_status}, Reason='{decision_s2.decision_reason}'",
        )
    )

    # ---------------------------------------------------------------
    # S3 — PAYMENT RECOVERY WITHOUT PAYMENT EVIDENCE
    # ---------------------------------------------------------------
    print("\n--- Scenario S3: PAYMENT_RECOVERY Without Payment Evidence ---")
    sc = make_scored_customer("cus_s3")
    ev_item = EvidenceItem(
        evidence_type=EvidenceCategory.SESSION_ACTIVITY,  # Session evidence only, NO payment evidence!
        strength=1.0,
        description="Recorded 1 session",
    )
    diag = CustomerDiagnosis(
        customer_id=sc.customer_id,
        prediction_timestamp=sc.prediction_timestamp,
        risk_score=sc.risk_score,
        risk_tier=sc.risk_tier,
        diagnosis=DiagnosisCategory.PAYMENT_FRICTION,
        confidence=0.80,
        confidence_tier=ConfidenceTier.HIGH,
        actionability=Actionability.CANDIDATE,
        candidate_causes=[],
        supporting_evidence=[ev_item],
        explanation="Payment friction claimed without payment evidence",
    )
    feat = {}
    assert_no_ground_truth_leakage(feat)

    decision_s3 = engine.decide_intervention(sc, diag, plan, feat)
    pay_rec_cand = next(c for c in decision_s3.candidate_scores if c.action == InterventionAction.PAYMENT_RECOVERY)
    s3_ok = (
        decision_s3.selected_action != InterventionAction.PAYMENT_RECOVERY
        and pay_rec_cand.is_eligible is False
        and "Rule S2 Violation" in (pay_rec_cand.disqualification_reason or "")
    )
    results.append(
        check_test_result(
            "S3: PAYMENT_RECOVERY is disqualified by Rule S2 when payment evidence is missing",
            s3_ok,
            f"Selected={decision_s3.selected_action.value}, PayRecEligible={pay_rec_cand.is_eligible}, Reason='{pay_rec_cand.disqualification_reason}'",
        )
    )

    # ---------------------------------------------------------------
    # S4 — CHECKOUT ASSISTANCE WITHOUT CHECKOUT EVIDENCE
    # ---------------------------------------------------------------
    print("\n--- Scenario S4: CHECKOUT_ASSISTANCE Without Checkout Evidence ---")
    sc = make_scored_customer("cus_s4")
    ev_item = EvidenceItem(
        evidence_type=EvidenceCategory.CHECKOUT_ABANDONED,  # Abandoned ONLY, NOT CHECKOUT_STARTED!
        strength=1.0,
        description="Checkout abandoned recorded",
    )
    diag = CustomerDiagnosis(
        customer_id=sc.customer_id,
        prediction_timestamp=sc.prediction_timestamp,
        risk_score=sc.risk_score,
        risk_tier=sc.risk_tier,
        diagnosis=DiagnosisCategory.CHECKOUT_ABANDONMENT,
        confidence=0.85,
        confidence_tier=ConfidenceTier.HIGH,
        actionability=Actionability.CANDIDATE,
        candidate_causes=[],
        supporting_evidence=[ev_item],
        explanation="Checkout abandoned",
    )
    feat = {}
    assert_no_ground_truth_leakage(feat)

    decision_s4 = engine.decide_intervention(sc, diag, plan, feat)
    chk_cand = next(c for c in decision_s4.candidate_scores if c.action == InterventionAction.CHECKOUT_ASSISTANCE)
    s4_ok = (
        decision_s4.selected_action != InterventionAction.CHECKOUT_ASSISTANCE
        and chk_cand.is_eligible is False
        and "Rule S3 Violation" in (chk_cand.disqualification_reason or "")
    )
    results.append(
        check_test_result(
            "S4: CHECKOUT_ASSISTANCE is disqualified by Rule S3 when CHECKOUT_STARTED is missing",
            s4_ok,
            f"Selected={decision_s4.selected_action.value}, ChkEligible={chk_cand.is_eligible}, Reason='{chk_cand.disqualification_reason}'",
        )
    )

    # ---------------------------------------------------------------
    # S5 — INSUFFICIENT EVIDENCE
    # ---------------------------------------------------------------
    print("\n--- Scenario S5: INSUFFICIENT_EVIDENCE ---")
    sc = make_scored_customer("cus_s5")
    diag = CustomerDiagnosis(
        customer_id=sc.customer_id,
        prediction_timestamp=sc.prediction_timestamp,
        risk_score=sc.risk_score,
        risk_tier=sc.risk_tier,
        diagnosis=DiagnosisCategory.INSUFFICIENT_EVIDENCE,
        confidence=0.0,
        confidence_tier=ConfidenceTier.LOW,
        actionability=Actionability.NONE,
        candidate_causes=[],
        supporting_evidence=[],
        explanation="Insufficient evidence to ground diagnosis",
    )
    feat = {}
    assert_no_ground_truth_leakage(feat)

    decision_s5 = engine.decide_intervention(sc, diag, plan, feat)
    s5_ok = (
        decision_s5.selected_action == InterventionAction.NO_ACTION
        and decision_s5.eligibility_status == "INELIGIBLE"
        and decision_s5.expected_value == Decimal("0.00")
        and InterventionEvaluator.verify_safety_compliance_single(decision_s5, diagnosis=diag, feature_record=feat)
    )
    results.append(
        check_test_result(
            "S5: INSUFFICIENT_EVIDENCE strictly produces NO_ACTION and INELIGIBLE status",
            s5_ok,
            f"Action={decision_s5.selected_action.value}, Status={decision_s5.eligibility_status}, Reason='{decision_s5.decision_reason}'",
        )
    )

    # ---------------------------------------------------------------
    # S6 — MIXED / AMBIGUOUS DIAGNOSIS
    # ---------------------------------------------------------------
    print("\n--- Scenario S6: MIXED_SIGNALS / Ambiguous Diagnosis ---")
    sc = make_scored_customer("cus_s6", risk_score=0.85, revenue_at_risk=Decimal("3500.00"))
    diag = CustomerDiagnosis(
        customer_id=sc.customer_id,
        prediction_timestamp=sc.prediction_timestamp,
        risk_score=sc.risk_score,
        risk_tier=sc.risk_tier,
        diagnosis=DiagnosisCategory.MIXED_SIGNALS,
        confidence=0.40,
        confidence_tier=ConfidenceTier.LOW,
        actionability=Actionability.REQUIRES_REVIEW,
        candidate_causes=[],
        supporting_evidence=[],
        explanation="Multiple ambiguous signals",
    )
    feat = {}
    assert_no_ground_truth_leakage(feat)

    decision_s6 = engine.decide_intervention(sc, diag, plan, feat)
    s6_ok = (
        decision_s6.selected_action == InterventionAction.HUMAN_REVIEW
        and decision_s6.eligibility_status == "ESCALATED"
        and InterventionEvaluator.verify_safety_compliance_single(decision_s6, diagnosis=diag, feature_record=feat)
    )
    results.append(
        check_test_result(
            "S6: MIXED_SIGNALS + High Revenue escalates to HUMAN_REVIEW with ESCALATED status",
            s6_ok,
            f"Action={decision_s6.selected_action.value}, Status={decision_s6.eligibility_status}, Reason='{decision_s6.decision_reason}'",
        )
    )

    # ---------------------------------------------------------------
    # S7 — NO_ACTION
    # ---------------------------------------------------------------
    print("\n--- Scenario S7: Low Risk NO_ACTION ---")
    sc = make_scored_customer("cus_s7", risk_score=0.15, revenue_at_risk=Decimal("0.00"))
    diag = CustomerDiagnosis(
        customer_id=sc.customer_id,
        prediction_timestamp=sc.prediction_timestamp,
        risk_score=sc.risk_score,
        risk_tier="LOW",
        diagnosis=DiagnosisCategory.NO_MEANINGFUL_RISK,
        confidence=1.0,
        confidence_tier=ConfidenceTier.VERY_HIGH,
        actionability=Actionability.NONE,
        candidate_causes=[],
        supporting_evidence=[],
        explanation="Low risk customer",
    )
    feat = {}
    assert_no_ground_truth_leakage(feat)

    decision_s7 = engine.decide_intervention(sc, diag, plan, feat)
    s7_ok = (
        decision_s7.selected_action == InterventionAction.NO_ACTION
        and decision_s7.eligibility_status == "INELIGIBLE"
        and InterventionEvaluator.verify_safety_compliance_single(decision_s7, diagnosis=diag, feature_record=feat)
    )
    results.append(
        check_test_result(
            "S7: Low risk score (< 0.30) strictly produces NO_ACTION and INELIGIBLE status",
            s7_ok,
            f"Action={decision_s7.selected_action.value}, Status={decision_s7.eligibility_status}, Reason='{decision_s7.decision_reason}'",
        )
    )

    # ---------------------------------------------------------------
    # S8 — DETERMINISM
    # ---------------------------------------------------------------
    print("\n--- Scenario S8: Execution Determinism ---")
    sc_det = make_scored_customer("cus_s8", risk_score=0.80, revenue_at_risk=Decimal("800.80"))
    ev_item_det = EvidenceItem(
        evidence_type=EvidenceCategory.SESSION_ACTIVITY,
        strength=1.0,
        description="Recorded 1 session during trial",
    )
    diag_det = CustomerDiagnosis(
        customer_id=sc_det.customer_id,
        prediction_timestamp=sc_det.prediction_timestamp,
        risk_score=sc_det.risk_score,
        risk_tier=sc_det.risk_tier,
        diagnosis=DiagnosisCategory.LOW_INTENT,
        confidence=1.0,
        confidence_tier=ConfidenceTier.VERY_HIGH,
        actionability=Actionability.CANDIDATE,
        candidate_causes=[],
        supporting_evidence=[ev_item_det],
        explanation="Low intent",
    )
    feat_det = {"hours_until_trial_expiry": 100.0}

    d_run1 = engine.decide_intervention(sc_det, diag_det, plan, feat_det)
    d_run2 = engine.decide_intervention(sc_det, diag_det, plan, feat_det)

    det_ok = (
        d_run1.selected_action == d_run2.selected_action
        and d_run1.eligibility_status == d_run2.eligibility_status
        and d_run1.expected_value == d_run2.expected_value
        and d_run1.decision_reason == d_run2.decision_reason
        and d_run1.model_dump_json() == d_run2.model_dump_json()
    )
    results.append(
        check_test_result(
            "S8: Repeated execution produces 100% identical InterventionDecision JSON payloads",
            det_ok,
            f"Run1_Action={d_run1.selected_action.value}, Run2_Action={d_run2.selected_action.value}",
        )
    )

    # ---------------------------------------------------------------
    # FINAL SUMMARY
    # ---------------------------------------------------------------
    print("\n" + "=" * 70)
    passed = sum(results)
    total = len(results)
    print(f"MANUAL BEHAVIORAL TEST RESULT: {passed}/{total} SCENARIOS PASSED")

    if passed == total:
        print("[SUCCESS] All Phase 5 manual behavioral scenarios passed successfully.")
    else:
        print("[FAILURE] One or more Phase 5 behavioral scenarios failed.")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()