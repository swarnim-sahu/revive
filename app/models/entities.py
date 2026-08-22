"""Contains core in-memory domain entities."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator, ValidationInfo

from app.models.enums import (
    InterventionStatus,
    InterventionType,
    PaymentStatus,
    SubscriptionStatus,
    TrialStatus,
)


def _validate_non_empty_string(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _validate_tz_aware_datetime(field_name: str, value: datetime) -> datetime:
    if value is not None:
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _validate_non_negative_decimal(field_name: str, value: Decimal) -> Decimal:
    if value < Decimal("0"):
        raise ValueError(f"{field_name} must be non-negative")
    return value


class Merchant(BaseModel):
    """Merchant entity representing a subscription business using Revive."""

    model_config = ConfigDict(extra="forbid")

    merchant_id: str
    name: str
    currency: str = "INR"
    timezone: str = "UTC"

    @field_validator("merchant_id", "name", "currency", "timezone")
    @classmethod
    def validate_strings(cls, v: Any, info: ValidationInfo) -> str:
        return _validate_non_empty_string(info.field_name or "field", v)


class Customer(BaseModel):
    """Customer entity within a merchant's domain."""

    model_config = ConfigDict(extra="forbid")

    customer_id: str
    merchant_id: str
    created_at: datetime
    plan_id: str

    @field_validator("customer_id", "merchant_id", "plan_id")
    @classmethod
    def validate_strings(cls, v: Any, info: ValidationInfo) -> str:
        return _validate_non_empty_string(info.field_name or "field", v)

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, v: datetime, info: ValidationInfo) -> datetime:
        return _validate_tz_aware_datetime(info.field_name or "created_at", v)


class Plan(BaseModel):
    """Subscription plan offered by a merchant."""

    model_config = ConfigDict(extra="forbid")

    plan_id: str
    name: str
    # Monetary amounts use Decimal to avoid floating-point precision errors.
    price: Decimal
    currency: str = "INR"
    billing_interval: str = "month"

    @field_validator("plan_id", "name", "currency", "billing_interval")
    @classmethod
    def validate_strings(cls, v: Any, info: ValidationInfo) -> str:
        return _validate_non_empty_string(info.field_name or "field", v)

    @field_validator("price")
    @classmethod
    def validate_price(cls, v: Decimal, info: ValidationInfo) -> Decimal:
        return _validate_non_negative_decimal(info.field_name or "price", v)


class Trial(BaseModel):
    """Trial period entity tracking customer conversion window."""

    model_config = ConfigDict(extra="forbid")

    trial_id: str
    customer_id: str
    start_at: datetime
    end_at: datetime
    status: TrialStatus

    @field_validator("trial_id", "customer_id")
    @classmethod
    def validate_strings(cls, v: Any, info: ValidationInfo) -> str:
        return _validate_non_empty_string(info.field_name or "field", v)

    @field_validator("start_at", "end_at")
    @classmethod
    def validate_datetimes(cls, v: datetime, info: ValidationInfo) -> datetime:
        return _validate_tz_aware_datetime(info.field_name or "datetime", v)

    @model_validator(mode="after")
    def validate_end_after_start(self) -> "Trial":
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be strictly after start_at")
        return self


class Subscription(BaseModel):
    """Active or past subscription entity for a customer."""

    model_config = ConfigDict(extra="forbid")

    subscription_id: str
    customer_id: str
    plan_id: str
    status: SubscriptionStatus
    # Monetary amounts use Decimal to avoid floating-point precision errors.
    amount: Decimal
    created_at: datetime

    @field_validator("subscription_id", "customer_id", "plan_id")
    @classmethod
    def validate_strings(cls, v: Any, info: ValidationInfo) -> str:
        return _validate_non_empty_string(info.field_name or "field", v)

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, v: datetime, info: ValidationInfo) -> datetime:
        return _validate_tz_aware_datetime(info.field_name or "created_at", v)

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal, info: ValidationInfo) -> Decimal:
        return _validate_non_negative_decimal(info.field_name or "amount", v)


class Payment(BaseModel):
    """Payment attempt or transaction entity."""

    model_config = ConfigDict(extra="forbid")

    payment_id: str
    customer_id: str
    # Monetary amounts use Decimal to avoid floating-point precision errors.
    amount: Decimal
    status: PaymentStatus
    method: str
    failure_reason: Optional[str] = None
    created_at: datetime

    @field_validator("payment_id", "customer_id", "method")
    @classmethod
    def validate_strings(cls, v: Any, info: ValidationInfo) -> str:
        return _validate_non_empty_string(info.field_name or "field", v)

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, v: datetime, info: ValidationInfo) -> datetime:
        return _validate_tz_aware_datetime(info.field_name or "created_at", v)

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal, info: ValidationInfo) -> Decimal:
        return _validate_non_negative_decimal(info.field_name or "amount", v)


class Intervention(BaseModel):
    """Intervention record tracking proposed or executed recovery actions."""

    model_config = ConfigDict(extra="forbid")

    intervention_id: str
    customer_id: str
    action: InterventionType
    status: InterventionStatus
    # Monetary amounts use Decimal to avoid floating-point precision errors.
    expected_value: Decimal
    actual_revenue: Optional[Decimal] = None
    created_at: datetime

    @field_validator("intervention_id", "customer_id")
    @classmethod
    def validate_strings(cls, v: Any, info: ValidationInfo) -> str:
        return _validate_non_empty_string(info.field_name or "field", v)

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, v: datetime, info: ValidationInfo) -> datetime:
        return _validate_tz_aware_datetime(info.field_name or "created_at", v)

    @field_validator("expected_value")
    @classmethod
    def validate_expected_value(cls, v: Decimal, info: ValidationInfo) -> Decimal:
        return _validate_non_negative_decimal(info.field_name or "expected_value", v)

    @field_validator("actual_revenue")
    @classmethod
    def validate_actual_revenue(cls, v: Optional[Decimal], info: ValidationInfo) -> Optional[Decimal]:
        if v is not None:
            return _validate_non_negative_decimal(info.field_name or "actual_revenue", v)
        return v
