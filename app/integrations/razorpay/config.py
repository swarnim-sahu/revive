"""
Configuration Module for Revive Phase 9 Razorpay Sandbox Integration.
Reads credentials safely from environment variables and redacts secrets in __repr__ and __str__.
"""

import os
from typing import Optional
from pydantic import BaseModel, ConfigDict


class RazorpayConfig(BaseModel):
    """Configuration options for Razorpay sandbox integration."""

    model_config = ConfigDict(extra="forbid")

    environment: str = "sandbox"
    key_id: Optional[str] = None
    key_secret: Optional[str] = None
    webhook_secret: Optional[str] = None
    request_timeout_seconds: float = 10.0
    base_url: str = "https://api.razorpay.com/v1"
    currency: str = "INR"

    def __repr__(self) -> str:
        secret_str = "'[REDACTED]'" if self.key_secret else "None"
        wh_secret_str = "'[REDACTED]'" if self.webhook_secret else "None"
        return (
            f"RazorpayConfig(environment={self.environment!r}, key_id={self.key_id!r}, "
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
            environment=os.environ.get("RAZORPAY_ENV", "sandbox"),
            key_id=os.environ.get("RAZORPAY_KEY_ID", None),
            key_secret=os.environ.get("RAZORPAY_KEY_SECRET", None),
            webhook_secret=os.environ.get("RAZORPAY_WEBHOOK_SECRET", None),
        )


DEFAULT_RAZORPAY_CONFIG = RazorpayConfig.from_env()
