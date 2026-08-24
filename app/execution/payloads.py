"""
Deterministic Payload Builder Module for Revive Phase 6 Execution Layer.
Constructs structured, auditable, test-mode recovery action payloads for bounded interventions.
"""

import hashlib
from typing import Optional
from app.intervention.schemas import InterventionAction, InterventionDecision
from app.execution.schemas import InterventionPayload


class PayloadBuilder:
    """Constructs deterministic, auditable workflow payloads for executable Phase 5 actions."""

    @classmethod
    def build_payload(
        cls, decision: InterventionDecision
    ) -> Optional[InterventionPayload]:
        """
        Build an InterventionPayload for a given decision.
        Returns None for non-executable actions (NO_ACTION, HUMAN_REVIEW).
        """
        act = decision.selected_action

        if act in {InterventionAction.NO_ACTION, InterventionAction.HUMAN_REVIEW}:
            return None

        # Hash customer ID + decision timestamp to generate deterministic payload ID
        hash_id = hashlib.md5(
            f"{decision.customer_id}_{decision.decision_timestamp}".encode("utf-8")
        ).hexdigest()[:8]

        cid = decision.customer_id

        if act == InterventionAction.PRODUCT_GUIDANCE:
            return InterventionPayload(
                payload_id=f"payload_pg_{hash_id}",
                action=act,
                customer_id=cid,
                headline="Explore Your Active Features",
                body="You have unactivated feature capabilities in your trial. Click below for guided setup.",
                target_url=f"sim://revive/product-guidance?cid={cid}",
                parameters={"guidance_type": "in_app_tooltip", "feature_focus": "core_workflow"},
            )

        if act == InterventionAction.REMINDER:
            return InterventionPayload(
                payload_id=f"payload_rem_{hash_id}",
                action=act,
                customer_id=cid,
                headline="Your Trial Expiry Is Approaching",
                body="Friendly reminder that your plan trial is ending soon. Secure your subscription today.",
                target_url=f"sim://revive/trial-reminder?cid={cid}",
                parameters={"channel": "email_and_in_app", "template_id": "trial_expiry_prompt"},
            )

        if act == InterventionAction.CHECKOUT_ASSISTANCE:
            return InterventionPayload(
                payload_id=f"payload_chk_{hash_id}",
                action=act,
                customer_id=cid,
                headline="Resume Your Saved Checkout",
                body="We saved your checkout session. Click to complete your plan subscription seamlessly.",
                target_url=f"sim://revive/checkout-assistance?cid={cid}&session=sess_{hash_id}",
                parameters={"recovery_mode": "resume_checkout_link", "discount_applied": False},
            )

        if act == InterventionAction.PAYMENT_RECOVERY:
            return InterventionPayload(
                payload_id=f"payload_pay_{hash_id}",
                action=act,
                customer_id=cid,
                headline="Update Your Subscription Payment Method",
                body="Your payment method requires update to complete subscription setup. Click to retry safely.",
                target_url=f"sim://revive/payment-recovery?cid={cid}&token=tok_{hash_id}",
                parameters={"recovery_mode": "alternate_payment_prompt", "gateway": "razorpay_test_mode"},
            )

        if act == InterventionAction.TRIAL_EXTENSION:
            return InterventionPayload(
                payload_id=f"payload_ext_{hash_id}",
                action=act,
                customer_id=cid,
                headline="3-Day Trial Extension Granted",
                body="We added 3 extra days to your trial so you can evaluate all features without interruption.",
                target_url=f"sim://revive/trial-extension?cid={cid}&token=grant_ext_{hash_id}",
                parameters={"extension_days": 3, "grant_token": f"grant_ext_{hash_id}"},
            )

        return None
