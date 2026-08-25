"""
Razorpay Sandbox Execution Dispatcher for Revive Phase 9.
Implements the Phase 6 ExecutionDispatcher interface to route authorized PAYMENT_RECOVERY payloads
to Razorpay payment link generation without altering Phase 5 policy authority.
"""

from typing import Optional
from app.execution.dispatcher import ExecutionDispatcher
from app.execution.schemas import InterventionPayload
from app.intervention.schemas import InterventionAction
from app.integrations.razorpay.config import DEFAULT_RAZORPAY_CONFIG, RazorpayConfig
from app.integrations.razorpay.client import BaseRazorpayClient, MockRazorpayClient
from app.integrations.razorpay.schemas import (
    RazorpayCustomerInfo,
    RazorpayPaymentLinkRequest,
)


class RazorpaySandboxDispatcher(ExecutionDispatcher):
    """
    Razorpay Sandbox Execution Dispatcher.
    Adapter implementing the existing Phase 6 ExecutionDispatcher interface.
    """

    def __init__(
        self,
        config: RazorpayConfig = DEFAULT_RAZORPAY_CONFIG,
        client: Optional[BaseRazorpayClient] = None,
    ) -> None:
        self.config = config
        self.client = client or MockRazorpayClient(config=config)

    def dispatch(
        self,
        payload: InterventionPayload,
        environment: str,
        simulated_failure: Optional[str] = None,
    ) -> Optional[str]:
        """
        Dispatch InterventionPayload through Razorpay payment link generation.
        Returns None if dispatch succeeded, or a failure reason string if dispatch failed.
        """
        # 1. Action Type Validation: Only PAYMENT_RECOVERY and CHECKOUT_ASSISTANCE are supported for payment link creation
        if payload.action not in {InterventionAction.PAYMENT_RECOVERY, InterventionAction.CHECKOUT_ASSISTANCE}:
            return f"RazorpaySandboxDispatcher refused: Action '{payload.action.value}' is not supported for Razorpay payment link dispatch"

        # 2. Extract amount in paise (default to ₹999.00 = 99900 paise if omitted in parameters)
        amount_paise = int(payload.parameters.get("amount_paise", 99900))

        # 3. Construct minimum typed Razorpay payment link request from existing InterventionPayload fields ONLY
        req = RazorpayPaymentLinkRequest(
            amount=amount_paise,
            currency=self.config.currency,
            description=f"{payload.headline}: {payload.body}",
            customer=RazorpayCustomerInfo(
                name=payload.customer_id,
                email=payload.parameters.get("email", f"{payload.customer_id}@example.com"),
            ),
            reference_id=payload.payload_id,
            callback_url=f"https://revive.example.com/payment-callback?payload_id={payload.payload_id}",
        )

        # If simulated failure passed, pass it to client if mock
        if simulated_failure and isinstance(self.client, MockRazorpayClient):
            self.client.simulated_failure_reason = simulated_failure

        # 4. Invoke client with payload.payload_id as idempotency key
        response, err = self.client.create_payment_link(
            request=req,
            idempotency_key=payload.payload_id,
        )

        if err:
            return err

        if response and response.short_url:
            payload.target_url = response.short_url

        return None
