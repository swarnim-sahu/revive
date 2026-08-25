"""
Revive Phase 9 — End-to-End Razorpay Sandbox Proof Script.
Exercises the complete production REVIVE pipeline from customer event input
through risk scoring, diagnosis, AI analysis, policy engine, execution engine,
and Razorpay Sandbox payment-link generation.

Supports:
  --mode offline  (Default: MockAIProvider + MockRazorpayClient, zero network)
  --mode sandbox  (Requires operator GEMINI_API_KEY & RAZORPAY credentials, real sandbox API)
"""

import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import os
import sys
from typing import Any, Dict, List

sys.path.insert(0, os.path.abspath("."))

from app.models.entities import Customer, Plan
from app.models.enums import EventType
from app.models.events import BaseEvent
from app.risk.features import CustomerFeatureExtractor
from app.risk.model import ReviveRiskModel
from app.risk.scoring import RiskScorer
from app.diagnosis.engine import DiagnosisEngine
from app.ai.config import AIConfig
from app.ai.service import AIService
from app.ai.client import MockAIProvider, GeminiAIProvider
from app.intervention.engine import InterventionEngine
from app.execution.engine import ExecutionEngine
from app.integrations.razorpay.config import RazorpayConfig
from app.integrations.razorpay.client import MockRazorpayClient, RazorpaySandboxClient
from app.integrations.razorpay.dispatcher import RazorpaySandboxDispatcher


def build_controlled_payment_failure_customer(
    mode: str = "offline",
) -> tuple[Customer, Plan, List[BaseEvent]]:
    """Construct a canonical controlled customer with a payment failure event."""
    plan = Plan(
        plan_id="pro",
        name="Pro Subscription Plan",
        price=Decimal("999.00"),
        billing_interval="monthly",
    )

    if mode == "sandbox":
        # Generate unique timezone-aware UTC base timestamp per sandbox invocation
        base_time = datetime.now(timezone.utc) - timedelta(days=3)
    else:
        # Preserve deterministic fixed base timestamp for offline mode
        base_time = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)

    t0 = base_time
    t1 = base_time + timedelta(days=2, hours=4)
    t2 = base_time + timedelta(days=2, hours=23, minutes=30)

    customer = Customer(
        customer_id="cus_e2e_razorpay_001",
        merchant_id="merch_codecraft",
        created_at=t0,
        plan_id="pro",
    )

    events = [
        BaseEvent(
            event_id="evt_e2e_01",
            event_type=EventType.TRIAL_STARTED,
            schema_version="1.0",
            merchant_id="merch_codecraft",
            customer_id="cus_e2e_razorpay_001",
            timestamp=t0,
            source="e2e_generator",
            payload={"trial_days": 14},
        ),
        BaseEvent(
            event_id="evt_e2e_02",
            event_type=EventType.PAYMENT_FAILED,
            schema_version="1.0",
            merchant_id="merch_codecraft",
            customer_id="cus_e2e_razorpay_001",
            timestamp=t1,
            source="e2e_generator",
            payload={
                "amount": 999.00,
                "currency": "INR",
                "error_code": "CARD_DECLINED",
                "error_description": "Card authorization failed",
            },
        ),
        BaseEvent(
            event_id="evt_e2e_03",
            event_type=EventType.PAYMENT_FAILED,
            schema_version="1.0",
            merchant_id="merch_codecraft",
            customer_id="cus_e2e_razorpay_001",
            timestamp=t2,
            source="e2e_generator",
            payload={
                "amount": 999.00,
                "currency": "INR",
                "error_code": "INSUFFICIENT_FUNDS",
                "error_description": "Insufficient funds available",
            },
        ),
    ]
    return customer, plan, events


