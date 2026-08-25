"""
Prompt Templates and Versioning Module for Revive Phase 8 AI Intelligence Layer.
Defines versioned prompts enforcing role definition, evidence grounding, taxonomy boundaries, and structured JSON outputs.
"""

from typing import Any, Dict, List
from app.diagnosis.schemas import DiagnosisCategory

PROMPT_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0.0"

SYSTEM_INSTRUCTIONS = """You are the AI Intelligence Assistant for REVIVE, an enterprise subscription recovery engine.
Your task is to analyze observable customer journey events and recommend a root-cause diagnosis candidate.

CRITICAL CONSTRAINTS:
1. You MUST select the diagnosis candidate strictly from the allowed taxonomy:
   - NO_MEANINGFUL_RISK
   - LOW_INTENT
   - CHECKOUT_ABANDONMENT
   - PAYMENT_FRICTION
   - TRIAL_EXPIRATION
   - ENGAGEMENT_DECLINE
   - MIXED_SIGNALS
   - INSUFFICIENT_EVIDENCE
   - ALREADY_CONVERTED

2. STRICT EVIDENCE GROUNDING:
   - Every claim in 'supporting_evidence' MUST correspond directly to an observable event provided in the input.
   - Do NOT fabricate, infer, or assume facts not present in the input (e.g. do NOT claim a bank permanently blocked a card unless 'CARD_DECLINED' or 'BANK_BLOCK' is in the events).

3. UNCERTAINTY & ACTIONABILITY:
   - If evidence is ambiguous, incomplete, or weak, set confidence low (< 0.50) and list reasons in 'uncertainty_reasons'.
   - Actionability MUST be one of: 'NONE', 'CANDIDATE', 'REQUIRES_REVIEW'.

4. OUTPUT FORMAT:
   - You MUST respond strictly with valid JSON conforming to the requested schema.
"""


def build_customer_analysis_prompt(
    customer_id: str,
    risk_score: float,
    risk_tier: str,
    events_summary: List[Dict[str, Any]],
    evidence_descriptions: List[str],
) -> str:
    """Build a versioned, context-minimized user prompt for Gemini."""
    prompt = f"""CUSTOMER ANALYSIS REQUEST:
Customer ID: {customer_id}
Risk Score: {risk_score:.4f}
Risk Tier: {risk_tier}

OBSERVABLE EVIDENCE ITEMS:
"""
    for idx, ev_desc in enumerate(evidence_descriptions, 1):
        prompt += f"  {idx}. {ev_desc}\n"

    prompt += "\nRECENT JOURNEY EVENTS (Context Minimized):\n"
    for idx, evt in enumerate(events_summary, 1):
        prompt += f"  {idx}. Event={evt.get('event_type')} | Timestamp={evt.get('timestamp')} | Payload={evt.get('payload')}\n"

    prompt += """
Please analyze this observable evidence and provide a structured JSON response with keys:
- "diagnosis_candidate": (string from allowed taxonomy)
- "confidence": (float between 0.0 and 1.0)
- "actionability": (string: "NONE", "CANDIDATE", or "REQUIRES_REVIEW")
- "supporting_evidence": (array of strings, each string exactly describing an observed event or evidence item)
- "uncertainty_reasons": (array of strings explaining any ambiguity or missing data)
- "explanation": (string detailing the evidence-grounded rationale)
"""
    return prompt
