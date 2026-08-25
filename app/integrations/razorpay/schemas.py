"""
Typed Pydantic Schemas for Razorpay Payment Links API Integration.
"""

from typing import Dict, Optional
from pydantic import BaseModel, ConfigDict, Field


class RazorpayCustomerInfo(BaseModel):
    """Customer metadata for Razorpay payment link creation."""

    model_config = ConfigDict(extra="forbid")

    name: str
    email: Optional[str] = None
    contact: Optional[str] = None


class RazorpayPaymentLinkRequest(BaseModel):
    """Request payload for creating a Razorpay Payment Link."""

    model_config = ConfigDict(extra="forbid")

    amount: int = Field(..., gt=0, description="Amount in smallest currency unit (paise for INR)")
    currency: str = "INR"
    accept_partial: bool = False
    description: str
    customer: RazorpayCustomerInfo
    notify: Dict[str, bool] = Field(default_factory=lambda: {"email": True, "sms": False})
    reminder_enable: bool = True
    reference_id: str
    callback_url: Optional[str] = None
    callback_method: str = "get"


class RazorpayPaymentLinkResponse(BaseModel):
    """Response returned after creating a Razorpay Payment Link."""

    model_config = ConfigDict(extra="forbid")

    payment_link_id: str
    short_url: str
    status: str
    reference_id: str
    amount: int
    currency: str
    created_at: int
