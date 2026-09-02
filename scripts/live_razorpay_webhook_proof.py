"""
REVIVE — Live Razorpay Test Mode Webhook Proof Harness.
Temporary proof artifact demonstrating full end-to-end integration:
ReviveRuntimeContext -> Real Razorpay Test Mode Payment Link Creation ->
FastAPI /webhooks/razorpay -> OutcomeEngine (RECOVERED + DIRECTLY_OBSERVED).

Runs payment link creation and FastAPI webhook receiver inside the SAME Python process
to guarantee authoritative shared in-memory runtime context.
"""

import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import hmac
import json
import os
import socket
import sys
import threading
import time
from typing import List, Optional, Set, Tuple
import urllib.request
import uvicorn

# Ensure stdout flushes immediately in background task environments
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)

# Ensure repository root is in sys.path
sys.path.insert(0, os.path.abspath("."))

from app.api.main import app as fastapi_app
from app.api.webhooks import get_runtime_context, set_runtime_context
from app.models.entities import Customer, Plan
from app.models.enums import EventType
from app.models.events import BaseEvent
from app.intervention.schemas import CandidateActionScore, InterventionAction, InterventionDecision
from app.execution.schemas import ExecutionAuditRecord, ExecutionStatus, FailureType
from app.outcome.schemas import AttributionStatus, OutcomeType, OutcomeRecord
from app.integrations.razorpay.config import RazorpayConfig
from app.integrations.razorpay.client import RazorpaySandboxClient
from app.integrations.razorpay.dispatcher import RazorpaySandboxDispatcher
from app.integrations.razorpay.webhook import (
    ReviveRuntimeContext,
    WebhookAuditRecord,
    WebhookProcessingStatus,
)


def log(msg: str) -> None:
    """Print message and immediately flush stdout."""
    print(msg, flush=True)


