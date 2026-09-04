"""
Gemini Provider & Structured Output Validator Module for REVIVE Phase D.
Provides isolated Gemini provider integration, prompt versioning, structured output validation,
unsupported execution claim detection, and auditable error taxonomy.
"""

import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from app.diagnosis.schemas import Actionability, DiagnosisCategory
from app.evaluation.phase_d_schemas import (
    CANONICAL_OBSERVABLE_PRECEDENCE,
    GeminiCallResult,
    GeminiModelCallStatus,
    GeminiStructuredDiagnosis,
    PhaseDEvidenceRecord,
)

# Canonical Version Identifiers
PROMPT_VERSION = "REVIVE_GEMINI_DIAGNOSIS_PROMPT_V3"
EVIDENCE_VERSION = "3.0.0"

# Banned action/execution phrases that signal unconstrained model authority
_BANNED_EXECUTION_PATTERNS = [
    r"\bdispatched\s+payment\s+link\b",
    r"\bsent\s+payment\s+link\b",
    r"\bexecuted\s+payment\s+recovery\b",
    r"\bexecuted\s+intervention\b",
    r"\bcharged\s+(?:the\s+)?card\b",
    r"\bprocessed\s+refund\b",
    r"\bapplied\s+(?:\d+%\s+)?discount\b",
    r"\boverrode\s+policy\b",
    r"\bbypassed\s+guard\b",
    r"\bauthorized\s+(?:retry|execution|payment)\b",
    r"\bcreated\s+razorpay\s+link\b",
]
_COMPILED_EXECUTION_REGEX = re.compile("|".join(_BANNED_EXECUTION_PATTERNS), re.IGNORECASE)

# Unsupported action phrases that claim actions outside REVIVE's supported capability
_UNSUPPORTED_ACTION_PATTERNS = [
    r"\bunsupported\s+action\b",
    r"\bunsupported\s+intervention\b",
    r"\bdisallow(?:ed)?\s+action\b",
    r"\bunauthorized\s+action\b",
    r"\bclaim(?:ed)?\s+action\b",
]
_COMPILED_UNSUPPORTED_ACTION_REGEX = re.compile("|".join(_UNSUPPORTED_ACTION_PATTERNS), re.IGNORECASE)


def _format_precedence_instructions() -> str:
    """Format canonical observable precedence hierarchy dynamically for the Gemini prompt."""
    lines = []
    for item in CANONICAL_OBSERVABLE_PRECEDENCE:
        p = item["precedence"]
        cat = item["category"]
        act = item["actionability"]
        title = item["title"]
        desc = item["description"]
        criteria = item.get("criteria", "")
        lines.append(f"   [PRECEDENCE {p} - {title}]:")
        lines.append(f"   - \"{cat}\": {desc} (Actionability: {act})")
        if criteria:
            lines.append(f"     Criteria: {criteria}")
        lines.append("")
    return "\n".join(lines).rstrip()


