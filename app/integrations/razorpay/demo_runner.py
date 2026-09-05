"""
Controlled Razorpay Sandbox / Test Mode Demonstration Runner for REVIVE Phase 9.
Provides an explicit, intentional entry point for executing one approved recovery action
via ExecutionEngine and RazorpaySandboxDispatcher.

Strict Invariants:
1. Zero automated execution on startup, page load, or test suite execution.
2. Authoritative identity: payload.payload_id -> reference_id.
3. Hard separation: Payment Link Created != Payment Recovered.
4. Unexecuted baseline remains NOT_RUN (or DRY_RUN).
5. Zero secrets logged or persisted.
"""

from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from app.diagnosis.schemas import (
    Actionability,
    ConfidenceTier,
    CustomerDiagnosis,
    DiagnosisCategory,
    EvidenceCategory,
    EvidenceItem,
)
from app.models.entities import Plan
from app.risk.scoring import ScoredCustomer
from app.intervention.engine import InterventionEngine
from app.intervention.schemas import (
    CandidateActionScore,
    InterventionAction,
    InterventionDecision,
)
from app.models.enums import EventType
from app.models.events import BaseEvent
from app.execution.engine import ExecutionEngine
from app.execution.schemas import ExecutionAuditRecord, ExecutionStatus
from app.integrations.razorpay.config import DEFAULT_RAZORPAY_CONFIG, RazorpayConfig
from app.integrations.razorpay.client import (
    BaseRazorpayClient,
    MockRazorpayClient,
    RazorpaySandboxClient,
)
from app.integrations.razorpay.dispatcher import RazorpaySandboxDispatcher
from app.integrations.razorpay.persistence import (
    DEFAULT_PHASE9_CONTEXT_PATH,
    Phase9RuntimeContext,
    save_phase9_runtime_context,
)

# Path to the dedicated Phase 9 demonstration evidence artifact
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PHASE9_ARTIFACT_PATH = (
    _PROJECT_ROOT / "docs" / "evidence" / "phase9_razorpay_sandbox_demo.json"
)


def create_demo_intervention_decision(
    customer_id: str = "cus_rzp_sandbox_demo_001",
    amount_paise: int = 99900,
    intervention_engine: Optional[InterventionEngine] = None,
) -> InterventionDecision:
    """
    Produce an authoritative, policy-approved Phase 5 InterventionDecision
    by invoking the existing deterministic InterventionEngine through its public interface.
    """
    plan_price = Decimal(str(Decimal(amount_paise) / Decimal(100)))
    plan = Plan(
        plan_id="pro",
        name="Pro Subscription Plan",
        price=plan_price,
        billing_interval="monthly",
    )

    now_iso = datetime.now(timezone.utc).isoformat()

    scored_customer = ScoredCustomer(
        customer_id=customer_id,
        prediction_timestamp=now_iso,
        risk_score=0.88,
        risk_tier="CRITICAL",
        plan_id=plan.plan_id,
        plan_price=plan_price,
        revenue_at_risk=plan_price,
    )

    ev_item = EvidenceItem(
        evidence_type=EvidenceCategory.PAYMENT_FAILURE,
        strength=1.0,
        description="Recorded 1 payment failure before snapshot (reason: bank_declined)",
    )

    diagnosis = CustomerDiagnosis(
        customer_id=customer_id,
        prediction_timestamp=now_iso,
        risk_score=0.88,
        risk_tier="CRITICAL",
        diagnosis=DiagnosisCategory.PAYMENT_FRICTION,
        confidence=0.90,
        confidence_tier=ConfidenceTier.VERY_HIGH,
        actionability=Actionability.CANDIDATE,
        candidate_causes=[],
        supporting_evidence=[ev_item],
        explanation="Observable payment failure detected with high customer intent",
    )

    feature_record: Dict[str, Any] = {
        "customer_id": customer_id,
        "payment_failure_count": 1,
        "active_days": 12,
        "failed_checkout_count": 0,
        "payment_method": "card",
    }

    engine = intervention_engine or InterventionEngine()
    decision = engine.decide_intervention(
        scored_customer=scored_customer,
        diagnosis=diagnosis,
        plan=plan,
        feature_record=feature_record,
    )

    return decision