def check_port_available(host: str = "0.0.0.0", port: int = 8000) -> bool:
    """Verify that the target port is free to bind before launching in-process Uvicorn."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind((host, port))
        s.close()
        return True
    except OSError:
        return False


def build_deterministic_live_proof_customer() -> Tuple[Customer, Plan, List[BaseEvent]]:
    """Construct a canonical customer journey with observable payment failure events."""
    plan = Plan(
        plan_id="pro",
        name="Pro Subscription Plan",
        price=Decimal("999.00"),
        currency="INR",
        billing_interval="monthly",
    )

    base_time = datetime.now(timezone.utc) - timedelta(days=2)
    t0 = base_time
    t1 = base_time + timedelta(days=1, hours=2)

    customer = Customer(
        customer_id="cus_live_proof_001",
        merchant_id="merch_codecraft",
        created_at=t0,
        plan_id="pro",
    )

    events = [
        BaseEvent(
            event_id="evt_live_proof_01",
            event_type=EventType.TRIAL_STARTED,
            schema_version="1.0",
            merchant_id="merch_codecraft",
            customer_id=customer.customer_id,
            timestamp=t0,
            source="billing_system",
            payload={"trial_days": 14},
        ),
        BaseEvent(
            event_id="evt_live_proof_02",
            event_type=EventType.PAYMENT_FAILED,
            schema_version="1.0",
            merchant_id="merch_codecraft",
            customer_id=customer.customer_id,
            timestamp=t1,
            source="gateway_webhook",
            payload={
                "amount": "999.00",
                "currency": "INR",
                "error_code": "CARD_DECLINED",
                "error_description": "Card authorization failed by issuing bank",
            },
        ),
    ]

    return customer, plan, events


def build_deterministic_live_proof_decision(
    customer: Customer,
    plan: Plan,
) -> InterventionDecision:
    """Construct a deterministic eligible PAYMENT_RECOVERY InterventionDecision."""
    exec_ts = datetime.now(timezone.utc).isoformat()

    candidate = CandidateActionScore(
        action=InterventionAction.PAYMENT_RECOVERY,
        expected_value=Decimal("746.25"),
        recovery_probability_assumption=0.75,
        direct_cost=Decimal("3.00"),
        incentive_penalty_assumption=Decimal("0.00"),
        harm_penalty_assumption=Decimal("0.00"),
        is_eligible=True,
    )

    return InterventionDecision(
        customer_id=customer.customer_id,
        decision_timestamp=exec_ts,
        risk_score=0.85,
        risk_tier="CRITICAL",
        revenue_at_risk=plan.price,
        diagnosis="PAYMENT_FRICTION",
        diagnosis_confidence=1.0,
        diagnosis_actionability="candidate",
        eligibility_status="ELIGIBLE",
        selected_action=InterventionAction.PAYMENT_RECOVERY,
        expected_value=Decimal("746.25"),
        candidate_scores=[candidate],
        decision_reason="Autonomous recovery of subscription billing payment friction",
        supporting_evidence=["Card authorization failed", "Recent critical churn risk"],
    )


class UvicornServerThread(threading.Thread):
    """Run FastAPI application via Uvicorn in a dedicated daemon thread inside the same process."""

    def __init__(self, app, host: str = "0.0.0.0", port: int = 8000):
        super().__init__(daemon=True)
        self.server_config = uvicorn.Config(
            app=app,
            host=host,
            port=port,
            log_level="info",
            access_log=True,
        )
        self.server = uvicorn.Server(config=self.server_config)

    def run(self):
        self.server.run()

    def stop(self):
        self.server.should_exit = True


def wait_for_server_ready(url: str = "http://127.0.0.1:8000/health", timeout_seconds: int = 10) -> bool:
    """Poll local health endpoint until the internal Uvicorn server is accepting connections."""
    start = time.time()
    while time.time() - start < timeout_seconds:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.3)
    return False


def run_live_proof(
    timeout_seconds: int = 1800,
    reuse_payload_id: Optional[str] = None,
    reuse_payment_url: Optional[str] = None,
) -> int:
    log("=" * 80)
    log("  REVIVE — REAL RAZORPAY TEST MODE WEBHOOK PROOF HARNESS")
    log("=" * 80)

    # 1. Environment & Credential Safety Checks
    log("\n[STEP 1: CONFIGURATION & CREDENTIAL VALIDATION]")
    rzp_config = RazorpayConfig.from_env()

    if rzp_config.environment != "sandbox":
        log(f"[FAIL] Expected sandbox environment, got '{rzp_config.environment}'")
        return 1

    if not rzp_config.key_id or not rzp_config.key_secret or not rzp_config.webhook_secret:
        log("[FAIL] Missing required credentials in environment:")
        log(f"       RAZORPAY_KEY_ID:        {'SET' if rzp_config.key_id else 'NOT SET'}")
        log(f"       RAZORPAY_KEY_SECRET:    {'SET' if rzp_config.key_secret else 'NOT SET'}")
        log(f"       RAZORPAY_WEBHOOK_SECRET:{'SET' if rzp_config.webhook_secret else 'NOT SET'}")
        return 1

    if not rzp_config.key_id.startswith("rzp_test_"):
        log(f"[FAIL] Production safety block: Key ID does not start with 'rzp_test_'")
        return 1

    log("[OK] Environment: sandbox (Test Mode)")
    log(f"[OK] Key ID Status:         SET ({rzp_config.key_id[:12]}...)")
    log("[OK] Key Secret Status:     SET (REDACTED)")
    log("[OK] Webhook Secret Status: SET (REDACTED)")

    # 2. Pre-flight Port Check: ensure port 8000 is NOT occupied by a foreign process
    log("\n[STEP 2: PRE-FLIGHT PORT 8000 EXCLUSIVITY CHECK]")
    if not check_port_available("0.0.0.0", 8000):
        log("[FAIL] Port 8000 is already in use by another process.")
        log("       Please terminate any background uvicorn processes to ensure shared runtime context integrity.")
        return 1
    log("[OK] Port 8000 is free and available for in-process binding")

    # 3. Construct Authoritative Customer, Plan, Decision
    log("\n[STEP 3: CONSTRUCTING AUTHORITATIVE DOMAIN CONTEXT]")
    customer, plan, events = build_deterministic_live_proof_customer()
    decision = build_deterministic_live_proof_decision(customer=customer, plan=plan)
    decision_id = f"dec_{decision.customer_id}_{decision.decision_timestamp}"

    log(f"Customer ID:         {customer.customer_id}")
    log(f"Plan ID:             {plan.plan_id} (Price: INR {plan.price:.2f})")
    log(f"Decision ID:         {decision_id}")
    log(f"Selected Action:     {decision.selected_action.value}")
    log(f"Expected Value (EV): INR {decision.expected_value:.2f}")

    # 4. Create Shared ReviveRuntimeContext & Bind to FastAPI
    log("\n[STEP 4: INITIALIZING UNIFIED RUNTIME CONTEXT]")
    context = ReviveRuntimeContext(config=rzp_config)
    set_runtime_context(context)
    log("[OK] Shared ReviveRuntimeContext wired to FastAPI /webhooks/razorpay router")

    # 5. Start Internal FastAPI Webhook Server in Background Thread
    log("\n[STEP 5: STARTING IN-PROCESS FASTAPI SERVER ON PORT 8000]")
    server_thread = UvicornServerThread(app=fastapi_app, host="0.0.0.0", port=8000)
    server_thread.start()

    if not wait_for_server_ready("http://127.0.0.1:8000/health", timeout_seconds=10):
        log("[FAIL] Could not verify local FastAPI /health endpoint on port 8000")
        server_thread.stop()
        return 1

    log("[OK] FastAPI server active on http://0.0.0.0:8000 (Serving /health & /webhooks/razorpay)")

    # 6. Create / Bind Real Razorpay Payment Link through Execution Engine
    log("\n[STEP 6: EXECUTION ORCHESTRATION & PAYMENT LINK BINDING]")
    if reuse_payload_id:
        log(f"[INFO] Reusing existing payload_id/reference_id: '{reuse_payload_id}' to conserve Razorpay link quota")
        context.record_decision(decision=decision, customer_events=events, plan=plan)
        audit_record = context.audit_logger.log_execution_attempt(
            decision=decision,
            status=ExecutionStatus.EXECUTED,
            attempt_number=1,
            payload_id=reuse_payload_id,
            target_url=reuse_payment_url or f"https://rzp.io/rzp/existing",
        )
        payload_id = reuse_payload_id
        payment_url = audit_record.target_url
    else:
        rzp_client = RazorpaySandboxClient(config=rzp_config)
        conn_ok, conn_err = rzp_client.check_connectivity()
        if not conn_ok:
            log(f"[WARN] Pre-flight Razorpay API check returned: {conn_err}")
        else:
            log("[OK] Pre-flight Razorpay API connectivity verified (read-only GET succeeded)")

        dispatcher = RazorpaySandboxDispatcher(config=rzp_config, client=rzp_client)

        audit_record = context.execute_decision(
            decision=decision,
            customer_events=events,
            plan=plan,
            dispatcher=dispatcher,
        )

        if audit_record.status != ExecutionStatus.EXECUTED:
            log(f"[FAIL] Payment link dispatch failed: {audit_record.failure_reason}")
            server_thread.stop()
            return 1

        payload_id = audit_record.payload_id
        payment_url = audit_record.target_url

    log("=" * 80)
    log("  REAL RAZORPAY PAYMENT LINK READY FOR OPERATOR ACTION")
    log("=" * 80)
    log(f"  Customer ID:      {customer.customer_id}")
    log(f"  Execution ID:     {audit_record.execution_id}")
    log(f"  Payload ID:       {payload_id}")
    log(f"  Reference ID:     {payload_id}")
    log(f"  Payment Link URL: {payment_url}")
    log("=" * 80)
    log("\n  >>> INSTRUCTIONS FOR OPERATOR <<<")
    log(f"  1. Open the URL in your browser: {payment_url}")
    log("  2. Select any payment method (Card / UPI / Netbanking) in Razorpay Test Mode.")
    log("  3. Complete payment with Success.")
    log("  4. Razorpay will automatically deliver 'payment_link.paid' to your zrok webhook tunnel.")
    log("  5. This proof process will capture the webhook and complete the loop.\n")
    log("=" * 80)

    # 7. Wait for Live Webhook Delivery with Ingress Observability
    log(f"\n[STEP 7: LISTENING FOR RAZORPAY WEBHOOK (Timeout: {timeout_seconds}s)]")
    start_time = time.time()
    captured_outcome: Optional[OutcomeRecord] = None
    captured_audit: Optional[WebhookAuditRecord] = None
    seen_audit_ids: Set[str] = set()

    last_ping = 0.0
    while time.time() - start_time < timeout_seconds:
        elapsed = int(time.time() - start_time)

        # Check audit records for any ingress activity
        current_audit_records = context.audit_store.get_all_records()
        for rec in current_audit_records:
            if rec.audit_id not in seen_audit_ids:
                seen_audit_ids.add(rec.audit_id)
                log(f"  >>> [INGRESS OBSERVED] Event: {rec.event_type} | ID: {rec.event_id} | Ref: {rec.reference_id} | Status: {rec.status.value} | Reason: {rec.reason}")

        # Check outcome engine
        outcomes = context.outcome_engine.get_customer_outcomes(customer.customer_id)
        if outcomes:
            captured_outcome = outcomes[0]
            for rec in current_audit_records:
                if rec.status == WebhookProcessingStatus.PROCESSED:
                    captured_audit = rec
                    break
            break

        if time.time() - last_ping >= 10.0:
            log(f"  ... [Listening] Elapsed: {elapsed}s / {timeout_seconds}s — awaiting payment_link.paid webhook...")
            last_ping = time.time()

        time.sleep(1.0)

    if not captured_outcome or not captured_audit:
        log("\n[FAIL] Timed out waiting for Razorpay webhook delivery.")
        server_thread.stop()
        return 1

    # 8. Print Real Live Webhook Proof Results
    log("\n" + "=" * 80)
    log("  REAL RAZORPAY TEST MODE WEBHOOK INGESTION VERIFIED")
    log("=" * 80)
    log(f"  Webhook Event ID:       {captured_audit.event_id}")
    log(f"  Webhook Processing:     {captured_audit.status.value}")
    log(f"  Correlated Reference:   {captured_audit.reference_id} (Matches payload_id: {captured_audit.reference_id == payload_id})")
    log(f"  Correlated Customer:    {captured_audit.customer_id}")
    log(f"  Outcome ID:             {captured_outcome.outcome_id}")
    log(f"  Measured Outcome:       {captured_outcome.outcome.value}")
    log(f"  Attribution Status:     {captured_outcome.attribution_status.value}")
    log(f"  Attributable Revenue:   INR {captured_outcome.attributable_revenue:.2f}")
    log(f"  Net Recovered Revenue:  INR {captured_outcome.net_recovered_revenue:.2f}")
    log(f"  Payment Reference:      {captured_outcome.payment_reference}")
    log(f"  Plan ID Verified:       {plan.plan_id}")
    log("=" * 80)

    # 9. Controlled Post-Payment Duplicate Delivery Check
    log("\n[STEP 8: CONTROLLED POST-PAYMENT DUPLICATE DELIVERY CHECK]")
    dup_event_id = captured_audit.event_id
    raw_dummy = json.dumps({
        "event": "payment_link.paid",
        "payload": {
            "payment_link": {"entity": {"reference_id": payload_id}},
            "payment": {"entity": {"id": captured_outcome.payment_reference or "pay_dup", "amount": 99900}},
        },
    }).encode("utf-8")

    dup_sig = hmac.new(rzp_config.webhook_secret.encode("utf-8"), raw_dummy, hashlib.sha256).hexdigest()

    st_dup, resp_dup = context.webhook_handler.process_webhook(
        raw_body=raw_dummy,
        signature=dup_sig,
        event_id_header=dup_event_id,
    )

    log(f"  Duplicate Delivery HTTP Status: {st_dup}")
    log(f"  Duplicate Processing Status:    {resp_dup.get('status')}")

    outcomes_after_dup = context.outcome_engine.get_customer_outcomes(customer.customer_id)
    log(f"  Total Outcome Records:          {len(outcomes_after_dup)} (Must be exactly 1)")

    if st_dup == 200 and resp_dup.get("status") == "duplicate_acknowledged" and len(outcomes_after_dup) == 1:
        log("[OK] Duplicate delivery idempotency verified: zero double-counting, safely acknowledged.")
    else:
        log("[FAIL] Duplicate delivery check failed.")
        server_thread.stop()
        return 1

    log("\n" + "=" * 80)
    log("  LIVE RAZORPAY TEST MODE WEBHOOK PROOF COMPLETED SUCCESSFULLY")
    log("=" * 80)

    server_thread.stop()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="REVIVE Live Razorpay Webhook Proof Harness")
    parser.add_argument(
        "--timeout",
        type=int,
        default=1800,
        help="Timeout in seconds to wait for Razorpay webhook delivery (default: 1800)",
    )
    parser.add_argument(
        "--reference-id",
        type=str,
        default=None,
        help="Optional existing payload/reference ID to reuse without creating a new link on Razorpay",
    )
    parser.add_argument(
        "--payment-url",
        type=str,
        default=None,
        help="Optional existing payment URL corresponding to --reference-id",
    )
    args = parser.parse_args()
    sys.exit(run_live_proof(
        timeout_seconds=args.timeout,
        reuse_payload_id=args.reference_id,
        reuse_payment_url=args.payment_url,
    ))