def build_gemini_diagnosis_prompt(
    evidence: PhaseDEvidenceRecord,
    routing_reason: Optional[str] = None,
) -> str:
    """
    Build context-minimized, versioned diagnosis prompt for Gemini (v3.0.0).
    CRITICAL: Contains ONLY observable customer evidence and aggregate metrics.
    Ground truth (true_root_cause, natural_conversion, recoverable, generation_segment) is NEVER included.
    """
    recent_events_str = ""
    for idx, evt in enumerate(evidence.recent_observable_events[-5:], 1):
        recent_events_str += (
            f"  {idx}. type={evt.get('event_type')} | "
            f"timestamp={evt.get('timestamp')} | payload={evt.get('payload')}\n"
        )
    if not recent_events_str:
        recent_events_str = "  (No observable journey events recorded)\n"

    evidence_items_str = ""
    for idx, desc in enumerate(evidence.observable_evidence_descriptions, 1):
        evidence_items_str += f"  {idx}. {desc}\n"
    if not evidence_items_str:
        evidence_items_str = "  (No explicit evidence items extracted)\n"

    precedence_instructions = _format_precedence_instructions()
    routing_reason_text = routing_reason or "Customer journey exhibits multi-signal ambiguity requiring AI root-cause interpretation."

    prompt = f"""You are the AI Diagnosis Intelligence component for REVIVE, an enterprise subscription recovery engine.
Your sole responsibility is to evaluate observable customer journey evidence and produce a structured root-cause diagnosis candidate.

============================================================
AI REVIEW ROUTING CONTEXT (SELECTIVE INVOCATION):
============================================================
Review Mode: AI_REVIEW
Routing Reason: {routing_reason_text}
Note: You are being selectively invoked because deterministic rules identified multi-signal ambiguity in this customer journey.

============================================================
CRITICAL BOUNDARIES & INSTRUCTIONS (READ CAREFULLY):
============================================================
1. DIAGNOSIS ONLY — NO EXECUTION AUTHORITY:
   - You provide diagnosis intelligence only.
   - You have ZERO execution authority.
   - You must NEVER claim to have executed an intervention, sent a payment link, charged a card, granted a discount, or refunded money.
   - REVIVE's deterministic policy engines and execution guards retain sole execution authority.

2. STRICT EVIDENCE GROUNDING:
   - Base your diagnosis STRICTLY on the supplied observable journey events and features.
   - Do NOT invent, assume, or hallucinate events not present in the input.

3. AUTHORITATIVE OBSERVABLE DIAGNOSIS TAXONOMY & PRECEDENCE:
   You MUST choose exactly one 'diagnosis' value from this allowed list, respecting observable precedence:

{precedence_instructions}

4. ACTIONABILITY:
   Must be one of: "NONE", "CANDIDATE", "REQUIRES_REVIEW".

5. CONFIDENCE & UNCERTAINTY:
   Must be a float between 0.00 and 1.00. Express genuine diagnostic uncertainty (lower confidence 0.40-0.70 when signals conflict). List specific uncertainty_reasons if key signals are missing or conflicting.

6. OUTPUT FORMAT:
   Return ONLY a valid JSON object with these exact keys:
   {{
     "diagnosis": "<one of the 9 allowed categories>",
     "confidence": <float between 0.0 and 1.0>,
     "actionability": "<NONE | CANDIDATE | REQUIRES_REVIEW>",
     "rationale": "<concise explanation grounded in observable evidence>",
     "evidence_used": ["<list of specific observable items/events supporting this diagnosis>"],
     "uncertainty_reasons": ["<optional list of reasons for uncertainty or missing data>"]
   }}

============================================================
OBSERVABLE CUSTOMER EVIDENCE:
============================================================
Customer ID: {evidence.customer_id}
Plan: {evidence.plan_name} (Price: INR {evidence.plan_price_inr:.2f}, Billing: {evidence.billing_cycle})
Risk Score: {evidence.risk_score:.4f} (Tier: {evidence.risk_tier})
Revenue at Risk: INR {evidence.revenue_at_risk:.2f}
Trial Status: Active={evidence.trial_active}, Hours Until Expiry={evidence.hours_until_trial_expiry:.1f}
Observed Payment Failure: {evidence.payment_failed_observed}
Observed Checkout Abandonment: {evidence.checkout_abandonment_observed}
Days Since Last Active: {evidence.days_since_last_active:.2f}
Prior Conversion Detected: {evidence.has_prior_conversion}

LIFETIME OBSERVABLE ENGAGEMENT & ACTIVITY AGGREGATES:
- Lifetime Total Events: {evidence.lifetime_event_count}
- Lifetime Product Sessions: {evidence.lifetime_session_count}
- Lifetime Feature Uses: {evidence.lifetime_feature_use_count}
- Lifetime Pricing Views: {evidence.lifetime_pricing_view_count}
- Lifetime Checkout Starts: {evidence.lifetime_checkout_start_count}
- Lifetime Payment Attempts: {evidence.lifetime_payment_attempt_count}
- Lifetime Payment Successes: {evidence.lifetime_payment_success_count}
- Lifetime Payment Failures: {evidence.lifetime_payment_failure_count}

EXTRACTED OBSERVABLE EVIDENCE DESCRIPTIONS:
{evidence_items_str}
RECENT OBSERVABLE JOURNEY EVENTS:
{recent_events_str}
"""
    return prompt


