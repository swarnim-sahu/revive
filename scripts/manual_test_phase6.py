"""
READ-ONLY MANUAL BEHAVIORAL TEST — REVIVE PHASE 6 EXECUTION ENGINE

Exercises the real ExecutionEngine.execute_decision execution path across
behavioral scenarios S1-S12 and asserts actual behavioral invariants.

Usage:
    python scripts/manual_test_phase6.py
"""

from decimal import Decimal
from typing import Any, Dict, Optional
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.models.entities import Plan
from app.models.enums import EventType
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
from app.intervention.schemas import CandidateActionScore, InterventionAction, InterventionDecision
from app.execution.config import DEFAULT_EXECUTION_CONFIG
from app.execution.dispatcher import TestModeDispatcher
from app.execution.engine import ExecutionEngine
from app.execution.evaluation import ExecutionEvaluator
from app.execution.payloads import PayloadBuilder
from app.execution.schemas import ExecutionAuditRecord, ExecutionStatus, FailureType


def make_decision(
    customer_id: str,
    action: InterventionAction,
    eligibility_status: str = "ELIGIBLE",
    diagnosis: str = "LOW_INTENT",
    timestamp: str = "2026-08-04T10:00:00+00:00",
) -> InterventionDecision:
    candidate = CandidateActionScore(
        action=action,
        expected_value=Decimal("200.00"),
        recovery_probability_assumption=0.25,
        direct_cost=Decimal("0.00"),
        incentive_penalty_assumption=Decimal("0.00"),
        harm_penalty_assumption=Decimal("0.00"),
        is_eligible=True,
    )
    return InterventionDecision(
        customer_id=customer_id,
        decision_timestamp=timestamp,
        risk_score=0.80,
        risk_tier="CRITICAL",
        revenue_at_risk=Decimal("800.80"),
        diagnosis=diagnosis,
        diagnosis_confidence=1.0,
        diagnosis_actionability="candidate" if eligibility_status == "ELIGIBLE" else "none",
        eligibility_status=eligibility_status,
        selected_action=action,
        expected_value=Decimal("200.00"),
        candidate_scores=[candidate],
        decision_reason="Test decision",
        supporting_evidence=["Observed low activity"],
    )


def check_test_result(test_name: str, passed: bool, details: str = "") -> bool:
    status = "[PASS]" if passed else "[FAIL]"
    print(f"{status} {test_name}")
    if details:
        print(f"       Details: {details}")
    return passed


