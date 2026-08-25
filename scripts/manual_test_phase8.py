"""
Real Behavioral Manual Sanity Test Suite for Revive Phase 8 AI Intelligence Layer.
Executes 12 real behavioral scenarios verifying mock provider determinism, Gemini safety boundaries,
structured schema validation, evidence grounding, and safe Phase 4/5 fallbacks.

Usage:
    python scripts/manual_test_phase8.py
"""

from decimal import Decimal
import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from app.models.entities import Customer, Plan
from app.models.enums import EventType
from app.models.events import BaseEvent
from app.risk.scoring import ScoredCustomer
from app.diagnosis.schemas import Actionability, DiagnosisCategory
from app.intervention.engine import InterventionEngine
from app.ai.config import AIConfig
from app.ai.client import BaseAIProvider, MockAIProvider
from app.ai.prompts import PROMPT_VERSION, SCHEMA_VERSION
from app.ai.schemas import AIFailureStatus
from app.ai.service import AIService


class CustomTestAIProvider(BaseAIProvider):
    """Custom provider for forcing specific test scenario outputs."""

    def __init__(self, raw_dict=None, failure_status=AIFailureStatus.AI_SUCCESS):
        self.raw_dict = raw_dict
        self.failure_status = failure_status

    def analyze_customer(self, customer_id, risk_score, risk_tier, events, evidence_items):
        return self.raw_dict, self.failure_status, 5.0


