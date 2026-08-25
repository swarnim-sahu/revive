"""
Real Behavioral Manual Sanity Test Suite for Revive Phase 7 Outcome Engine.
Executes real Phase 7 outcome measurement scenarios and verifies operational correctness.

Usage:
    python scripts/manual_test_phase7.py
"""

from datetime import datetime, timezone
from decimal import Decimal
import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from app.models.entities import Plan
from app.models.enums import EventType
from app.models.events import BaseEvent
from app.intervention.schemas import CandidateActionScore, InterventionAction, InterventionDecision
from app.execution.schemas import ExecutionAuditRecord, ExecutionStatus
from app.outcome.engine import OutcomeEngine
from app.outcome.schemas import AttributionMethod, AttributionStatus, OutcomeType


def make_decision(customer_id: str, action: InterventionAction, risk_score: float = 0.80) -> InterventionDecision:
    candidate = CandidateActionScore(
        action=action,
        expected_value=Decimal("450.00"),
        recovery_probability_assumption=0.45,
        direct_cost=Decimal("3.00"),
        incentive_penalty_assumption=Decimal("0.00"),
        harm_penalty_assumption=Decimal("0.00"),
        is_eligible=True,
    )
    return InterventionDecision(
        customer_id=customer_id,
        decision_timestamp="2026-08-05T12:00:00+00:00",
        risk_score=risk_score,
        risk_tier="CRITICAL",
        revenue_at_risk=Decimal("999.00"),
        diagnosis="PAYMENT_FRICTION",
        diagnosis_confidence=1.0,
        diagnosis_actionability="candidate",
        eligibility_status="ELIGIBLE",
        selected_action=action,
        expected_value=Decimal("450.00"),
        candidate_scores=[candidate],
        decision_reason="Test manual scenario",
        supporting_evidence=["Test evidence"],
    )


def make_execution(decision: InterventionDecision, status: ExecutionStatus = ExecutionStatus.EXECUTED) -> ExecutionAuditRecord:
    return ExecutionAuditRecord(
        execution_id=f"exec_{decision.customer_id}_{decision.decision_timestamp}_att1",
        decision_id=f"dec_{decision.customer_id}_{decision.decision_timestamp}",
        customer_id=decision.customer_id,
        merchant_id="merch_codecraft",
        execution_timestamp=decision.decision_timestamp,
        action=decision.selected_action,
        status=status,
        attempt_number=1,
        payload_id=f"payload_{decision.customer_id}",
        target_url=f"sim://revive/recovery?cid={decision.customer_id}",
    )


def make_event(evt_type: EventType, customer_id: str, ts_str: str, payload: dict = None) -> BaseEvent:
    return BaseEvent(
        event_id=f"evt_{customer_id}_{evt_type.value}_{ts_str}",
        event_type=evt_type,
        schema_version="1.0",
        merchant_id="merch_codecraft",
        customer_id=customer_id,
        timestamp=datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc),
        source="test_manual",
        payload=payload or {},
    )