def run_e2e_proof(mode: str = "offline") -> int:
    print("=" * 80)
    print(f"  REVIVE PHASE 9 — END-TO-END INTEGRATION PROOF (Mode: {mode.upper()})")
    print("=" * 80)

    # 1. Setup Razorpay Dispatcher & Client according to mode
    if mode == "sandbox":
        print("\n--- [STEP 0: SANDBOX ENVIRONMENT & CREDENTIAL VERIFICATION] ---")
        rzp_config = RazorpayConfig.from_env()

        if rzp_config.environment != "sandbox":
            print(f"[FAIL] Expected environment 'sandbox', got '{rzp_config.environment}'")
            return 1
        if not rzp_config.base_url.startswith("https://api.razorpay.com"):
            print(f"[FAIL] Unexpected Razorpay API base URL: '{rzp_config.base_url}'")
            return 1
        if not rzp_config.key_id or not rzp_config.key_secret:
            print("[FAIL] Missing RAZORPAY_KEY_ID or RAZORPAY_KEY_SECRET in environment")
            return 1
        if not rzp_config.key_id.startswith("rzp_test_"):
            print(f"[FAIL] Production safety block: Key ID does not start with 'rzp_test_'")
            return 1

        print("[OK] Razorpay Config Environment: sandbox")
        print(f"[OK] Razorpay Key ID Detected:   {bool(rzp_config.key_id)}")
        print(f"[OK] Razorpay Key Secret Status:  {repr(rzp_config)}")
        print("[OK] All Razorpay sandbox safety preconditions satisfied")

        rzp_client = RazorpaySandboxClient(config=rzp_config)
        
        # AI Provider in sandbox mode: use Gemini if key present, else safe Mock
        ai_config = AIConfig.from_env()
        ai_provider = GeminiAIProvider(config=ai_config) if ai_config.api_key else MockAIProvider(config=ai_config)
    else:
        print("\n--- [STEP 0: OFFLINE MOCK MODE INITIALIZATION] ---")
        rzp_config = RazorpayConfig(environment="sandbox", key_id="rzp_test_MOCK12345", key_secret="SECRET_MOCK")
        rzp_client = MockRazorpayClient(config=rzp_config)
        ai_config = AIConfig(provider="mock")
        ai_provider = MockAIProvider(config=ai_config)
        print("[OK] Operating strictly in 100% offline mock sandbox mode")

    dispatcher = RazorpaySandboxDispatcher(config=rzp_config, client=rzp_client)
    exec_engine = ExecutionEngine(dispatcher=dispatcher)
    ai_service = AIService(config=ai_config, provider=ai_provider)

    # Load trained risk model or create fallback
    model_path = os.path.join("models", "risk", "risk_model.joblib")
    if os.path.exists(model_path):
        risk_model = ReviveRiskModel.load(model_path)
    else:
        print(f"[FAIL] Trained risk model artifact not found at '{model_path}'")
        return 1

    risk_scorer = RiskScorer(model=risk_model)
    feature_extractor = CustomerFeatureExtractor()
    diagnosis_engine = DiagnosisEngine()
    intervention_engine = InterventionEngine()

    # 2. Input Data Setup
    print("\n--- [STEP 1: CUSTOMER JOURNEY EVENT INGESTION] ---")
    customer, plan, events = build_controlled_payment_failure_customer(mode=mode)
    print(f"Customer ID:  {customer.customer_id}")
    print(f"Plan ID:       {plan.plan_id} (Price: INR {plan.price:.2f})")
    print(f"Event Count:   {len(events)} observable journey events")

    # 3. Feature Extraction & Risk Scoring
    print("\n--- [STEP 2: FEATURE EXTRACTION & RISK SCORING (PHASE 3)] ---")
    feature_record, status_str = feature_extractor.extract_features(customer, events, plan)
    if status_str != "OK":
        print(f"[FAIL] Feature extraction failed with status '{status_str}'")
        return 1

    scored_customer = risk_scorer.score_customer(feature_record)
    print(f"Risk Score:       {scored_customer.risk_score:.4f}")
    print(f"Risk Tier:        {scored_customer.risk_tier}")
    print(f"Revenue at Risk:  INR {scored_customer.revenue_at_risk:.2f}")

    # 4. Root-Cause Diagnosis (Phase 4)
    print("\n--- [STEP 3: ROOT-CAUSE DIAGNOSIS (PHASE 4)] ---")
    baseline_diag = diagnosis_engine.diagnose_customer(
        scored_customer=scored_customer,
        customer=customer,
        events=events,
        plan=plan,
        feature_record=feature_record,
    )
    print(f"Deterministic Diagnosis: {baseline_diag.diagnosis.value}")
    print(f"Confidence:              {baseline_diag.confidence:.2f}")

    # 5. AI Intelligence Layer (Phase 8)
    print("\n--- [STEP 4: AI INTELLIGENCE & GROUNDING VALIDATION (PHASE 8)] ---")
    ai_result = ai_service.analyze_and_diagnose(
        scored_customer=scored_customer,
        customer=customer,
        events=events,
        plan=plan,
        feature_record=feature_record,
    )
    print(f"AI Provider Status: {ai_result.metadata.status.value}")
    print(f"AI Final Diagnosis: {ai_result.final_diagnosis.diagnosis.value}")
    print(f"Fallback Used:       {ai_result.metadata.fallback_used}")

    # 6. Intervention Policy Decision (Phase 5)
    print("\n--- [STEP 5: INTERVENTION POLICY DECISION (PHASE 5)] ---")
    decision = intervention_engine.decide_intervention(
        scored_customer=scored_customer,
        diagnosis=ai_result.final_diagnosis,
        plan=plan,
        feature_record=feature_record,
    )
    decision_id_str = f"dec_{decision.customer_id}_{decision.decision_timestamp}"
    print(f"Decision ID:         {decision_id_str}")
    print(f"Eligibility Status:  {decision.eligibility_status}")
    print(f"Selected Action:     {decision.selected_action.value}")
    print(f"Expected Value (EV): INR {decision.expected_value:.2f}")
    print(f"Decision Reason:     {decision.decision_reason}")

    # 7. Execution Orchestration & Razorpay Dispatch (Phase 6 + Phase 9)
    print("\n--- [STEP 6: WORKFLOW EXECUTION & RAZORPAY DISPATCH (PHASE 6 + 9)] ---")
    audit_record = exec_engine.execute_decision(decision=decision)

    print(f"Execution Status: {audit_record.status.value}")
    print(f"Payload ID:       {audit_record.payload_id}")
    print(f"Target URL:       {audit_record.target_url}")

    # 8. Complete Execution Trace Display
    print("\n" + "=" * 80)
    print("  COMPLETE E2E EXECUTION TRACE SUMMARY")
    print("=" * 80)
    print(f"Customer ID:           {customer.customer_id}")
    print(f"Risk Score:            {scored_customer.risk_score:.4f}")
    print(f"Risk Tier:             {scored_customer.risk_tier}")
    print(f"Deterministic Diag:    {baseline_diag.diagnosis.value}")
    print(f"AI Analysis Status:    {ai_result.metadata.status.value}")
    print(f"AI Confidence:         {ai_result.final_diagnosis.confidence:.2f}")
    print(f"Decision ID:           {decision_id_str}")
    print(f"Eligibility Status:    {decision.eligibility_status}")
    print(f"Selected Action:       {decision.selected_action.value}")
    print(f"Expected Value:        INR {decision.expected_value:.2f}")
    print(f"Execution Payload ID:  {audit_record.payload_id}")
    print(f"Execution Status:      {audit_record.status.value}")
    print(f"Target Payment URL:    {audit_record.target_url}")
    print(f"Execution Timestamp:   {audit_record.execution_timestamp}")
    print("=" * 80)

    if audit_record.status.value in {"EXECUTED", "SUCCESS"}:
        print("\n[SUCCESS] E2E integration proof executed cleanly from event input to Razorpay payment link.")
        return 0
    else:
        print(f"\n[FAIL] Execution failed with status '{audit_record.status.value}': {audit_record.failure_reason}")
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="REVIVE E2E Razorpay Proof Script")
    parser.add_argument(
        "--mode",
        choices=["offline", "sandbox"],
        default="offline",
        help="Execution mode: 'offline' (default mock) or 'sandbox' (real Razorpay Sandbox)",
    )
    args = parser.parse_args()
    sys.exit(run_e2e_proof(mode=args.mode))
