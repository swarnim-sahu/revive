"""
Core Orchestration Engine for Revive Phase 6 Execution Layer.
Consumes Phase 5 InterventionDecisions, enforces execution-time safety, cooldown-aware idempotency,
dispatches test-mode recovery workflows via TestModeDispatcher, and maintains an auditable execution trail.
"""

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from app.models.enums import EventType
from app.models.events import BaseEvent
from app.intervention.schemas import InterventionAction, InterventionDecision
from app.execution.config import DEFAULT_EXECUTION_CONFIG, ExecutionConfig
from app.execution.audit import ExecutionAuditLogger
from app.execution.dispatcher import ExecutionDispatcher, TestModeDispatcher
from app.execution.payloads import PayloadBuilder
from app.execution.schemas import ExecutionAuditRecord, ExecutionState, ExecutionStatus, FailureType
from app.execution.state_machine import ExecutionStateMachine


def _parse_timestamp(ts_str: str) -> datetime:
    """Parse an ISO 8601 timestamp string into a timezone-aware datetime."""
    dt = datetime.fromisoformat(ts_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class ExecutionEngine:
    """Core deterministic, side-effect-free Phase 6 execution orchestrator."""

    def __init__(
        self,
        config: ExecutionConfig = DEFAULT_EXECUTION_CONFIG,
        audit_logger: Optional[ExecutionAuditLogger] = None,
        dispatcher: Optional[ExecutionDispatcher] = None,
    ) -> None:
        self.config = config
        self.audit_logger = audit_logger or ExecutionAuditLogger(config=config)
        self.dispatcher = dispatcher or TestModeDispatcher()
        self.state_machine = ExecutionStateMachine(config=config)
        self.emitted_events: List[BaseEvent] = []

    def execute_decision(
        self,
        decision: InterventionDecision,
        feature_record: Optional[Dict[str, Any]] = None,
        failure_simulator: Optional[Callable[[InterventionAction, int], Optional[str]]] = None,
    ) -> ExecutionAuditRecord:
        """
        Execute an authorized Phase 5 InterventionDecision in test/simulation mode.
        Does NOT alter the original Phase 5 decision object.
        """
        # 1. Action & Eligibility Authorization Guard
        if decision.selected_action == InterventionAction.NO_ACTION:
            return self.audit_logger.log_execution_attempt(
                decision=decision,
                status=ExecutionStatus.NO_ACTION,
                attempt_number=1,
            )

        if decision.eligibility_status == "INELIGIBLE":
            record = self.audit_logger.log_execution_attempt(
                decision=decision,
                status=ExecutionStatus.BLOCKED,
                attempt_number=1,
                failure_type=FailureType.NON_RETRYABLE,
                failure_reason="Execution refused: Phase 5 decision marked INELIGIBLE",
            )
            self._emit_event(
                decision,
                EventType.POLICY_REJECTED,
                {
                    "action": decision.selected_action.value,
                    "reason": "ineligible_status",
                    "payload_id": None,
                    "target_url": None,
                },
            )
            return record

        if (
            decision.selected_action == InterventionAction.HUMAN_REVIEW
            or decision.eligibility_status == "ESCALATED"
        ):
            record = self.audit_logger.log_execution_attempt(
                decision=decision,
                status=ExecutionStatus.ESCALATED,
                attempt_number=1,
                escalation_reason=decision.decision_reason or "Escalated for human review",
            )
            self._emit_event(
                decision,
                EventType.RECOVERY_ESCALATED,
                {
                    "action": "HUMAN_REVIEW",
                    "reason": "human_review_requested",
                    "payload_id": None,
                    "target_url": None,
                },
            )
            return record

        # 2. Idempotency & Cooldown Guard
        decision_id = f"dec_{decision.customer_id}_{decision.decision_timestamp}"
        customer_history = self.audit_logger.get_customer_audit_history(decision.customer_id)

        # 2a. Exact Duplicate Decision Identity Check (Same decision submitted twice)
        exact_duplicates = [
            r for r in customer_history
            if r.decision_id == decision_id and r.status in {ExecutionStatus.EXECUTED, ExecutionStatus.ESCALATED, ExecutionStatus.BLOCKED}
        ]
        if exact_duplicates:
            # Re-return original execution record without emitting duplicate event
            return exact_duplicates[0]

        # 2b. Cooldown Window Check across previous executed active interventions
        executable_actions = {
            InterventionAction.PRODUCT_GUIDANCE,
            InterventionAction.REMINDER,
            InterventionAction.CHECKOUT_ASSISTANCE,
            InterventionAction.PAYMENT_RECOVERY,
            InterventionAction.TRIAL_EXTENSION,
        }
        active_executed_records = [
            r for r in customer_history
            if r.status == ExecutionStatus.EXECUTED and r.action in executable_actions
        ]

        if active_executed_records:
            curr_dt = _parse_timestamp(decision.decision_timestamp)
            for prev_rec in active_executed_records:
                prev_dt = _parse_timestamp(prev_rec.execution_timestamp)
                elapsed_hours = (curr_dt - prev_dt).total_seconds() / 3600.0
                if elapsed_hours >= 0 and elapsed_hours < self.config.cooldown_period_hours:
                    # Inside active intervention cooldown period -> Block execution
                    record = self.audit_logger.log_execution_attempt(
                        decision=decision,
                        status=ExecutionStatus.BLOCKED,
                        attempt_number=1,
                        failure_type=FailureType.NON_RETRYABLE,
                        failure_reason=f"Execution blocked: customer {decision.customer_id} is in active intervention cooldown window ({elapsed_hours:.1f}h / {self.config.cooldown_period_hours:.1f}h elapsed)",
                    )
                    self._emit_event(
                        decision,
                        EventType.POLICY_REJECTED,
                        {
                            "action": decision.selected_action.value,
                            "reason": "cooldown_active",
                            "elapsed_hours": elapsed_hours,
                            "cooldown_period_hours": self.config.cooldown_period_hours,
                            "payload_id": None,
                            "target_url": None,
                        },
                    )
                    return record

        # 3. Payload Construction
        payload = PayloadBuilder.build_payload(decision)

        # 4. Dispatch Loop with Bounded Retries (Attempts 1 to max_retries + 1)
        max_attempts = self.config.max_retries + 1
        current_action = decision.selected_action

        for attempt in range(1, max_attempts + 1):
            simulated_fail = failure_simulator(current_action, attempt) if failure_simulator else None

            # Dispatch via ExecutionDispatcher (structurally enforces TEST_MODE sandbox)
            dispatch_failure = self.dispatcher.dispatch(
                payload=payload,
                environment=self.config.environment,
                simulated_failure=simulated_fail,
            )

            if not dispatch_failure:
                # Dispatch Succeeded!
                record = self.audit_logger.log_execution_attempt(
                    decision=decision,
                    status=ExecutionStatus.EXECUTED,
                    attempt_number=attempt,
                    payload_id=payload.payload_id if payload else None,
                    target_url=payload.target_url if payload else None,
                )
                self._emit_event(
                    decision,
                    EventType.RECOVERY_ACTION_EXECUTED,
                    {
                        "action": current_action.value,
                        "payload_id": payload.payload_id if payload else None,
                        "target_url": payload.target_url if payload else None,
                        "attempt": attempt,
                        "environment": self.config.environment,
                    },
                )
                return record

            # Dispatch Failed! Classify and evaluate transition
            failure_type = self.state_machine.classify_failure(dispatch_failure)
            next_state, fallback_action = self.state_machine.evaluate_failure_transition(
                current_action, attempt, failure_type
            )

            if next_state == ExecutionState.RETRY:
                # Intermediate attempt failure with retries remaining
                self.audit_logger.log_execution_attempt(
                    decision=decision,
                    status=ExecutionStatus.FAILED,
                    attempt_number=attempt,
                    payload_id=payload.payload_id if payload else None,
                    target_url=payload.target_url if payload else None,
                    failure_type=failure_type,
                    failure_reason=dispatch_failure,
                )
                self._emit_event(
                    decision,
                    EventType.RECOVERY_ACTION_FAILED,
                    {
                        "action": current_action.value,
                        "attempt": attempt,
                        "failure_type": failure_type.value,
                        "failure_reason": dispatch_failure,
                        "payload_id": payload.payload_id if payload else None,
                        "target_url": payload.target_url if payload else None,
                    },
                )
                continue

            if next_state == ExecutionState.FALLBACK and fallback_action:
                # Log primary attempt failure
                self.audit_logger.log_execution_attempt(
                    decision=decision,
                    status=ExecutionStatus.FAILED,
                    attempt_number=attempt,
                    payload_id=payload.payload_id if payload else None,
                    target_url=payload.target_url if payload else None,
                    failure_type=failure_type,
                    failure_reason=dispatch_failure,
                )
                self._emit_event(
                    decision,
                    EventType.RECOVERY_ACTION_FAILED,
                    {
                        "action": current_action.value,
                        "attempt": attempt,
                        "failure_type": failure_type.value,
                        "failure_reason": dispatch_failure,
                        "payload_id": payload.payload_id if payload else None,
                        "target_url": payload.target_url if payload else None,
                    },
                )

                # Attempt Fallback Action Dispatch
                fallback_decision = decision.model_copy(update={"selected_action": fallback_action})
                fallback_payload = PayloadBuilder.build_payload(fallback_decision)

                fb_dispatch_fail = self.dispatcher.dispatch(
                    payload=fallback_payload,
                    environment=self.config.environment,
                    simulated_failure=None,
                )

                if not fb_dispatch_fail:
                    fb_record = self.audit_logger.log_execution_attempt(
                        decision=decision,
                        status=ExecutionStatus.EXECUTED,
                        attempt_number=attempt,
                        action_override=fallback_action,
                        is_fallback=True,
                        payload_id=fallback_payload.payload_id if fallback_payload else None,
                        target_url=fallback_payload.target_url if fallback_payload else None,
                        failure_type=failure_type,
                        failure_reason=f"Primary action {current_action.value} failed: {dispatch_failure}",
                        fallback_action=fallback_action,
                    )
                    self._emit_event(
                        decision,
                        EventType.RECOVERY_ACTION_EXECUTED,
                        {
                            "action": fallback_action.value,
                            "primary_action_failed": current_action.value,
                            "payload_id": fallback_payload.payload_id if fallback_payload else None,
                            "target_url": fallback_payload.target_url if fallback_payload else None,
                            "is_fallback": True,
                        },
                    )
                    return fb_record

            # Next state is ESCALATED: Log single ESCALATED terminal audit record
            record = self.audit_logger.log_execution_attempt(
                decision=decision,
                status=ExecutionStatus.ESCALATED,
                attempt_number=attempt,
                payload_id=payload.payload_id if payload else None,
                target_url=payload.target_url if payload else None,
                failure_type=failure_type,
                failure_reason=dispatch_failure,
                escalation_reason=f"Execution failed on attempt {attempt}: {dispatch_failure}",
            )
            self._emit_event(
                decision,
                EventType.RECOVERY_ESCALATED,
                {
                    "action": current_action.value,
                    "attempt": attempt,
                    "failure_reason": dispatch_failure,
                    "payload_id": payload.payload_id if payload else None,
                    "target_url": payload.target_url if payload else None,
                },
            )
            return record

        # Terminal Escalation Safety Net
        record = self.audit_logger.log_execution_attempt(
            decision=decision,
            status=ExecutionStatus.ESCALATED,
            attempt_number=max_attempts,
            escalation_reason="Retry budget exhausted without resolution",
        )
        self._emit_event(
            decision,
            EventType.RECOVERY_ESCALATED,
            {
                "action": current_action.value,
                "reason": "retry_budget_exhausted",
                "payload_id": None,
                "target_url": None,
            },
        )
        return record

    def _emit_event(
        self, decision: InterventionDecision, event_type: EventType, details: Dict[str, Any]
    ) -> BaseEvent:
        """Construct and emit a canonical BaseEvent deterministically from decision execution context."""
        evt_dt = _parse_timestamp(decision.decision_timestamp)
        seq_idx = len(self.emitted_events)
        event_id = f"evt_exec_{decision.customer_id}_{decision.decision_timestamp}_{event_type.value}_{seq_idx}"

        evt = BaseEvent(
            event_id=event_id,
            event_type=event_type,
            schema_version="1.0",
            merchant_id="merch_codecraft",
            customer_id=decision.customer_id,
            timestamp=evt_dt,
            source="revive_phase6_execution_engine",
            payload={
                "decision_id": f"dec_{decision.customer_id}_{decision.decision_timestamp}",
                "customer_id": decision.customer_id,
                **details,
            },
        )
        self.emitted_events.append(evt)
        return evt
