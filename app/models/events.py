"""Contains the canonical event envelope used to represent customer/revenue lifecycle events."""

from datetime import datetime
from typing import Any, Dict

from pydantic import BaseModel, ConfigDict, Field, field_validator, ValidationInfo

from app.models.enums import EventType


def _validate_non_empty_string(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


class BaseEvent(BaseModel):
    """Canonical event model representing all domain events in Revive."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    event_type: EventType
    schema_version: str = "1.0"
    merchant_id: str
    customer_id: str
    timestamp: datetime
    source: str
    payload: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_id", "merchant_id", "customer_id", "source", "schema_version")
    @classmethod
    def validate_non_empty_strings(cls, v: Any, info: ValidationInfo) -> str:
        return _validate_non_empty_string(info.field_name or "field", v)

    @field_validator("timestamp")
    @classmethod
    def validate_tz_aware_timestamp(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.tzinfo.utcoffset(v) is None:
            raise ValueError("timestamp must be timezone-aware")
        return v

    @field_validator("payload", mode="before")
    @classmethod
    def validate_payload_dict(cls, v: Any) -> Dict[str, Any]:
        if not isinstance(v, dict):
            raise ValueError("payload must be a dictionary")
        return v