def main() -> None:
    print("=" * 70)
    print("  REVIVE PHASE 6 — REAL BEHAVIORAL MANUAL SANITY TEST")
    print("=" * 70)

    engine = ExecutionEngine()
    results = []

    # ---------------------------------------------------------------
    # S1 — SUCCESSFUL PRODUCT_GUIDANCE
    # ---------------------------------------------------------------
    print("\n--- Scenario S1: Successful PRODUCT_GUIDANCE Dispatch ---")
    d1 = make_decision("cus_p6_s1", InterventionAction.PRODUCT_GUIDANCE)
    rec1 = engine.execute_decision(d1)
    s1_ok = (
        rec1.status == ExecutionStatus.EXECUTED
        and rec1.action == InterventionAction.PRODUCT_GUIDANCE
        and rec1.attempt_number == 1
        and rec1.payload_id is not None
        and "payload_pg_" in rec1.payload_id
    )
    results.append(
        check_test_result(
            "S1: Successful PRODUCT_GUIDANCE produces EXECUTED status & payload ID",
            s1_ok,
            f"Status={rec1.status.value}, Payload={rec1.payload_id}",
        )
    )

    # ---------------------------------------------------------------
    # S2 — SUCCESSFUL CHECKOUT_ASSISTANCE
    # ---------------------------------------------------------------
    print("\n--- Scenario S2: Successful CHECKOUT_ASSISTANCE Dispatch ---")
    d2 = make_decision("cus_p6_s2", InterventionAction.CHECKOUT_ASSISTANCE, diagnosis="CHECKOUT_ABANDONMENT")
    rec2 = engine.execute_decision(d2)
    s2_ok = (
        rec2.status == ExecutionStatus.EXECUTED
        and rec2.action == InterventionAction.CHECKOUT_ASSISTANCE
        and rec2.payload_id is not None
        and "payload_chk_" in rec2.payload_id
    )
    results.append(
        check_test_result(
            "S2: Successful CHECKOUT_ASSISTANCE produces checkout payload",
            s2_ok,
            f"Status={rec2.status.value}, Payload={rec2.payload_id}",
        )
    )

    # ---------------------------------------------------------------
    # S3 — RETRYABLE FAILURE (Succeeds on Attempt 2)
    # ---------------------------------------------------------------
    print("\n--- Scenario S3: Retryable Failure Handling ---")
    d3 = make_decision("cus_p6_s3", InterventionAction.REMINDER)
    def sim_s3(act: InterventionAction, att: int) -> Optional[str]:
        return "Simulated network_timeout" if att == 1 else None

    engine_s3 = ExecutionEngine()
    rec3 = engine_s3.execute_decision(d3, failure_simulator=sim_s3)
    s3_ok = (
        rec3.status == ExecutionStatus.EXECUTED
        and rec3.attempt_number == 2
        and len(engine_s3.audit_logger.get_customer_audit_history("cus_p6_s3")) == 2
    )
    results.append(
        check_test_result(
            "S3: Retryable failure retries and succeeds on attempt 2",
            s3_ok,
            f"Status={rec3.status.value}, Attempt={rec3.attempt_number}",
        )
    )

    # ---------------------------------------------------------------
    # S4 — NON-RETRYABLE FAILURE
    # ---------------------------------------------------------------
    print("\n--- Scenario S4: Non-Retryable Failure Handling ---")
    d4 = make_decision("cus_p6_s4", InterventionAction.REMINDER)
    def sim_s4(act: InterventionAction, att: int) -> Optional[str]:
        return "Malformed payload schema error"

    engine_s4 = ExecutionEngine()
    rec4 = engine_s4.execute_decision(d4, failure_simulator=sim_s4)
    s4_ok = (
        rec4.status in {ExecutionStatus.ESCALATED, ExecutionStatus.NO_ACTION}
        and rec4.failure_type == FailureType.NON_RETRYABLE
        and rec4.attempt_number == 1
    )
    results.append(
        check_test_result(
            "S4: Non-retryable failure halts retries on attempt 1",
            s4_ok,
            f"Status={rec4.status.value}, FailureType={rec4.failure_type.value}",
        )
    )

    # ---------------------------------------------------------------
    # S5 — RETRY EXHAUSTION
    # ---------------------------------------------------------------
    print("\n--- Scenario S5: Retry Exhaustion ---")
    d5 = make_decision("cus_p6_s5", InterventionAction.TRIAL_EXTENSION)
    def sim_s5(act: InterventionAction, att: int) -> Optional[str]:
        return f"Simulated network_timeout_attempt_{att}"

    engine_s5 = ExecutionEngine()
    rec5 = engine_s5.execute_decision(d5, failure_simulator=sim_s5)
    s5_ok = (
        rec5.status == ExecutionStatus.ESCALATED
        and rec5.attempt_number == 3
        and ("Retry" in (rec5.escalation_reason or "") or "failed" in (rec5.escalation_reason or ""))
    )
    results.append(
        check_test_result(
            "S5: Retry budget exhaustion (3 attempts) transitions to ESCALATED",
            s5_ok,
            f"Status={rec5.status.value}, Attempt={rec5.attempt_number}, Reason='{rec5.escalation_reason}'",
        )
    )

    # ---------------------------------------------------------------
    # S6 — FALLBACK ACTION EXECUTION
    # ---------------------------------------------------------------
    print("\n--- Scenario S6: Fallback Action Execution ---")
    d6 = make_decision("cus_p6_s6", InterventionAction.CHECKOUT_ASSISTANCE)
    def sim_s6(act: InterventionAction, att: int) -> Optional[str]:
        return "Simulated gateway_503_service_unavailable" if act == InterventionAction.CHECKOUT_ASSISTANCE else None

    engine_s6 = ExecutionEngine()
    rec6 = engine_s6.execute_decision(d6, failure_simulator=sim_s6)
    s6_ok = (
        rec6.status == ExecutionStatus.EXECUTED
        and rec6.fallback_action == InterventionAction.REMINDER
    )
    results.append(
        check_test_result(
            "S6: Primary action failure executes fallback action (REMINDER)",
            s6_ok,
            f"Status={rec6.status.value}, FallbackAction={rec6.fallback_action.value if rec6.fallback_action else None}",
        )
    )

    # ---------------------------------------------------------------
    # S7 — HUMAN ESCALATION
    # ---------------------------------------------------------------
    print("\n--- Scenario S7: Direct HUMAN_REVIEW Escalation ---")
    d7 = make_decision("cus_p6_s7", InterventionAction.HUMAN_REVIEW, eligibility_status="ESCALATED")
    rec7 = engine.execute_decision(d7)
    s7_ok = (
        rec7.status == ExecutionStatus.ESCALATED
        and rec7.action == InterventionAction.HUMAN_REVIEW
        and rec7.payload_id is None
    )
    results.append(
        check_test_result(
            "S7: HUMAN_REVIEW creates ESCALATED audit record without customer dispatch",
            s7_ok,
            f"Status={rec7.status.value}, Action={rec7.action.value}",
        )
    )

    # ---------------------------------------------------------------
    # S8 — DUPLICATE EXECUTION & COOLDOWN IDEMPOTENCY
    # ---------------------------------------------------------------
    print("\n--- Scenario S8: Cooldown-Aware Idempotency & Duplicate Execution ---")
    engine_s8 = ExecutionEngine()
    d8_a = make_decision("cus_p6_s8", InterventionAction.PRODUCT_GUIDANCE, timestamp="2026-08-04T10:00:00+00:00")
    run1 = engine_s8.execute_decision(d8_a)

    # Exact same decision again
    run2 = engine_s8.execute_decision(d8_a)

    # New decision 10 hours later (inside 72h cooldown)
    d8_b = make_decision("cus_p6_s8", InterventionAction.CHECKOUT_ASSISTANCE, timestamp="2026-08-04T20:00:00+00:00")
    run3 = engine_s8.execute_decision(d8_b)

    # New decision 80 hours later (outside 72h cooldown)
    d8_c = make_decision("cus_p6_s8", InterventionAction.CHECKOUT_ASSISTANCE, timestamp="2026-08-07T18:00:00+00:00")
    run4 = engine_s8.execute_decision(d8_c)

    s8_ok = (
        run1.execution_id == run2.execution_id  # Exact duplicate returns same record
        and run3.status == ExecutionStatus.BLOCKED  # Cooldown blocks 10h decision
        and run4.status == ExecutionStatus.EXECUTED  # 80h decision allowed after cooldown expiry
    )
    results.append(
        check_test_result(
            "S8: Cooldown idempotency blocks active intervention inside 72h window and allows after expiry",
            s8_ok,
            f"ExactDup={run1.execution_id == run2.execution_id}, InsideCooldown={run3.status.value}, PostCooldown={run4.status.value}",
        )
    )

    # ---------------------------------------------------------------
    # S9 — INELIGIBLE DECISION BLOCKED
    # ---------------------------------------------------------------
    print("\n--- Scenario S9: INELIGIBLE Decision Blocked ---")
    d9 = make_decision("cus_p6_s9", InterventionAction.PRODUCT_GUIDANCE, eligibility_status="INELIGIBLE")
    rec9 = engine.execute_decision(d9)
    s9_ok = (
        rec9.status == ExecutionStatus.BLOCKED
        and rec9.failure_type == FailureType.NON_RETRYABLE
    )
    results.append(
        check_test_result(
            "S9: INELIGIBLE decision is BLOCKED by execution authorization guard",
            s9_ok,
            f"Status={rec9.status.value}, Reason='{rec9.failure_reason}'",
        )
    )

    # ---------------------------------------------------------------
    # S10 — NO_ACTION BASELINE
    # ---------------------------------------------------------------
    print("\n--- Scenario S10: NO_ACTION Baseline ---")
    d10 = make_decision("cus_p6_s10", InterventionAction.NO_ACTION, eligibility_status="INELIGIBLE")
    rec10 = engine.execute_decision(d10)
    s10_ok = (
        rec10.status == ExecutionStatus.NO_ACTION
        and rec10.payload_id is None
    )
    results.append(
        check_test_result(
            "S10: NO_ACTION produces NO_ACTION terminal status with zero customer payload",
            s10_ok,
            f"Status={rec10.status.value}",
        )
    )

    # ---------------------------------------------------------------
    # S11 — EXPLICIT DETERMINISTIC REPEATED EXECUTION
    # ---------------------------------------------------------------
    print("\n--- Scenario S11: Deterministic Repeated Execution ---")
    d11 = make_decision("cus_p6_s11", InterventionAction.PRODUCT_GUIDANCE)
    e1 = ExecutionEngine()
    e2 = ExecutionEngine()
    r1 = e1.execute_decision(d11)
    r2 = e2.execute_decision(d11)

    s11_ok = (
        r1.action == r2.action
        and r1.status == r2.status
        and r1.payload_id == r2.payload_id
        and r1.model_dump_json() == r2.model_dump_json()
    )
    results.append(
        check_test_result(
            "S11: Identical decisions produce 100% byte-for-byte identical ExecutionAuditRecords",
            s11_ok,
            f"Status1={r1.status.value}, Status2={r2.status.value}",
        )
    )

    # ---------------------------------------------------------------
    # S12 — TEST-MODE ISOLATION & DISPATCHER BOUNDARY
    # ---------------------------------------------------------------
    print("\n--- Scenario S12: Test-Mode Isolation Verification ---")
    dispatcher = TestModeDispatcher()
    payload_s12 = PayloadBuilder.build_payload(d1)

    # TestModeDispatcher raises RuntimeError if environment != "TEST_MODE"
    live_blocked = False
    try:
        dispatcher.dispatch(payload_s12, environment="PRODUCTION")
    except RuntimeError:
        live_blocked = True

    s12_ok = (
        DEFAULT_EXECUTION_CONFIG.environment == "TEST_MODE"
        and engine.config.environment == "TEST_MODE"
        and live_blocked
    )
    results.append(
        check_test_result(
            "S12: Execution environment is strictly sandboxed; live dispatching raises RuntimeError",
            s12_ok,
            f"Environment={engine.config.environment}, LiveBlocked={live_blocked}",
        )
    )

    # ---------------------------------------------------------------
    # FINAL SUMMARY
    # ---------------------------------------------------------------
    print("\n" + "=" * 70)
    passed = sum(results)
    total = len(results)
    print(f"PHASE 6 MANUAL BEHAVIORAL TEST RESULT: {passed}/{total} PASSED")

    if passed == total:
        print("[SUCCESS] All Phase 6 manual behavioral scenarios passed successfully.")
    else:
        print("[FAILURE] One or more Phase 6 behavioral scenarios failed.")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
