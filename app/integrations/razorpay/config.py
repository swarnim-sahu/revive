"""
Configuration Module for Revive Phase 9 Razorpay Sandbox Integration.
Reads credentials safely from environment variables and redacts secrets in __repr__ and __str__.
"""

import os
from typing import Optional
from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class RazorpayConfig(BaseModel):
    """Configuration options for Razorpay sandbox / test mode integration."""

    model_config = ConfigDict(extra="forbid")

    execution_mode: str = "mock"  # "mock" or "sandbox"
    environment: str = "sandbox"
    key_id: Optional[str] = None
    key_secret: Optional[str] = None
    webhook_secret: Optional[str] = None
    request_timeout_seconds: float = 10.0
    base_url: str = "https://api.razorpay.com/v1"
    currency: str = "INR"

    @field_validator("execution_mode")
    @classmethod
    def validate_execution_mode(cls, v: str) -> str:
        clean = (v or "").strip().lower()
        if clean not in {"mock", "sandbox"}:
            raise ValueError(
                f"Invalid RAZORPAY_EXECUTION_MODE: '{v}'. Supported modes are 'mock' and 'sandbox'."
            )
        return clean

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        clean = (v or "").strip().lower()
        if clean in {"production", "live"}:
            raise ValueError(
                "Production/live environment is strictly prohibited in Razorpay Test Mode integration."
            )
        return v

    @field_validator("key_id")
    @classmethod
    def validate_key_id(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v.strip():
            clean = v.strip()
            if clean.startswith("rzp_live_"):
                raise ValueError(
                    "Production Razorpay credentials ('rzp_live_*') are strictly prohibited in sandbox/test mode integration."
                )
        return v

    @model_validator(mode="after")
    def validate_sandbox_mode_credentials(self) -> "RazorpayConfig":
        if self.execution_mode == "sandbox" and self.key_id:
            clean_key = self.key_id.strip()
            if not clean_key.startswith("rzp_test_"):
                raise ValueError(
                    f"Sandbox execution mode requires Razorpay Test Mode credentials ('rzp_test_*'). "
                    f"Provided key does not match test mode prefix."
                )
        return self

    def __repr__(self) -> str:
        secret_str = "'[REDACTED]'" if self.key_secret else "None"
        wh_secret_str = "'[REDACTED]'" if self.webhook_secret else "None"
        return (
            f"RazorpayConfig(execution_mode={self.execution_mode!r}, "
            f"environment={self.environment!r}, key_id={self.key_id!r}, "
            f"key_secret={secret_str}, webhook_secret={wh_secret_str}, "
            f"request_timeout_seconds={self.request_timeout_seconds!r}, "
            f"base_url={self.base_url!r}, currency={self.currency!r})"
        )

    def __str__(self) -> str:
        return self.__repr__()

    @classmethod
    def from_env(cls) -> "RazorpayConfig":
        """Instantiate RazorpayConfig from environment variables."""
        return cls(
            execution_mode=os.environ.get("RAZORPAY_EXECUTION_MODE", "mock"),
            environment=os.environ.get("RAZORPAY_ENV", "sandbox"),
            key_id=os.environ.get("RAZORPAY_KEY_ID", None),
            key_secret=os.environ.get("RAZORPAY_KEY_SECRET", None),
            webhook_secret=os.environ.get("RAZORPAY_WEBHOOK_SECRET", None),
        )


DEFAULT_RAZORPAY_CONFIG = RazorpayConfig.from_env()
