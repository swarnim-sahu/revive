"""
Pydantic Schema Models for Revive Phase 6 Execution & Workflow Engine.
Defines execution lifecycle states, statuses, failure types, workflow payloads, and execution audit records.
"""

from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, ValidationInfo

from app.models.entities import _validate_non_empty_string
from app.intervention.schemas import InterventionAction


class ExecutionState(str, Enum):
    """Internal deterministic state transitions for execution lifecycle."""

    RECEIVED = "RECEIVED"
    AUTHORIZED = "AUTHORIZED"
    IDEMPOTENCY_CHECKED = "IDEMPOTENCY_CHECKED"
    PAYLOAD_BUILT = "PAYLOAD_BUILT"
    DISPATCHING = "DISPATCHING"
    SUCCESS = "SUCCESS"
    FAILURE_CLASSIFIED = "FAILURE_CLASSIFIED"
    RETRY = "RETRY"
    RETRY_EXHAUSTED = "RETRY_EXHAUSTED"
    FALLBACK = "FALLBACK"
    ESCALATED = "ESCALATED"


class ExecutionStatus(str, Enum):
    """Terminal operational execution status returned to caller."""

    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    ESCALATED = "ESCALATED"
    NO_ACTION = "NO_ACTION"


class FailureType(str, Enum):
    """Classification of dispatch and execution failure outcomes."""

    NONE = "NONE"
    RETRYABLE = "RETRYABLE"
    NON_RETRYABLE = "NON_RETRYABLE"


class InterventionPayload(BaseModel):
    """Structured, auditable recovery payload constructed for bounded interventions."""

    model_config = ConfigDict(extra="forbid")

    payload_id: str
    action: InterventionAction
    customer_id: str
    headline: str
    body: str
    target_url: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("payload_id", "customer_id", "headline", "body")
    @classmethod
    def validate_strings(cls, v: str, info: ValidationInfo) -> str:
        return _validate_non_empty_string(info.field_name or "field", v)


class ExecutionAuditRecord(BaseModel):
    """Immutable, auditable record of an intervention execution attempt or terminal outcome."""

    model_config = ConfigDict(extra="forbid")

    execution_id: str
    decision_id: str
    customer_id: str
    merchant_id: str
    execution_timestamp: str
    action: InterventionAction
    status: ExecutionStatus
    attempt_number: int = Field(..., ge=1, le=3, description="Attempt number (1, 2, or 3)")
    payload_id: Optional[str] = None
    target_url: Optional[str] = None
    failure_type: FailureType = FailureType.NONE
    failure_reason: Optional[str] = None
    fallback_action: Optional[InterventionAction] = None
    escalation_reason: Optional[str] = None
    policy_version: str = "v1.0.0"
    execution_version: str = "v1.0.0"

    @field_validator("execution_id", "decision_id", "customer_id", "merchant_id", "execution_timestamp")
    @classmethod
    def validate_audit_strings(cls, v: str, info: ValidationInfo) -> str:
        return _validate_non_empty_string(info.field_name or "field", v)