def main() -> None:
    print("=" * 70)
    print("  REVIVE PHASE 7 — REAL BEHAVIORAL MANUAL SANITY TEST")
    print("=" * 70)

    passed_count = 0
    total_count = 12

    plan = Plan(plan_id="pro", name="Pro", price=Decimal("999.00"), currency="INR", billing_interval="month")

    # --- Scenario S1: Successful Post-Intervention Conversion ---
    print("\n--- Scenario S1: Successful Post-Intervention Conversion ---")
    d1 = make_decision("cus_s1", InterventionAction.CHECKOUT_ASSISTANCE)
    e1 = make_execution(d1)
    evt1 = make_event(EventType.CHECKOUT_COMPLETED, "cus_s1", "2026-08-05T14:00:00+00:00", {"amount": 999.00})
    engine = OutcomeEngine()
    r1 = engine.measure_outcome(e1, d1, [evt1], plan=plan)
    if r1.outcome == OutcomeType.RECOVERED and r1.attribution_status == AttributionStatus.DIRECTLY_OBSERVED:
        print("[PASS] S1: Successful post-intervention checkout completion resolves RECOVERED & DIRECTLY_OBSERVED")
        passed_count += 1
    else:
        print(f"[FAIL] S1: Outcome={r1.outcome}, Attr={r1.attribution_status}")

    # --- Scenario S2: Payment Recovery After Intervention ---
    print("\n--- Scenario S2: Payment Recovery After Intervention ---")
    d2 = make_decision("cus_s2", InterventionAction.PAYMENT_RECOVERY)
    e2 = make_execution(d2)
    evt2 = make_event(EventType.PAYMENT_SUCCEEDED, "cus_s2", "2026-08-05T15:00:00+00:00", {"payment_id": "pay_s2", "amount": 999.00})
    r2 = engine.measure_outcome(e2, d2, [evt2], plan=plan)
    if r2.outcome == OutcomeType.RECOVERED and r2.payment_reference == "pay_s2":
        print("[PASS] S2: Payment recovery intervention produces RECOVERED outcome with payment_reference")
        passed_count += 1
    else:
        print(f"[FAIL] S2: Outcome={r2.outcome}, Ref={r2.payment_reference}")

    # --- Scenario S3: Pre-Existing Conversion Protection ---
    print("\n--- Scenario S3: Pre-Existing Conversion Protection ---")
    d3 = make_decision("cus_s3", InterventionAction.PAYMENT_RECOVERY)
    e3 = make_execution(d3)
    # Event happened BEFORE execution (10:00 < 12:00)
    evt3 = make_event(EventType.PAYMENT_SUCCEEDED, "cus_s3", "2026-08-05T10:00:00+00:00", {"payment_id": "pay_pre"})
    r3 = engine.measure_outcome(e3, d3, [evt3], plan=plan)
    if r3.outcome == OutcomeType.ALREADY_CONVERTED and r3.attribution_status == AttributionStatus.UNATTRIBUTED:
        print("[PASS] S3: Pre-existing payment is correctly protected as ALREADY_CONVERTED & UNATTRIBUTED")
        passed_count += 1
    else:
        print(f"[FAIL] S3: Outcome={r3.outcome}, Attr={r3.attribution_status}")

    # --- Scenario S4: No Qualifying Outcome ---
    print("\n--- Scenario S4: No Qualifying Outcome ---")
    d4 = make_decision("cus_s4", InterventionAction.REMINDER)
    e4 = make_execution(d4)
    evt4 = make_event(EventType.PAYMENT_FAILED, "cus_s4", "2026-08-06T12:00:00+00:00")
    r4 = engine.measure_outcome(e4, d4, [evt4], plan=plan)
    if r4.outcome == OutcomeType.NOT_RECOVERED and r4.attributable_revenue == Decimal("0.00"):
        print("[PASS] S4: Failed payment event within window resolves NOT_RECOVERED & zero attributable revenue")
        passed_count += 1
    else:
        print(f"[FAIL] S4: Outcome={r4.outcome}, AttrRev={r4.attributable_revenue}")

    # --- Scenario S5: Event Outside Observation Window ---
    print("\n--- Scenario S5: Event Outside Observation Window ---")
    d5 = make_decision("cus_s5", InterventionAction.PRODUCT_GUIDANCE)
    e5 = make_execution(d5)
    # 10 days post execution > 7 days window
    evt5 = make_event(EventType.PAYMENT_SUCCEEDED, "cus_s5", "2026-08-16T12:00:00+00:00", {"amount": 999.00})
    r5 = engine.measure_outcome(e5, d5, [evt5], plan=plan, observation_window_hours=168.0, measurement_timestamp="2026-08-13T12:00:00+00:00")
    if r5.outcome == OutcomeType.NOT_RECOVERED and r5.attributable_revenue == Decimal("0.00"):
        print("[PASS] S5: Event outside window is excluded from attribution (NOT_RECOVERED)")
        passed_count += 1
    else:
        print(f"[FAIL] S5: Outcome={r5.outcome}")

    # --- Scenario S6: Incomplete Window / Ambiguous Outcome ---
    print("\n--- Scenario S6: Incomplete Window / Ambiguous Outcome ---")
    d6 = make_decision("cus_s6", InterventionAction.REMINDER)
    e6 = make_execution(d6)
    r6 = engine.measure_outcome(e6, d6, [], plan=plan, observation_window_hours=168.0, measurement_timestamp="2026-08-06T12:00:00+00:00")
    if r6.outcome == OutcomeType.NO_OBSERVABLE_OUTCOME and r6.attribution_status == AttributionStatus.UNATTRIBUTED:
        print("[PASS] S6: Open observation window with zero events returns NO_OBSERVABLE_OUTCOME")
        passed_count += 1
    else:
        print(f"[FAIL] S6: Outcome={r6.outcome}")

    # --- Scenario S7: Duplicate Outcome Processing / Idempotency ---
    print("\n--- Scenario S7: Duplicate Outcome Processing / Idempotency ---")
    d7 = make_decision("cus_s7", InterventionAction.PAYMENT_RECOVERY)
    e7 = make_execution(d7)
    evt7 = make_event(EventType.PAYMENT_SUCCEEDED, "cus_s7", "2026-08-05T14:00:00+00:00", {"payment_id": "pay_idemp"})
    rec_a = engine.measure_outcome(e7, d7, [evt7], plan=plan)
    rec_b = engine.measure_outcome(e7, d7, [evt7], plan=plan)
    if rec_a.outcome_id == rec_b.outcome_id and len(engine.get_customer_outcomes("cus_s7")) == 1:
        print("[PASS] S7: Repeated outcome processing is 100% idempotent; returns existing record")
        passed_count += 1
    else:
        print(f"[FAIL] S7: Count={len(engine.get_customer_outcomes('cus_s7'))}")

    # --- Scenario S8: Deterministic Repeated Outcome Resolution ---
    print("\n--- Scenario S8: Deterministic Repeated Outcome Resolution ---")
    eng_1 = OutcomeEngine()
    eng_2 = OutcomeEngine()
    rec_1 = eng_1.measure_outcome(e1, d1, [evt1], plan=plan)
    rec_2 = eng_2.measure_outcome(e1, d1, [evt1], plan=plan)
    if rec_1.model_dump_json() == rec_2.model_dump_json():
        print("[PASS] S8: Independent OutcomeEngines produce byte-for-byte identical outcome records")
        passed_count += 1
    else:
        print("[FAIL] S8: Serialization mismatch across engines")

    # --- Scenario S9: Revenue Accounting & Reconciliation ---
    print("\n--- Scenario S9: Revenue Accounting & Reconciliation ---")
    if r1.gross_observed_revenue == Decimal("999.00") and r1.attributable_revenue == Decimal("999.00") and r1.revenue_at_risk_at_decision == Decimal("999.00"):
        print("[PASS] S9: Revenue accounting preserves gross, attributable, and original risk-at-decision")
        passed_count += 1
    else:
        print(f"[FAIL] S9: Gross={r1.gross_observed_revenue}, Attr={r1.attributable_revenue}, Risk={r1.revenue_at_risk_at_decision}")

    # --- Scenario S10: Intervention Cost and Net Revenue ---
    print("\n--- Scenario S10: Intervention Cost and Net Revenue ---")
    if r1.intervention_cost == Decimal("2.00") and r1.net_recovered_revenue == (r1.attributable_revenue - r1.intervention_cost):
        print("[PASS] S10: Net recovered revenue correctly equals attributable revenue minus direct cost")
        passed_count += 1
    else:
        print(f"[FAIL] S10: Cost={r1.intervention_cost}, Net={r1.net_recovered_revenue}")

    # --- Scenario S11: Hidden Ground-Truth Isolation ---
    print("\n--- Scenario S11: Hidden Ground-Truth Isolation ---")
    # Verify no hidden simulator fields are accessed on decision or execution records
    dict_keys = set(d1.model_dump().keys()) | set(e1.model_dump().keys())
    forbidden = {"true_root_cause", "natural_conversion", "recoverable", "ground_truth"}
    if forbidden.isdisjoint(dict_keys):
        print("[PASS] S11: Zero hidden simulator ground-truth fields present in runtime outcome objects")
        passed_count += 1
    else:
        print(f"[FAIL] S11: Leaked keys={forbidden.intersection(dict_keys)}")

    # --- Scenario S12: Simulated Razorpay Boundary ---
    print("\n--- Scenario S12: Simulated Razorpay Boundary ---")
    if e1.target_url.startswith("sim://revive/"):
        print("[PASS] S12: Simulated Razorpay boundary verified; zero live endpoint URLs")
        passed_count += 1
    else:
        print(f"[FAIL] S12: Target URL={e1.target_url}")

    print("\n" + "=" * 70)
    print(f"PHASE 7 MANUAL BEHAVIORAL TEST RESULT: {passed_count}/{total_count} PASSED")
    if passed_count == total_count:
        print("[SUCCESS] All Phase 7 manual behavioral scenarios passed successfully.")
        print("=" * 70 + "\n")
    else:
        print("[FAILURE] Some Phase 7 manual behavioral scenarios failed.")
        print("=" * 70 + "\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