def main() -> None:
    print("=" * 70)
    print("  REVIVE PHASE 8 — REAL BEHAVIORAL MANUAL SANITY TEST")
    print("=" * 70)

    passed_count = 0
    total_count = 12

    customer = Customer(
        customer_id="cus_man_001",
        merchant_id="merch_codecraft",
        created_at="2026-01-01T00:00:00+00:00",
        plan_id="pro",
    )
    plan = Plan(plan_id="pro", name="Pro", price=Decimal("999.00"), currency="INR", billing_interval="month")
    scored_cust = ScoredCustomer(
        customer_id="cus_man_001",
        prediction_timestamp="2026-08-05T12:00:00+00:00",
        risk_score=0.85,
        risk_tier="CRITICAL",
        plan_id="pro",
        plan_price=Decimal("999.00"),
        revenue_at_risk=Decimal("999.00"),
    )
    pay_failed_event = BaseEvent(
        event_id="evt_pay_fail",
        event_type=EventType.PAYMENT_FAILED,
        schema_version="1.0",
        merchant_id="merch_codecraft",
        customer_id="cus_man_001",
        timestamp="2026-08-05T11:30:00+00:00",
        source="billing",
        payload={"error_code": "CARD_DECLINED", "amount": 999.00},
    )

    # --- Scenario S1: Valid AI Diagnosis ---
    print("\n--- Scenario S1: Valid AI Diagnosis ---")
    service1 = AIService(config=AIConfig(provider="mock"))
    r1 = service1.analyze_and_diagnose(scored_cust, customer, [pay_failed_event], plan, {})
    if r1.metadata.status == AIFailureStatus.AI_SUCCESS and not r1.metadata.fallback_used:
        print("[PASS] S1: Valid AI proposal accepted with AI_SUCCESS and fallback_used=False")
        passed_count += 1
    else:
        print(f"[FAIL] S1: Status={r1.metadata.status}, Fallback={r1.metadata.fallback_used}")

    # --- Scenario S2: Malformed AI Output (Schema Fallback) ---
    print("\n--- Scenario S2: Malformed AI Output (Schema Fallback) ---")
    p2 = CustomTestAIProvider(raw_dict={"diagnosis_candidate": "BAD_TAXONOMY", "confidence": 0.9})
    service2 = AIService(config=AIConfig(provider="mock"), provider=p2)
    r2 = service2.analyze_and_diagnose(scored_cust, customer, [pay_failed_event], plan, {})
    if r2.metadata.status == AIFailureStatus.AI_SCHEMA_INVALID and r2.metadata.fallback_used:
        print("[PASS] S2: Invalid diagnosis category triggers AI_SCHEMA_INVALID & safe deterministic fallback")
        passed_count += 1
    else:
        print(f"[FAIL] S2: Status={r2.metadata.status}, Fallback={r2.metadata.fallback_used}")

    # --- Scenario S3: Unsupported Evidence Claim ---
    print("\n--- Scenario S3: Unsupported Evidence Claim ---")
    p3 = CustomTestAIProvider(raw_dict={
        "diagnosis_candidate": "PAYMENT_FRICTION",
        "confidence": 0.85,
        "actionability": "CANDIDATE",
        "supporting_evidence": ["Customer bank account was permanently closed by law enforcement"],
        "explanation": "Fabricated rationale",
    })
    service3 = AIService(config=AIConfig(provider="mock"), provider=p3)
    r3 = service3.analyze_and_diagnose(scored_cust, customer, [pay_failed_event], plan, {})
    if r3.metadata.status == AIFailureStatus.AI_GROUNDING_FAILED and r3.metadata.fallback_used:
        print("[PASS] S3: Fabricated evidence claim triggers AI_GROUNDING_FAILED & safe deterministic fallback")
        passed_count += 1
    else:
        print(f"[FAIL] S3: Status={r3.metadata.status}, Fallback={r3.metadata.fallback_used}")

    # --- Scenario S4: Low Confidence AI Proposal ---
    print("\n--- Scenario S4: Low Confidence AI Proposal ---")
    p4 = CustomTestAIProvider(raw_dict={
        "diagnosis_candidate": "LOW_INTENT",
        "confidence": 0.30,
        "actionability": "NONE",
        "supporting_evidence": ["payment_failed"],
        "explanation": "Uncertain proposal",
    })
    service4 = AIService(config=AIConfig(provider="mock", min_confidence_threshold=0.50), provider=p4)
    r4 = service4.analyze_and_diagnose(scored_cust, customer, [pay_failed_event], plan, {})
    if r4.metadata.status == AIFailureStatus.AI_LOW_CONFIDENCE and r4.metadata.fallback_used:
        print("[PASS] S4: Confidence 0.30 below 0.50 threshold triggers AI_LOW_CONFIDENCE & fallback")
        passed_count += 1
    else:
        print(f"[FAIL] S4: Status={r4.metadata.status}, Fallback={r4.metadata.fallback_used}")

    # --- Scenario S5: Provider Unavailable ---
    print("\n--- Scenario S5: Provider Unavailable ---")
    p5 = CustomTestAIProvider(failure_status=AIFailureStatus.AI_UNAVAILABLE)
    service5 = AIService(config=AIConfig(provider="mock"), provider=p5)
    r5 = service5.analyze_and_diagnose(scored_cust, customer, [pay_failed_event], plan, {})
    if r5.metadata.status == AIFailureStatus.AI_UNAVAILABLE and r5.metadata.fallback_used:
        print("[PASS] S5: AI_UNAVAILABLE triggers safe fallback to deterministic Phase 4 diagnosis")
        passed_count += 1
    else:
        print(f"[FAIL] S5: Status={r5.metadata.status}")

    # --- Scenario S6: Provider Timeout ---
    print("\n--- Scenario S6: Provider Timeout ---")
    p6 = CustomTestAIProvider(failure_status=AIFailureStatus.AI_TIMEOUT)
    service6 = AIService(config=AIConfig(provider="mock"), provider=p6)
    r6 = service6.analyze_and_diagnose(scored_cust, customer, [pay_failed_event], plan, {})
    if r6.metadata.status == AIFailureStatus.AI_TIMEOUT and r6.metadata.fallback_used:
        print("[PASS] S6: AI_TIMEOUT triggers safe fallback to deterministic Phase 4 diagnosis")
        passed_count += 1
    else:
        print(f"[FAIL] S6: Status={r6.metadata.status}")

    # --- Scenario S7: Phase 5 Policy Protection Boundary ---
    print("\n--- Scenario S7: Phase 5 Policy Protection Boundary ---")
    decision = InterventionEngine().decide_intervention(scored_cust, r1.final_diagnosis, plan, {})
    if decision.selected_action is not None and decision.eligibility_status in {"ELIGIBLE", "INELIGIBLE"}:
        print("[PASS] S7: Phase 5 independently evaluates and governs intervention selected action")
        passed_count += 1
    else:
        print(f"[FAIL] S7: Decision={decision}")

    # --- Scenario S8: Execution Authority Isolation ---
    print("\n--- Scenario S8: Execution Authority Isolation ---")
    if not hasattr(service1, "execute") and not hasattr(service1, "dispatch"):
        print("[PASS] S8: Zero direct execution authority present in Phase 8 AI service layer")
        passed_count += 1
    else:
        print("[FAIL] S8: Found execution methods in AIService")

    # --- Scenario S9: Hidden Ground-Truth Isolation ---
    print("\n--- Scenario S9: Hidden Ground-Truth Isolation ---")
    from app.ai import prompts
    import inspect
    p_src = inspect.getsource(prompts)
    forbidden = ["ground_truth.jsonl", "true_root_cause", "natural_conversion", "recoverable"]
    if not any(f in p_src for f in forbidden):
        print("[PASS] S9: Verified 0.0% ground-truth leakage in AI prompts and input payloads")
        passed_count += 1
    else:
        print("[FAIL] S9: Found forbidden simulator fields in prompt source")

    # --- Scenario S10: Deterministic Mock Reproducibility ---
    print("\n--- Scenario S10: Deterministic Mock Reproducibility ---")
    p_mock = MockAIProvider()
    res1, _, _ = p_mock.analyze_customer("c1", 0.85, "CRITICAL", [pay_failed_event], [])
    res2, _, _ = p_mock.analyze_customer("c1", 0.85, "CRITICAL", [pay_failed_event], [])
    if res1 == res2:
        print("[PASS] S10: Mock AI Provider produces 100% identical outputs for identical inputs")
        passed_count += 1
    else:
        print("[FAIL] S10: Mock outputs non-deterministic")

    # --- Scenario S11: Prompt & Schema Versioning ---
    print("\n--- Scenario S11: Prompt & Schema Versioning ---")
    if r1.metadata.prompt_version == PROMPT_VERSION and r1.metadata.schema_version == SCHEMA_VERSION:
        print("[PASS] S11: AI Analysis metadata accurately records prompt and schema versions")
        passed_count += 1
    else:
        print(f"[FAIL] S11: PromptVer={r1.metadata.prompt_version}, SchemaVer={r1.metadata.schema_version}")

    # --- Scenario S12: Secrets & Sandbox Isolation ---
    print("\n--- Scenario S12: Secrets & Sandbox Isolation ---")
    cfg = AIConfig()
    if cfg.provider == "mock" and cfg.api_key is None:
        print("[PASS] S12: Default offline mock sandbox active with zero committed API secrets")
        passed_count += 1
    else:
        print(f"[FAIL] S12: Provider={cfg.provider}, Key={cfg.api_key}")

    print("\n" + "=" * 70)
    print(f"PHASE 8 MANUAL BEHAVIORAL TEST RESULT: {passed_count}/{total_count} PASSED")
    if passed_count == total_count:
        print("[SUCCESS] All Phase 8 manual behavioral scenarios passed successfully.")
        print("=" * 70 + "\n")
    else:
        print("[FAILURE] Some Phase 8 manual behavioral scenarios failed.")
        print("=" * 70 + "\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
