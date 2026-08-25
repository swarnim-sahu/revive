"""
Evidence Grounding Validator Module for Revive Phase 8 AI Intelligence Layer.
Enforces relationship-aware evidence grounding: verifies that AI evidence claims correspond directly to observable customer events.
Rejects fabricated, speculative, inferred, ungrounded quantitative/temporal/causal, or unsupported claims.
"""

import re
from typing import Any, Dict, List, Optional, Tuple
from app.models.events import BaseEvent
from app.diagnosis.schemas import EvidenceCategory, EvidenceItem
from app.ai.schemas import AIAnalysis


GENERIC_STOP_WORDS = {
    "the", "a", "an", "customer", "customers", "user", "users", "was", "is", "are", "were", "been", "being",
    "to", "for", "in", "on", "of", "and", "or", "with", "observed", "detected", "definitely", "probably",
    "has", "have", "had", "that", "this", "these", "those", "from", "at", "by", "an", "be", "it", "its",
}

UNSUPPORTED_SPECULATIVE_PHRASES = {
    "permanently blocked",
    "permanently closed",
    "stolen card",
    "stolen",
    "bankrupt",
    "bankruptcy",
    "account hacked",
    "hacked",
    "identity theft",
    "police report",
    "legal dispute",
    "blacklisted",
}

UNSUPPORTED_CAUSAL_WORDS = {
    "caused",
    "because",
    "due to",
    "resulted in",
    "led to",
    "triggered",
}

UNSUPPORTED_EXTERNAL_ACTORS = {
    "bank",
    "card issuer",
    "issuer",
    "gateway",
    "fraud system",
    "support agent",
}

NUMBER_WORDS_MAP = {
    "once": 1,
    "twice": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "twenty": 20,
    "fifty": 50,
    "hundred": 100,
    "one hundred": 100,
    "thousand": 1000,
}

NEGATION_PATTERNS = [
    "no payment failure",
    "never experienced a payment failure",
    "no failure occurred",
    "no payment failed",
    "never failed",
    "zero failure",
]