def run_controlled_sandbox_demonstration(
    config: Optional[RazorpayConfig] = None,
    client: Optional[BaseRazorpayClient] = None,
    decision: Optional[InterventionDecision] = None,
    dry_run: bool = False,
    save_artifact: bool = True,
    artifact_path: Optional[Path] = None,
    context_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Execute ONE controlled Razorpay Sandbox / Test Mode recovery intervention.

    In dry_run mode:
      Evaluates the pipeline and records 'NOT_RUN' or 'DRY_RUN' without making live API calls.

    In live execution mode:
      Requires explicit sandbox configuration with Test Mode credentials ('rzp_test_*').
      Executes through ExecutionEngine -> RazorpaySandboxDispatcher -> RazorpaySandboxClient.
      Enforces: Payment Link Created != Payment Recovered.
    """
    target_path = artifact_path or DEFAULT_PHASE9_ARTIFACT_PATH
    now_iso = datetime.now(timezone.utc).isoformat()

    # 1. Obtain authoritative Phase 5 decision from existing InterventionEngine
    pol_decision = decision or create_demo_intervention_decision()

    # 2. Verify Phase 5 policy authority
    if (
        pol_decision.eligibility_status != "ELIGIBLE"
        or pol_decision.selected_action != InterventionAction.PAYMENT_RECOVERY
    ):
        raise PermissionError(
            "Phase 5 policy gate rejected intervention. Cannot execute via Razorpay."
        )

    # 3. Handle DRY_RUN mode (Safe unexecuted or simulated inspection)
    if dry_run:
        result = {
            "phase_version": "9.0.0",
            "operation": "CREATE_PAYMENT_LINK",
            "environment": "sandbox",
            "policy_decision": {
                "customer_id": pol_decision.customer_id,
                "selected_action": pol_decision.selected_action.value,
                "eligibility_status": pol_decision.eligibility_status,
                "expected_value": float(pol_decision.expected_value),
                "revenue_at_risk": float(pol_decision.revenue_at_risk),
                "decision_timestamp": pol_decision.decision_timestamp,
            },
            "execution_status": "NOT_RUN",
            "payment_status": "PENDING",
            "payload_id": f"payload_dryrun_{pol_decision.customer_id}",
            "provider_reference": None,
            "short_url": None,
            "webhook_status": "PENDING_WEBHOOK",
            "outcome_status": "NO_OBSERVABLE_OUTCOME",
            "attribution_status": "UNATTRIBUTED",
            "timestamps": {
                "decision_timestamp": pol_decision.decision_timestamp,
                "demonstration_timestamp": now_iso,
            },
            "idempotency_result": "DRY_RUN_UNEXECUTED",
            "disclosure": (
                "Controlled Razorpay Test Mode demonstration record. Initialized in NOT_RUN state. "
                "Requires explicit user invocation with Test Mode credentials."
            ),
        }
        if save_artifact:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
        return result

    # 4. Live or explicitly mocked execution path
    cfg = config or RazorpayConfig.from_env()

    # Select dispatcher
    dispatcher = RazorpaySandboxDispatcher(config=cfg, client=client)

    # Execute through ExecutionEngine
    engine = ExecutionEngine(dispatcher=dispatcher)

    # Check for duplicate decision submission before execution
    decision_id = f"dec_{pol_decision.customer_id}_{pol_decision.decision_timestamp}"
    prior_history = engine.audit_logger.get_customer_audit_history(pol_decision.customer_id)
    is_pre_existing_dup = any(
        r.decision_id == decision_id and r.status in {ExecutionStatus.EXECUTED, ExecutionStatus.ESCALATED, ExecutionStatus.BLOCKED}
        for r in prior_history
    )

    audit_record: ExecutionAuditRecord = engine.execute_decision(decision=pol_decision)

    # Check execution status
    is_success = audit_record.status == ExecutionStatus.EXECUTED
    provider_link_id = None
    short_url = None

    if is_success:
        short_url = audit_record.target_url
        # Obtain authoritative provider payment link ID from the dispatcher/client boundary
        latest_resp = dispatcher.latest_provider_response
        if latest_resp and latest_resp.payment_link_id:
            provider_link_id = latest_resp.payment_link_id
        elif isinstance(dispatcher.client, MockRazorpayClient):
            key = audit_record.payload_id
            if key and key in dispatcher.client.created_links:
                provider_link_id = dispatcher.client.created_links[key].payment_link_id

    # Truthful idempotency result determination:
    if is_success:
        if is_pre_existing_dup:
            idempotency_result = "DUPLICATE_SUPPRESSED"
        elif audit_record.attempt_number > 1:
            idempotency_result = "RETRY_SUCCESS"
        else:
            idempotency_result = "EXECUTION_SUCCEEDED"
    else:
        idempotency_result = "EXECUTION_FAILED"

    # 5. Build structured result ensuring: Payment Link Created != Payment Recovered!
    result = {
        "phase_version": "9.0.0",
        "operation": "CREATE_PAYMENT_LINK",
        "environment": "sandbox",
        "policy_decision": {
            "customer_id": pol_decision.customer_id,
            "selected_action": pol_decision.selected_action.value,
            "eligibility_status": pol_decision.eligibility_status,
            "expected_value": float(pol_decision.expected_value),
            "revenue_at_risk": float(pol_decision.revenue_at_risk),
            "decision_timestamp": pol_decision.decision_timestamp,
        },
        "execution_status": audit_record.status.value,
        "payment_status": "PENDING" if is_success else "FAILED",
        "payload_id": audit_record.payload_id,
        "provider_reference": provider_link_id,
        "short_url": short_url,
        "webhook_status": "PENDING_WEBHOOK",
        "outcome_status": "NO_OBSERVABLE_OUTCOME",
        "attribution_status": "UNATTRIBUTED",
        "timestamps": {
            "decision_timestamp": pol_decision.decision_timestamp,
            "execution_timestamp": audit_record.execution_timestamp,
            "demonstration_timestamp": now_iso,
        },
        "idempotency_result": idempotency_result,
        "failure_reason": audit_record.failure_reason,
        "disclosure": (
            "Controlled Razorpay Test Mode execution demonstration. "
            "A created Payment Link is an outbound recovery attempt and is NOT recovered revenue. "
            "Financial recovery and attribution strictly require subsequent verified payment evidence."
        ),
    }

    if is_success:
        # Build durable Phase 9 correlation projection
        plan = Plan(
            plan_id="pro",
            name="Pro Subscription Plan",
            price=Decimal(str(pol_decision.revenue_at_risk)),
            billing_interval="monthly",
        )
        pre_dt = datetime.fromisoformat(pol_decision.decision_timestamp)
        pre_fail_evt = BaseEvent(
            event_id=f"evt_pre_{audit_record.payload_id}",
            event_type=EventType.PAYMENT_FAILED,
            schema_version="1.0",
            merchant_id=audit_record.merchant_id,
            customer_id=pol_decision.customer_id,
            timestamp=pre_dt,
            source="pre_intervention_observable",
            payload={"reason": "bank_declined", "amount": str(pol_decision.revenue_at_risk)},
        )
        p9_context = Phase9RuntimeContext(
            schema_version="1.0.0",
            payload_id=audit_record.payload_id or f"payload_{pol_decision.customer_id}",
            execution_id=audit_record.execution_id,
            decision_id=audit_record.decision_id,
            customer_id=pol_decision.customer_id,
            provider_reference=provider_link_id,
            short_url=short_url,
            decision=pol_decision.model_dump(mode="json"),
            plan=plan.model_dump(mode="json"),
            execution_record=audit_record.model_dump(mode="json"),
            customer_events=[pre_fail_evt.model_dump(mode="json")],
            processed_event_ids=[],
            created_at=now_iso,
            updated_at=now_iso,
        )
        if save_artifact:
            save_phase9_runtime_context(p9_context, path=context_path)

    if save_artifact:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)

    return result
