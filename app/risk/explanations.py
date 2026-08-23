"""
Deterministic Observable Risk Explanations for Revive (Phase 3).
Provides human-readable, auditable explanations strictly based on observable signals at prediction snapshot.
NO LLMs are used for Phase 3 explanations.
"""

from typing import Any, Dict, List


class DeterministicRiskExplainer:
    """Generates deterministic, feature-based evidence bullet points for customer risk predictions."""

    @staticmethod
    def explain(feature_record: Dict[str, Any], risk_score: float, risk_tier: str) -> List[str]:
        """
        Generate bullet point explanations based on observable feature thresholds.
        Does NOT access or mention hidden generation segments or ground truth fields.
        """
        reasons: List[str] = []

        # 1. Trial Expiry Signal
        hours_expiry = feature_record.get("hours_until_trial_expiry", 999.0)
        if hours_expiry <= 24.0:
            reasons.append("Trial expires within 24 hours")
        elif hours_expiry <= 48.0:
            reasons.append("Trial expiring within 48 hours")

        # 2. Payment Friction Signal
        payment_failures = feature_record.get("payment_failure_count", 0)
        if payment_failures > 0:
            reasons.append(f"Previous payment failure detected ({payment_failures} failed attempt(s))")

        # 3. Checkout Abandonment Signal
        checkout_started = feature_record.get("checkout_started", 0)
        checkout_completed = feature_record.get("checkout_completed", 0)
        if checkout_started == 1 and checkout_completed == 0:
            reasons.append("Checkout was initiated but not completed")

        # 4. High Pricing Intent without Checkout
        pricing_views = feature_record.get("pricing_view_count", 0)
        if pricing_views >= 2 and checkout_started == 0:
            reasons.append(f"Viewed pricing {pricing_views} times without initiating checkout")

        # 5. Low Engagement / Inactivity Signal
        hours_activity = feature_record.get("hours_since_last_activity", 0.0)
        sessions = feature_record.get("session_count", 0)
        if hours_activity >= 48.0:
            reasons.append("Low recent activity (no product engagement in the last 48 hours)")

        if sessions <= 2:
            reasons.append("Low overall product usage during trial")

        # Fallback if no specific high-risk trigger condition met
        if not reasons:
            if risk_tier in {"HIGH", "CRITICAL"}:
                reasons.append("Combined behavioural and engagement signals indicate elevated conversion risk")
            else:
                reasons.append("Normal product usage and engagement levels observed")

        return reasons
