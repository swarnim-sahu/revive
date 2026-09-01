"""
Razorpay Webhook Handling & Outcome Integration Module for REVIVE Phase A.
Implements raw-body HMAC-SHA256 signature verification, required event-id delivery idempotency,
exact reference_id correlation, exact decision_id and authoritative Plan resolution,
canonical BaseEvent translation, append-only audit tracking, retry-safe at-least-once delivery,
and Phase 7 OutcomeEngine integration.

Note on Idempotency Persistence:
`WebhookAuditStore` and `RazorpayWebhookHandler.processed_event_ids` operate as an in-memory
repository for Phase A. Webhook delivery idempotency (`X-Razorpay-Event-Id`) is scoped to the
lifetime of the running application process. In production deployment, this maps to an external
append-only persistence sink (e.g. Redis / PostgreSQL / Kafka deduplication stream).
"""

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import hashlib
import hmac
import json
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, ConfigDict, Field, field_validator, ValidationInfo

from app.models.entities import Customer, Plan, _validate_non_empty_string
from app.models.enums import EventType
from app.models.events import BaseEvent
from app.intervention.schemas import InterventionDecision
from app.execution.audit import ExecutionAuditLogger
from app.execution.schemas import ExecutionAuditRecord
from app.outcome.engine import OutcomeEngine
from app.outcome.schemas import OutcomeRecord
from app.integrations.razorpay.config import DEFAULT_RAZORPAY_CONFIG, RazorpayConfig


def verify_webhook_signature(
    raw_body: bytes,
    signature: Optional[str],
    secret: Optional[str],
) -> bool:
    """
    Verify Razorpay webhook HMAC-SHA256 signature against raw request body bytes.
    Uses constant-time comparison to prevent timing side-channel attacks.
    Fails closed if signature or secret is missing or empty.
    """
    if not signature or not secret or not raw_body:
        return False

    try:
        expected_signature = hmac.new(
            key=secret.encode("utf-8"),
            msg=raw_body,
            digestmod=hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected_signature, signature.strip())
    except Exception:
        return False


class WebhookProcessingStatus(str, Enum):
    """Lifecycle and operational processing status for incoming webhook events."""

    PROCESSED = "PROCESSED"
    DUPLICATE_IGNORED = "DUPLICATE_IGNORED"
    UNSUPPORTED_IGNORED = "UNSUPPORTED_IGNORED"
    UNMATCHED_REFERENCE = "UNMATCHED_REFERENCE"
    DECISION_UNAVAILABLE = "DECISION_UNAVAILABLE"
    PLAN_UNAVAILABLE = "PLAN_UNAVAILABLE"
    INVALID_SIGNATURE = "INVALID_SIGNATURE"
    MISSING_EVENT_ID = "MISSING_EVENT_ID"
    MALFORMED_PAYLOAD = "MALFORMED_PAYLOAD"


class WebhookAuditRecord(BaseModel):
    """Immutable, auditable record of an incoming Razorpay webhook delivery attempt."""

    model_config = ConfigDict(extra="forbid")

    audit_id: str
    event_id: str
    event_type: str
    status: WebhookProcessingStatus
    received_at: str
    reference_id: Optional[str] = None
    execution_id: Optional[str] = None
    customer_id: Optional[str] = None
    outcome_id: Optional[str] = None
    reason: Optional[str] = None

    @field_validator("audit_id", "event_id", "event_type", "received_at")
    @classmethod
    def validate_audit_strings(cls, v: Any, info: ValidationInfo) -> str:
        return _validate_non_empty_string(info.field_name or "field", v)