class GeminiOutputValidator:
    """Strict schema, vocabulary, confidence, and governance validator for Gemini responses."""

    @classmethod
    def validate(
        cls,
        raw_text: str,
        evidence: PhaseDEvidenceRecord,
    ) -> Tuple[bool, Optional[GeminiStructuredDiagnosis], Optional[str], bool, bool, bool]:
        """
        Validate model response string.

        Returns:
            (is_valid, structured_diag, validation_error, unsupported_action_claim, execution_bypass_attempt, policy_guard_violation)
        """
        if not raw_text or not raw_text.strip():
            return (False, None, "Empty response received from model", False, False, False)

        clean_text = raw_text.strip()
        # Clean markdown code fences if present
        if clean_text.startswith("```"):
            lines = clean_text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            clean_text = "\n".join(lines).strip()

        try:
            parsed = json.loads(clean_text)
        except json.JSONDecodeError as err:
            return (False, None, f"Malformed JSON: {err}", False, False, False)

        if not isinstance(parsed, dict):
            return (False, None, "Response JSON root must be a dictionary", False, False, False)

        # Check for required fields
        required_fields = ["diagnosis", "confidence", "actionability", "rationale", "evidence_used"]
        missing = [f for f in required_fields if f not in parsed]
        if missing:
            return (False, None, f"Missing required fields: {missing}", False, False, False)

        # Validate diagnosis category
        diag_str = str(parsed["diagnosis"]).strip()
        allowed_diags = {d.value for d in DiagnosisCategory}
        if diag_str not in allowed_diags:
            return (
                False,
                None,
                f"Invalid diagnosis category '{diag_str}'. Must be one of {sorted(allowed_diags)}",
                False,
                False,
                False,
            )

        # Validate confidence
        try:
            conf = float(parsed["confidence"])
            if not (0.0 <= conf <= 1.0):
                return (
                    False,
                    None,
                    f"Confidence {conf} out of range [0.0, 1.0]",
                    False,
                    False,
                    False,
                )
        except (ValueError, TypeError):
            return (
                False,
                None,
                f"Invalid confidence value: {parsed.get('confidence')}",
                False,
                False,
                False,
            )

        # Validate actionability
        act_str = str(parsed["actionability"]).strip()
        allowed_actions = {a.value for a in Actionability}
        if act_str not in allowed_actions:
            return (
                False,
                None,
                f"Invalid actionability '{act_str}'. Must be one of {sorted(allowed_actions)}",
                False,
                False,
                False,
            )

        # Validate rationale & evidence_used
        rationale = str(parsed.get("rationale", "")).strip()
        if not rationale:
            return (False, None, "Rationale must not be empty", False, False, False)

        evidence_used = parsed.get("evidence_used")
        if not isinstance(evidence_used, list):
            return (False, None, "evidence_used must be a list", False, False, False)

        # -------------------------------------------------------------
        # Governance & Containment Checks
        # -------------------------------------------------------------
        combined_text = f"{rationale} {' '.join(str(e) for e in evidence_used)}"

        # Check for direct execution claims
        if _COMPILED_EXECUTION_REGEX.search(combined_text):
            return (
                False,
                None,
                "Governance violation: Model response claimed direct execution or payment mutation authority.",
                True,
                True,
                True,
            )

        # Check for unsupported action claims
        if _COMPILED_UNSUPPORTED_ACTION_REGEX.search(combined_text):
            return (
                False,
                None,
                "Governance violation: Model response claimed an unsupported action or unauthorized intervention.",
                True,
                False,
                False,
            )

        try:
            structured = GeminiStructuredDiagnosis(
                diagnosis=DiagnosisCategory(diag_str),
                confidence=round(conf, 4),
                actionability=Actionability(act_str),
                rationale=rationale.strip(),
                evidence_used=[str(x).strip() for x in evidence_used],
                uncertainty_reasons=[str(x).strip() for x in parsed.get("uncertainty_reasons", [])],
            )
            return (True, structured, None, False, False, False)
        except Exception as e:
            return (False, None, f"Schema validation error: {e}", False, False, False)