class GroundingValidator:
    """Enforces evidence-grounding constraints on AI-generated proposals."""

    @classmethod
    def extract_observable_tokens(
        cls,
        evidence_items: List[EvidenceItem],
        events: List[BaseEvent],
    ) -> Dict[str, Any]:
        """Extract set of observable terms, event types, payload values, and timestamps from input context."""
        observable_terms = set()
        observable_event_types = set()
        full_text_corpus = []

        obs_failure_count = 0
        obs_retry_count = 0
        obs_success_count = 0

        event_timestamps: Dict[str, str] = {}

        for item in evidence_items:
            ev_str = item.evidence_type.value.lower()
            observable_event_types.add(ev_str)
            observable_terms.add(ev_str)
            for sub_term in ev_str.split("_"):
                if len(sub_term) > 1:
                    observable_terms.add(sub_term)
            full_text_corpus.append(ev_str)

            if item.evidence_type == EvidenceCategory.PAYMENT_FAILURE:
                obs_failure_count += 1

            desc_lower = item.description.lower()
            full_text_corpus.append(desc_lower)
            for word in desc_lower.replace("_", " ").split():
                clean_word = "".join(c for c in word if c.isalnum())
                if len(clean_word) > 1:
                    observable_terms.add(clean_word)

        for evt in events:
            evt_type_str = evt.event_type.value.lower()
            observable_event_types.add(evt_type_str)
            observable_terms.add(evt_type_str)
            for sub_term in evt_type_str.split("_"):
                if len(sub_term) > 1:
                    observable_terms.add(sub_term)
            full_text_corpus.append(evt_type_str)

            # Track earliest timestamp per event type
            if evt_type_str not in event_timestamps:
                event_timestamps[evt_type_str] = evt.timestamp.isoformat()

            if evt_type_str in {"payment_failed", "checkout_abandoned"}:
                obs_failure_count = max(
                    obs_failure_count,
                    sum(1 for e in events if e.event_type.value.lower() in {"payment_failed", "checkout_abandoned"})
                )
            elif evt_type_str == "payment_succeeded":
                obs_success_count += 1
            elif evt_type_str == "payment_retried":
                obs_retry_count += 1

            if isinstance(evt.payload, dict):
                if evt.payload.get("is_retry"):
                    obs_retry_count += 1
                for k, v in evt.payload.items():
                    k_str = str(k).lower()
                    val_str = str(v).lower()
                    observable_terms.add(k_str)
                    observable_terms.add(val_str)
                    full_text_corpus.append(k_str)
                    full_text_corpus.append(val_str)
                    for word in val_str.replace("_", " ").split():
                        clean_word = "".join(c for c in word if c.isalnum())
                        if len(clean_word) > 1:
                            observable_terms.add(clean_word)

        combined_text = " ".join(full_text_corpus)

        return {
            "terms": observable_terms,
            "event_types": observable_event_types,
            "combined_text": combined_text,
            "obs_failure_count": obs_failure_count,
            "obs_retry_count": obs_retry_count,
            "obs_success_count": obs_success_count,
            "event_timestamps": event_timestamps,
        }

    @classmethod
    def extract_claimed_quantity(cls, claim_lower: str) -> Optional[int]:
        """Extract claimed failure/attempt quantity from claim string (digits or number words)."""
        # Only evaluate quantity if claim explicitly asserts a failure or attempt count
        if any(term in claim_lower for term in ("fail", "attempt", "retry", "retried", "occurrence")):
            # Match digit patterns: e.g. "5 times", "100 times", "7 times", "3 failures"
            digit_matches = re.findall(r"(\d+)\s*(?:times|failures?|attempts?|occurrences?)", claim_lower)
            if digit_matches:
                nums = [int(m) for m in digit_matches if m.isdigit()]
                if nums:
                    return max(nums)

            # Match number word patterns: e.g. "once", "twice", "three times", "five times", "one hundred times"
            for word, val in NUMBER_WORDS_MAP.items():
                if word in claim_lower:
                    return val

        return None

    @classmethod
    def validate_grounding(
        cls,
        analysis: AIAnalysis,
        evidence_items: List[EvidenceItem],
        events: List[BaseEvent],
    ) -> Tuple[bool, List[str], Optional[str]]:
        """
        Verify that supporting evidence claims in AIAnalysis are grounded in observable events.

        Returns:
            (is_fully_grounded, validated_evidence_list, rejection_reason)
        """
        if not analysis.supporting_evidence:
            return True, [], None

        obs_data = cls.extract_observable_tokens(evidence_items, events)
        obs_terms = obs_data["terms"]
        combined_text = obs_data["combined_text"]
        obs_event_types = obs_data["event_types"]
        obs_failure_count = obs_data["obs_failure_count"]
        obs_retry_count = obs_data["obs_retry_count"]
        obs_success_count = obs_data["obs_success_count"]
        event_timestamps = obs_data["event_timestamps"]

        validated_claims: List[str] = []
        unsupported_claims: List[str] = []

        for claim in analysis.supporting_evidence:
            claim_lower = claim.lower().strip()

            # 1. Speculative/hallucinated phrase check
            speculative_violation = False
            for spec_phrase in UNSUPPORTED_SPECULATIVE_PHRASES:
                if spec_phrase in claim_lower:
                    if spec_phrase not in combined_text and not any(spec_phrase in term for term in obs_terms):
                        speculative_violation = True
                        break

            if speculative_violation:
                unsupported_claims.append(claim)
                continue

            # 2. Causal language grounding check
            causal_violation = False
            for causal_word in UNSUPPORTED_CAUSAL_WORDS:
                if causal_word in claim_lower:
                    if causal_word not in combined_text:
                        causal_violation = True
                        break

            if causal_violation:
                unsupported_claims.append(claim)
                continue

            # 3. External actor attribution grounding check
            actor_violation = False
            for actor in UNSUPPORTED_EXTERNAL_ACTORS:
                if actor in claim_lower:
                    if actor not in combined_text:
                        actor_violation = True
                        break

            if actor_violation:
                unsupported_claims.append(claim)
                continue

            # 4. Implied event / action grounding check
            if "retri" in claim_lower and "retri" not in combined_text and obs_retry_count == 0:
                unsupported_claims.append(claim)
                continue

            if ("paid" in claim_lower or "success" in claim_lower) and "success" not in combined_text and obs_success_count == 0:
                unsupported_claims.append(claim)
                continue

            action_violation = False
            for act in {"refunded", "subscribed", "upgraded", "contacted support"}:
                if act in claim_lower and act not in combined_text:
                    action_violation = True
                    break

            if action_violation:
                unsupported_claims.append(claim)
                continue

            # 5. Quantity and count assertion check (ISSUE-01 Fix)
            claimed_qty = cls.extract_claimed_quantity(claim_lower)
            if claimed_qty is not None:
                if claimed_qty > obs_failure_count:
                    unsupported_claims.append(claim)
                    continue

            # 6. Negation / contradiction check
            negation_violation = False
            for neg_pat in NEGATION_PATTERNS:
                if neg_pat in claim_lower and obs_failure_count > 0:
                    negation_violation = True
                    break

            if negation_violation:
                unsupported_claims.append(claim)
                continue

            # 7. Temporal relationship grounding check (ISSUE-02 Fix)
            temporal_phrases = ["before checkout", "after checkout", "during checkout", "followed by", "followed checkout", "prior to checkout"]
            if any(tp in claim_lower for tp in temporal_phrases):
                if "checkout" in claim_lower:
                    has_checkout_event = any("checkout" in evt_type for evt_type in obs_event_types)
                    if not has_checkout_event:
                        # REJECT: Checkout event was never observed!
                        unsupported_claims.append(claim)
                        continue

                    co_ts = event_timestamps.get("checkout_started") or event_timestamps.get("checkout_abandoned")
                    pay_ts = event_timestamps.get("payment_failed")

                    if "before checkout" in claim_lower or "prior to checkout" in claim_lower:
                        if not co_ts or not pay_ts or pay_ts >= co_ts:
                            unsupported_claims.append(claim)
                            continue
                    elif "after checkout" in claim_lower or "followed by" in claim_lower or "followed checkout" in claim_lower:
                        if not co_ts or not pay_ts or pay_ts <= co_ts:
                            unsupported_claims.append(claim)
                            continue
                    elif "during checkout" in claim_lower:
                        if "during checkout" not in combined_text:
                            unsupported_claims.append(claim)
                            continue

            # 8. Extract meaningful non-generic words from claim
            words_in_claim = [
                "".join(c for c in w if c.isalnum() or c == "_")
                for w in claim_lower.split()
            ]
            meaningful_words = [
                w for w in words_in_claim
                if len(w) > 1 and w not in GENERIC_STOP_WORDS
            ]

            if not meaningful_words:
                unsupported_claims.append(claim)
                continue

            matched = any(w in obs_terms for w in meaningful_words)
            if matched:
                validated_claims.append(claim)
            else:
                unsupported_claims.append(claim)

        if unsupported_claims:
            reason = f"Grounding validation failed: {len(unsupported_claims)} unsupported claim(s) detected ({unsupported_claims[0]})"
            return False, validated_claims, reason

        return True, validated_claims, None