class WebhookAuditStore:
    """
    In-memory append-only audit repository for webhook events.
    Preserves complete delivery history across duplicate delivery attempts.
    """

    def __init__(self) -> None:
        self._records: List[WebhookAuditRecord] = []
        self._records_by_event_id: Dict[str, List[WebhookAuditRecord]] = {}

    def log_webhook_event(
        self,
        event_id: str,
        event_type: str,
        status: WebhookProcessingStatus,
        reference_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        customer_id: Optional[str] = None,
        outcome_id: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> WebhookAuditRecord:
        """Create and append an immutable WebhookAuditRecord preserving complete history."""
        seq_num = len(self._records) + 1
        clean_event_id = event_id.strip() if event_id and event_id.strip() else "missing_event_id"
        audit_id = f"wh_audit_{clean_event_id}_{seq_num}"

        record = WebhookAuditRecord(
            audit_id=audit_id,
            event_id=clean_event_id,
            event_type=event_type or "unknown",
            status=status,
            received_at=datetime.now(timezone.utc).isoformat(),
            reference_id=reference_id,
            execution_id=execution_id,
            customer_id=customer_id,
            outcome_id=outcome_id,
            reason=reason,
        )
        self._records.append(record)
        if clean_event_id not in self._records_by_event_id:
            self._records_by_event_id[clean_event_id] = []
        self._records_by_event_id[clean_event_id].append(record)
        return record

    def get_record(self, event_id: str) -> Optional[WebhookAuditRecord]:
        """Retrieve the primary (first recorded) audit record for a given event ID."""
        records = self._records_by_event_id.get(event_id, [])
        return records[0] if records else None

    def get_records_by_event_id(self, event_id: str) -> List[WebhookAuditRecord]:
        """Retrieve all historical audit entries for a given event ID in chronological order."""
        return list(self._records_by_event_id.get(event_id, []))

    def get_all_records(self) -> List[WebhookAuditRecord]:
        """Retrieve all append-only historical audit records."""
        return list(self._records)


def translate_razorpay_event_to_base_event(
    webhook_payload: Dict[str, Any],
    correlated_customer_id: str,
    event_id: str,
    merchant_id: str = "merch_codecraft",
) -> Optional[BaseEvent]:
    """
    Translate a Razorpay webhook JSON payload into a canonical REVIVE BaseEvent.
    Uses observable Razorpay attributes only. Never injects hidden simulator ground truth.
    Strictly scoped to Phase A:
    - 'payment_link.paid' is the ONLY primary successful recovery event (-> PAYMENT_SUCCEEDED).
    - 'payment.failed' maps to PAYMENT_FAILED.
    - Other events return None (non-mutating).
    """
    event_name = webhook_payload.get("event", "")
    payload_data = webhook_payload.get("payload", {})

    created_at_raw = webhook_payload.get("created_at")
    if created_at_raw and isinstance(created_at_raw, (int, float)):
        event_dt = datetime.fromtimestamp(created_at_raw, tz=timezone.utc)
    else:
        event_dt = datetime.now(timezone.utc)

    # Primary recovery event for Phase A Payment Links
    if event_name == "payment_link.paid":
        payment_link_entity = payload_data.get("payment_link", {}).get("entity", {})
        payment_entity = payload_data.get("payment", {}).get("entity", {})

        payment_id = payment_entity.get("id") or f"pay_link_{payment_link_entity.get('id', 'unknown')}"
        payment_link_id = payment_link_entity.get("id") or payload_data.get("payment_link_id")
        ref_id = payment_link_entity.get("reference_id") or payment_entity.get("notes", {}).get("reference_id")

        amount_paise = payment_entity.get("amount") or payment_link_entity.get("amount") or 0
        amount_inr = str(Decimal(amount_paise) / Decimal("100.00")) if amount_paise else "0.00"

        currency = payment_entity.get("currency") or payment_link_entity.get("currency") or "INR"
        method = payment_entity.get("method")

        return BaseEvent(
            event_id=f"evt_{event_id}",
            event_type=EventType.PAYMENT_SUCCEEDED,
            schema_version="1.0",
            merchant_id=merchant_id,
            customer_id=correlated_customer_id,
            timestamp=event_dt,
            source="razorpay_webhook",
            payload={
                "payment_id": payment_id,
                "payment_link_id": payment_link_id,
                "amount": amount_inr,
                "currency": currency,
                "reference_id": ref_id,
                "method": method,
                "razorpay_event_id": event_id,
                "razorpay_event_name": event_name,
            },
        )

    if event_name == "payment.failed":
        payment_entity = payload_data.get("payment", {}).get("entity", {})
        payment_id = payment_entity.get("id", "unknown_pay")
        amount_paise = payment_entity.get("amount", 0)
        amount_inr = str(Decimal(amount_paise) / Decimal("100.00")) if amount_paise else "0.00"
        err_code = payment_entity.get("error_code", "PAYMENT_FAILED")
        err_desc = payment_entity.get("error_description", "Payment failed on gateway")

        return BaseEvent(
            event_id=f"evt_{event_id}",
            event_type=EventType.PAYMENT_FAILED,
            schema_version="1.0",
            merchant_id=merchant_id,
            customer_id=correlated_customer_id,
            timestamp=event_dt,
            source="razorpay_webhook",
            payload={
                "payment_id": payment_id,
                "amount": amount_inr,
                "error_code": err_code,
                "error_description": err_desc,
                "razorpay_event_id": event_id,
                "razorpay_event_name": event_name,
            },
        )

    return None


class RazorpayWebhookHandler:
    """
    Thin integration handler connecting Razorpay webhooks to REVIVE outcome measurement.
    Adheres strictly to REVIVE Phase A architectural boundaries.
    """

    def __init__(
        self,
        config: RazorpayConfig = DEFAULT_RAZORPAY_CONFIG,
        audit_logger: Optional[ExecutionAuditLogger] = None,
        outcome_engine: Optional[OutcomeEngine] = None,
        audit_store: Optional[WebhookAuditStore] = None,
        decision_store: Optional[Dict[str, InterventionDecision]] = None,
        decision_plan_store: Optional[Dict[str, Plan]] = None,
        customer_events_store: Optional[Dict[str, List[BaseEvent]]] = None,
    ) -> None:
        self.config = config
        self.audit_logger = audit_logger or ExecutionAuditLogger()
        self.outcome_engine = outcome_engine or OutcomeEngine()
        self.audit_store = audit_store or WebhookAuditStore()
        self.decision_store: Dict[str, InterventionDecision] = decision_store if decision_store is not None else {}
        self.decision_plan_store: Dict[str, Plan] = decision_plan_store if decision_plan_store is not None else {}
        self.customer_events_store: Dict[str, List[BaseEvent]] = customer_events_store if customer_events_store is not None else {}
        self.processed_event_ids: Set[str] = set()

    def bind_decision(
        self,
        decision: InterventionDecision,
        customer_events: Optional[List[BaseEvent]] = None,
        plan: Optional[Plan] = None,
    ) -> None:
        """Store authoritative InterventionDecision and associated Plan for subsequent webhook correlation."""
        decision_id = f"dec_{decision.customer_id}_{decision.decision_timestamp}"
        self.decision_store[decision_id] = decision
        if customer_events is not None:
            self.customer_events_store[decision.customer_id] = list(customer_events)
        if plan is not None:
            self.decision_plan_store[decision_id] = plan

    def process_webhook(
        self,
        raw_body: bytes,
        signature: Optional[str],
        event_id_header: Optional[str],
    ) -> Tuple[int, Dict[str, Any]]:
        """
        Process incoming Razorpay webhook request.
        Returns (http_status_code, response_payload).
        Ensures failed processing attempts remain retryable under at-least-once delivery semantics.
        """
        # 1. Event ID Header Requirement Guard (X-Razorpay-Event-Id is required)
        if not event_id_header or not event_id_header.strip():
            self.audit_store.log_webhook_event(
                event_id="missing_event_id",
                event_type="unknown",
                status=WebhookProcessingStatus.MISSING_EVENT_ID,
                reason="Missing required X-Razorpay-Event-Id header",
            )
            return 400, {
                "error": "Missing required X-Razorpay-Event-Id header",
                "status": "bad_request",
            }

        event_id = event_id_header.strip()

        # 2. Signature Verification Guard (HMAC-SHA256 over raw bytes)
        if not self.config.webhook_secret:
            self.audit_store.log_webhook_event(
                event_id=event_id,
                event_type="unknown",
                status=WebhookProcessingStatus.INVALID_SIGNATURE,
                reason="Server configuration error: RAZORPAY_WEBHOOK_SECRET is not configured",
            )
            return 401, {"error": "Webhook secret not configured on server", "status": "unauthorized"}

        if not verify_webhook_signature(raw_body, signature, self.config.webhook_secret):
            self.audit_store.log_webhook_event(
                event_id=event_id,
                event_type="unknown",
                status=WebhookProcessingStatus.INVALID_SIGNATURE,
                reason="Invalid or missing X-Razorpay-Signature header",
            )
            return 401, {"error": "Invalid webhook signature", "status": "unauthorized"}

        # 3. JSON Parsing & Schema Validation Guard
        try:
            payload_json = json.loads(raw_body.decode("utf-8"))
            if not isinstance(payload_json, dict):
                raise ValueError("JSON root must be an object")
        except Exception as e:
            self.audit_store.log_webhook_event(
                event_id=event_id,
                event_type="unknown",
                status=WebhookProcessingStatus.MALFORMED_PAYLOAD,
                reason=f"Malformed JSON payload: {str(e)}",
            )
            return 400, {"error": "Malformed JSON payload", "status": "bad_request"}

        event_type = payload_json.get("event", "unknown")

        # 4. Webhook Delivery Idempotency Guard (In-memory successfully consumed X-Razorpay-Event-Id deduplication)
        # Only already-successfully-consumed or terminally-ignored events are treated as duplicates.
        if event_id in self.processed_event_ids:
            self.audit_store.log_webhook_event(
                event_id=event_id,
                event_type=event_type,
                status=WebhookProcessingStatus.DUPLICATE_IGNORED,
                reason=f"Duplicate delivery of already-consumed event_id '{event_id}' safely ignored",
            )
            return 200, {
                "status": "duplicate_acknowledged",
                "event_id": event_id,
                "message": "Event already processed",
            }

        # 5. Supported Event Scope Guard (Strictly bounded Phase A events)
        # Non-primary / informational events are terminally acknowledged safely without mutation.
        if event_type not in {"payment_link.paid", "payment.failed"}:
            self.processed_event_ids.add(event_id)  # Terminally handled / ignored
            self.audit_store.log_webhook_event(
                event_id=event_id,
                event_type=event_type,
                status=WebhookProcessingStatus.UNSUPPORTED_IGNORED,
                reason=f"Event type '{event_type}' is not a primary recovery event under Phase A and was ignored safely",
            )
            return 200, {
                "status": "ignored",
                "event_id": event_id,
                "event_type": event_type,
                "message": "Event type ignored safely",
            }

        # 6. Extract reference_id (mapped to REVIVE payload_id)
        payload_data = payload_json.get("payload", {})
        payment_link_entity = payload_data.get("payment_link", {}).get("entity", {})
        payment_entity = payload_data.get("payment", {}).get("entity", {})

        reference_id = (
            payment_link_entity.get("reference_id")
            or payment_entity.get("notes", {}).get("reference_id")
            or payload_data.get("reference_id")
        )

        try:
            # 7. Exact Correlation: reference_id -> payload_id -> ExecutionAuditRecord ONLY
            # No customer-name fallback is permitted.
            matched_exec_record: Optional[ExecutionAuditRecord] = None
            if reference_id and isinstance(reference_id, str) and reference_id.strip():
                ref_clean = reference_id.strip()
                for rec in self.audit_logger._audit_store.values():
                    if rec.payload_id == ref_clean:
                        matched_exec_record = rec
                        break

            if not matched_exec_record:
                # Processing failure: DO NOT mark as processed, allow subsequent retry
                self.audit_store.log_webhook_event(
                    event_id=event_id,
                    event_type=event_type,
                    status=WebhookProcessingStatus.UNMATCHED_REFERENCE,
                    reference_id=reference_id,
                    reason=f"Exact correlation failed: no ExecutionAuditRecord found matching payload_id '{reference_id}'",
                )
                return 404, {
                    "error": "Execution reference not found",
                    "reference_id": reference_id,
                    "status": "not_found",
                }

            customer_id = matched_exec_record.customer_id

            # 8. Decision Context Resolution Guard: Exact decision_id match ONLY.
            # Zero fallback to customer_id, payload_id, or synthetic generation.
            decision = self.decision_store.get(matched_exec_record.decision_id)

            if not decision:
                # Processing failure: DO NOT mark as processed, allow subsequent retry
                self.audit_store.log_webhook_event(
                    event_id=event_id,
                    event_type=event_type,
                    status=WebhookProcessingStatus.DECISION_UNAVAILABLE,
                    reference_id=reference_id,
                    execution_id=matched_exec_record.execution_id,
                    customer_id=customer_id,
                    reason=f"Authoritative decision context unavailable for decision_id '{matched_exec_record.decision_id}'. Synthetic decisions and fallbacks are forbidden.",
                )
                return 422, {
                    "error": "Authoritative decision context unavailable for execution",
                    "execution_id": matched_exec_record.execution_id,
                    "decision_id": matched_exec_record.decision_id,
                    "status": "decision_unavailable",
                }

            # 9. Plan Context Resolution Guard: Exact decision_id -> Plan match ONLY.
            # Zero fallback to 'pro', first available plan in store, or arbitrary defaults.
            plan = self.decision_plan_store.get(matched_exec_record.decision_id)

            if not plan:
                # Processing failure: DO NOT mark as processed, allow subsequent retry
                self.audit_store.log_webhook_event(
                    event_id=event_id,
                    event_type=event_type,
                    status=WebhookProcessingStatus.PLAN_UNAVAILABLE,
                    reference_id=reference_id,
                    execution_id=matched_exec_record.execution_id,
                    customer_id=customer_id,
                    reason=f"Authoritative plan context unavailable for decision_id '{matched_exec_record.decision_id}'. Fallbacks are forbidden.",
                )
                return 422, {
                    "error": "Authoritative plan context unavailable for decision",
                    "execution_id": matched_exec_record.execution_id,
                    "decision_id": matched_exec_record.decision_id,
                    "status": "plan_unavailable",
                }

            # 10. Translate Razorpay Event into Canonical BaseEvent
            base_event = translate_razorpay_event_to_base_event(
                webhook_payload=payload_json,
                correlated_customer_id=customer_id,
                event_id=event_id,
                merchant_id=matched_exec_record.merchant_id,
            )

            if not base_event:
                self.processed_event_ids.add(event_id)  # Terminally handled / ignored
                self.audit_store.log_webhook_event(
                    event_id=event_id,
                    event_type=event_type,
                    status=WebhookProcessingStatus.UNSUPPORTED_IGNORED,
                    reference_id=reference_id,
                    execution_id=matched_exec_record.execution_id,
                    customer_id=customer_id,
                    reason="Event produced no observable BaseEvent transition",
                )
                return 200, {
                    "status": "ignored",
                    "event_id": event_id,
                    "message": "Event produced no domain transition",
                }

            # 11. Ingest into Existing OutcomeEngine
            existing_events = self.customer_events_store.get(customer_id, [])
            all_customer_events = existing_events + [base_event]
            self.customer_events_store[customer_id] = all_customer_events

            outcome_record = self.outcome_engine.measure_outcome(
                execution_record=matched_exec_record,
                decision=decision,
                customer_events=all_customer_events,
                plan=plan,
            )

            # 12. Terminal Success: Mark event as successfully consumed and audit
            self.processed_event_ids.add(event_id)
            self.audit_store.log_webhook_event(
                event_id=event_id,
                event_type=event_type,
                status=WebhookProcessingStatus.PROCESSED,
                reference_id=reference_id,
                execution_id=matched_exec_record.execution_id,
                customer_id=customer_id,
                outcome_id=outcome_record.outcome_id,
                reason=f"Successfully measured outcome: {outcome_record.outcome.value} ({outcome_record.attribution_status.value})",
            )

            return 200, {
                "status": "processed",
                "event_id": event_id,
                "event_type": event_type,
                "customer_id": customer_id,
                "execution_id": matched_exec_record.execution_id,
                "outcome_id": outcome_record.outcome_id,
                "outcome": outcome_record.outcome.value,
                "attribution_status": outcome_record.attribution_status.value,
                "attributable_revenue": float(outcome_record.attributable_revenue),
                "net_recovered_revenue": float(outcome_record.net_recovered_revenue),
                "payment_reference": outcome_record.payment_reference,
                "plan_id": plan.plan_id,
            }

        except Exception as e:
            # Unexpected processing failure: DO NOT mark as processed, allow retry
            self.audit_store.log_webhook_event(
                event_id=event_id,
                event_type=event_type,
                status=WebhookProcessingStatus.MALFORMED_PAYLOAD,
                reference_id=reference_id,
                reason=f"Unexpected internal webhook processing error: {str(e)}",
            )
            return 500, {
                "error": "Internal webhook processing error",
                "status": "internal_error",
                "message": str(e),
            }


class ReviveRuntimeContext:
    """
    Authoritative shared runtime execution and webhook context for REVIVE.
    Maintains unified execution audit logging, decision registry, plan association,
    outcome engine, and webhook handling across the entire application lifecycle.
    """

    def __init__(
        self,
        config: RazorpayConfig = DEFAULT_RAZORPAY_CONFIG,
        audit_logger: Optional[ExecutionAuditLogger] = None,
        outcome_engine: Optional[OutcomeEngine] = None,
        audit_store: Optional[WebhookAuditStore] = None,
    ) -> None:
        self.config = config
        self.audit_logger = audit_logger or ExecutionAuditLogger()
        self.outcome_engine = outcome_engine or OutcomeEngine()
        self.audit_store = audit_store or WebhookAuditStore()
        self.decision_store: Dict[str, InterventionDecision] = {}
        self.decision_plan_store: Dict[str, Plan] = {}
        self.customer_events_store: Dict[str, List[BaseEvent]] = {}
        self.webhook_handler = RazorpayWebhookHandler(
            config=self.config,
            audit_logger=self.audit_logger,
            outcome_engine=self.outcome_engine,
            audit_store=self.audit_store,
            decision_store=self.decision_store,
            decision_plan_store=self.decision_plan_store,
            customer_events_store=self.customer_events_store,
        )

    def record_decision(
        self,
        decision: InterventionDecision,
        customer_events: Optional[List[BaseEvent]] = None,
        plan: Optional[Plan] = None,
    ) -> None:
        """Record an authoritative InterventionDecision and associated Plan into the shared registry."""
        decision_id = f"dec_{decision.customer_id}_{decision.decision_timestamp}"
        self.decision_store[decision_id] = decision
        if customer_events is not None:
            self.customer_events_store[decision.customer_id] = list(customer_events)
        if plan is not None:
            self.decision_plan_store[decision_id] = plan

    def create_execution_engine(
        self,
        dispatcher: Optional[Any] = None,
        config: Optional[Any] = None,
    ) -> Any:
        """Create an ExecutionEngine bound to this authoritative shared runtime audit logger."""
        from app.execution.engine import ExecutionEngine
        return ExecutionEngine(
            config=config or self.audit_logger.config,
            audit_logger=self.audit_logger,
            dispatcher=dispatcher,
        )

    def execute_decision(
        self,
        decision: InterventionDecision,
        customer_events: Optional[List[BaseEvent]] = None,
        plan: Optional[Plan] = None,
        dispatcher: Optional[Any] = None,
    ) -> ExecutionAuditRecord:
        """
        Execute an InterventionDecision using the authoritative execution engine,
        automatically registering the decision, plan association, and audit record into the shared context.
        """
        self.record_decision(decision, customer_events=customer_events, plan=plan)
        engine = self.create_execution_engine(dispatcher=dispatcher)
        return engine.execute_decision(decision)
