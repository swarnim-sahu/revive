"""
Audit Trail Logging Module for Revive Phase 6 Execution Layer.
Creates and maintains immutable ExecutionAuditRecords for every execution attempt and terminal outcome.

Note on Persistence Boundary:
`ExecutionAuditLogger` serves as an in-memory, deterministic audit repository for TEST_MODE simulation.
In production deployments, this logger maps to an immutable append-only storage sink (e.g., PostgreSQL / Kafka audit log).
Audit records logged in `_audit_store` are immutable once recorded.
"""

from typing import Dict, List, Optional
from app.intervention.schemas import InterventionAction, InterventionDecision
from app.execution.config import DEFAULT_EXECUTION_CONFIG, ExecutionConfig
from app.execution.schemas import ExecutionAuditRecord, ExecutionStatus, FailureType


class ExecutionAuditLogger:
    """Creates and stores immutable execution audit records in compliance with REVIVE Constitution §16."""

    def __init__(self, config: ExecutionConfig = DEFAULT_EXECUTION_CONFIG) -> None:
        self.config = config
        self._audit_store: Dict[str, ExecutionAuditRecord] = {}

    def log_execution_attempt(
        self,
        decision: InterventionDecision,
        status: ExecutionStatus,
        attempt_number: int,
        action_override: Optional[InterventionAction] = None,
        is_fallback: bool = False,
        payload_id: Optional[str] = None,
        target_url: Optional[str] = None,
        failure_type: FailureType = FailureType.NONE,
        failure_reason: Optional[str] = None,
        fallback_action: Optional[InterventionAction] = None,
        escalation_reason: Optional[str] = None,
    ) -> ExecutionAuditRecord:
        """
        Create and record an immutable ExecutionAuditRecord.
        If is_fallback is True, creates a distinct fallback audit identity (exec_..._fb_attN)
        preserving the original failed primary attempt record in audit history.
        """
        prefix = "exec" if not is_fallback else "exec_fb"
        exec_id = f"{prefix}_{decision.customer_id}_{decision.decision_timestamp}_att{attempt_number}"

        if exec_id in self._audit_store:
            # Audit records are strictly immutable: re-return existing record
            return self._audit_store[exec_id]

        record = ExecutionAuditRecord(
            execution_id=exec_id,
            decision_id=f"dec_{decision.customer_id}_{decision.decision_timestamp}",
            customer_id=decision.customer_id,
            merchant_id="merch_codecraft",
            execution_timestamp=decision.decision_timestamp,
            action=action_override or decision.selected_action,
            status=status,
            attempt_number=attempt_number,
            payload_id=payload_id,
            target_url=target_url,
            failure_type=failure_type,
            failure_reason=failure_reason,
            fallback_action=fallback_action,
            escalation_reason=escalation_reason,
            policy_version=self.config.policy_version,
            execution_version=self.config.execution_version,
        )

        self._audit_store[exec_id] = record
        return record

    def get_audit_record(self, execution_id: str) -> Optional[ExecutionAuditRecord]:
        """Retrieve a logged audit record by execution ID."""
        return self._audit_store.get(execution_id)

    def get_customer_audit_history(self, customer_id: str) -> List[ExecutionAuditRecord]:
        """Retrieve all logged audit records for a given customer ID."""
        return [rec for rec in self._audit_store.values() if rec.customer_id == customer_id]