class GeminiDiagnosisEvaluator:
    """
    Isolated Gemini provider client for Phase D v2.0.0.
    Supports official Google Gemini API via modern google.genai SDK.
    Captures latency, token counts, error taxonomy, and enforces validation.
    Includes bounded retry with exponential backoff on HTTP 429 and transient errors.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        pacing_delay_seconds: Optional[float] = None,
        max_retries: Optional[int] = None,
        initial_backoff_seconds: Optional[float] = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("GEMINI_API_KEY")
        self.model = model if model is not None else os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else float(os.environ.get("GEMINI_TIMEOUT_SECONDS", "10.0"))
        )
        self.pacing_delay_seconds = (
            pacing_delay_seconds
            if pacing_delay_seconds is not None
            else float(os.environ.get("GEMINI_PACING_DELAY_SECONDS", "0.0"))
        )
        self.max_retries = (
            max_retries
            if max_retries is not None
            else int(os.environ.get("GEMINI_MAX_RETRIES", "2"))
        )
        self.initial_backoff_seconds = (
            initial_backoff_seconds
            if initial_backoff_seconds is not None
            else float(os.environ.get("GEMINI_INITIAL_BACKOFF_SECONDS", "2.0"))
        )
        self.prompt_version = PROMPT_VERSION
        self.evidence_version = EVIDENCE_VERSION
        self._sdk_available = False
        self._genai_client = None

        if self.api_key:
            try:
                from google import genai
                from google.genai import types

                timeout_ms = int(self.timeout_seconds * 1000) if self.timeout_seconds else None
                http_options = types.HttpOptions(timeout=timeout_ms) if timeout_ms else None
                self._genai_client = genai.Client(api_key=self.api_key, http_options=http_options)
                self._sdk_available = True
            except ImportError:
                self._sdk_available = False

    def is_available(self) -> bool:
        """Check whether real Gemini provider credentials and SDK are available."""
        return bool(self.api_key and self._sdk_available and self._genai_client is not None)

    def evaluate(
        self,
        evidence: PhaseDEvidenceRecord,
        routing_reason: Optional[str] = None,
    ) -> GeminiCallResult:
        """
        Execute controlled evaluation for a single customer evidence record with bounded retry.
        Returns explicit GeminiCallResult distinguishing REAL_GEMINI,
        MODEL_UNAVAILABLE, MODEL_ERROR, or SCHEMA_REJECTED.
        """
        start_time = time.perf_counter()

        if not self.api_key:
            return GeminiCallResult(
                status=GeminiModelCallStatus.MODEL_UNAVAILABLE,
                latency_ms=0.0,
                error_type="CREDENTIALS_UNAVAILABLE",
                error_message="GEMINI_API_KEY environment variable is not configured.",
            )

        if not self._sdk_available or self._genai_client is None:
            return GeminiCallResult(
                status=GeminiModelCallStatus.MODEL_UNAVAILABLE,
                latency_ms=0.0,
                error_type="SDK_UNAVAILABLE",
                error_message="google.genai SDK is not available or client initialization failed.",
            )

        # Optional inter-request pacing delay to respect RPM quotas
        if self.pacing_delay_seconds > 0.0:
            time.sleep(self.pacing_delay_seconds)

        prompt_text = build_gemini_diagnosis_prompt(evidence, routing_reason=routing_reason)

        retries_attempted = 0
        last_error_type = "API_ERROR"
        last_error_message = "Unknown error"

        for attempt in range(self.max_retries + 1):
            try:
                from google.genai import types

                timeout_ms = int(self.timeout_seconds * 1000) if self.timeout_seconds else None
                http_options = types.HttpOptions(timeout=timeout_ms) if timeout_ms else None

                gen_config = types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=1024,
                    response_mime_type="application/json",
                    http_options=http_options,
                )

                response = self._genai_client.models.generate_content(
                    model=self.model,
                    contents=prompt_text,
                    config=gen_config,
                )

                latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
                raw_text = response.text.strip() if (response and response.text) else ""

                # Extract token counts if provided by SDK
                prompt_tokens = None
                candidates_tokens = None
                total_tokens = None
                if hasattr(response, "usage_metadata") and response.usage_metadata is not None:
                    meta = response.usage_metadata
                    prompt_tokens = getattr(meta, "prompt_token_count", None)
                    candidates_tokens = getattr(meta, "candidates_token_count", None)
                    total_tokens = getattr(meta, "total_token_count", None)

                # Validate structured output
                is_valid, structured, val_err, unsupp, bypass, viol = GeminiOutputValidator.validate(
                    raw_text, evidence
                )

                if not is_valid or structured is None:
                    return GeminiCallResult(
                        status=GeminiModelCallStatus.SCHEMA_REJECTED,
                        raw_response_text=raw_text,
                        latency_ms=latency_ms,
                        prompt_tokens=prompt_tokens,
                        candidates_tokens=candidates_tokens,
                        total_tokens=total_tokens,
                        retries_attempted=retries_attempted,
                        error_type="SCHEMA_REJECTED",
                        error_message=val_err,
                    )

                return GeminiCallResult(
                    status=GeminiModelCallStatus.REAL_GEMINI,
                    raw_response_text=raw_text,
                    parsed_json=structured.model_dump(),
                    latency_ms=latency_ms,
                    prompt_tokens=prompt_tokens,
                    candidates_tokens=candidates_tokens,
                    total_tokens=total_tokens,
                    retries_attempted=retries_attempted,
                )

            except TimeoutError as e:
                last_error_type = "TIMEOUT"
                last_error_message = f"Request to Gemini API timed out after {self.timeout_seconds}s: {e}"
                if attempt < self.max_retries:
                    retries_attempted += 1
                    backoff = self.initial_backoff_seconds * (1.5 ** attempt)
                    time.sleep(backoff)
                    continue
                break

            except Exception as e:
                err_str = str(e).lower()
                err_cls = e.__class__.__name__.lower()
                if "timeout" in err_str or "timeout" in err_cls or "timed out" in err_str:
                    last_error_type = "TIMEOUT"
                    last_error_message = str(e)
                    if attempt < self.max_retries:
                        retries_attempted += 1
                        backoff = self.initial_backoff_seconds * (1.5 ** attempt)
                        time.sleep(backoff)
                        continue
                    break
                elif "rate" in err_str or "quota" in err_str or "429" in err_str:
                    last_error_type = "RATE_LIMITED"
                    last_error_message = str(e)
                    if attempt < self.max_retries:
                        retries_attempted += 1
                        backoff = self.initial_backoff_seconds * (1.5 ** attempt)
                        time.sleep(backoff)
                        continue
                    break
                elif "503" in err_str or "500" in err_str or "overloaded" in err_str or "unavailable" in err_str:
                    last_error_type = "SERVICE_UNAVAILABLE"
                    last_error_message = str(e)
                    if attempt < self.max_retries:
                        retries_attempted += 1
                        backoff = self.initial_backoff_seconds * (1.5 ** attempt)
                        time.sleep(backoff)
                        continue
                    break
                elif "401" in err_str or "403" in err_str or "auth" in err_str or "permission" in err_str:
                    last_error_type = "AUTH_ERROR"
                    last_error_message = str(e)
                    break
                elif "404" in err_str or "not found" in err_str:
                    last_error_type = "MODEL_NOT_FOUND"
                    last_error_message = str(e)
                    break
                else:
                    last_error_type = "API_ERROR"
                    last_error_message = str(e)
                    break

        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return GeminiCallResult(
            status=GeminiModelCallStatus.MODEL_ERROR,
            latency_ms=latency_ms,
            retries_attempted=retries_attempted,
            error_type=last_error_type,
            error_message=last_error_message,
        )
