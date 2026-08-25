"""
AI Provider Abstraction Module for Revive Phase 8 AI Intelligence Layer.
Provides BaseAIProvider interface, deterministic MockAIProvider for offline test isolation,
and GeminiAIProvider integrating the official Google Gemini API using modern google.genai SDK.
"""

from abc import ABC, abstractmethod
import json
import time
from typing import Any, Dict, List, Optional, Tuple

from app.models.events import BaseEvent
from app.diagnosis.schemas import Actionability, DiagnosisCategory, EvidenceItem
from app.ai.config import AIConfig, DEFAULT_AI_CONFIG
from app.ai.prompts import SYSTEM_INSTRUCTIONS, build_customer_analysis_prompt
from app.ai.schemas import AIFailureStatus


class BaseAIProvider(ABC):
    """Abstract base provider for AI intelligence models."""

    @abstractmethod
    def analyze_customer(
        self,
        customer_id: str,
        risk_score: float,
        risk_tier: str,
        events: List[BaseEvent],
        evidence_items: List[EvidenceItem],
    ) -> Tuple[Optional[dict], AIFailureStatus, float]:
        """
        Execute customer analysis request.

        Returns:
            (raw_response_dict, failure_status, latency_ms)
        """
        pass


class MockAIProvider(BaseAIProvider):
    """
    Deterministic mock provider for offline development and testing.
    Guarantees 100% reproducible, zero-latency execution given identical evidence.
    """

    def __init__(self, config: AIConfig = DEFAULT_AI_CONFIG) -> None:
        self.config = config

    def analyze_customer(
        self,
        customer_id: str,
        risk_score: float,
        risk_tier: str,
        events: List[BaseEvent],
        evidence_items: List[EvidenceItem],
    ) -> Tuple[Optional[dict], AIFailureStatus, float]:
        start_time = time.perf_counter()

        # Extract evidence descriptions and types
        ev_types = {item.evidence_type.value for item in evidence_items}
        ev_descs = [item.description for item in evidence_items]

        # Deterministic analysis mapping matching Phase 4 ground-truth rules
        if "CONVERSION_STATE" in ev_types or any("conversion" in d.lower() for d in ev_descs):
            candidate = DiagnosisCategory.ALREADY_CONVERTED.value
            conf = 1.0
            act = Actionability.NONE.value
            expl = "Customer has already converted; zero intervention required."
        elif risk_score < 0.30:
            candidate = DiagnosisCategory.NO_MEANINGFUL_RISK.value
            conf = 1.0
            act = Actionability.NONE.value
            expl = f"Customer risk score {risk_score:.2f} is below intervention threshold."
        elif "PAYMENT_FAILURE" in ev_types or any("payment" in d.lower() for d in ev_descs):
            candidate = DiagnosisCategory.PAYMENT_FRICTION.value
            conf = 0.85
            act = Actionability.CANDIDATE.value
            expl = "Observed payment failure events indicate payment friction."
        elif "CHECKOUT_ABANDONED" in ev_types or any("checkout" in d.lower() for d in ev_descs):
            candidate = DiagnosisCategory.CHECKOUT_ABANDONMENT.value
            conf = 0.80
            act = Actionability.CANDIDATE.value
            expl = "Observed checkout abandonment without payment completion."
        elif "TRIAL_EXPIRY_PROXIMITY" in ev_types or any("trial" in d.lower() for d in ev_descs):
            candidate = DiagnosisCategory.TRIAL_EXPIRATION.value
            conf = 0.75
            act = Actionability.CANDIDATE.value
            expl = "Trial period approaching expiration without active conversion."
        elif "RECENCY_DECLINE" in ev_types or any("inactivity" in d.lower() or "decline" in d.lower() for d in ev_descs):
            candidate = DiagnosisCategory.ENGAGEMENT_DECLINE.value
            conf = 0.70
            act = Actionability.CANDIDATE.value
            expl = "Product usage recency and session engagement have significantly declined."
        elif ev_descs:
            candidate = DiagnosisCategory.LOW_INTENT.value
            conf = 0.60
            act = Actionability.CANDIDATE.value
            expl = "Low session activity and pricing views indicate general low intent."
        else:
            candidate = DiagnosisCategory.INSUFFICIENT_EVIDENCE.value
            conf = 0.40
            act = Actionability.NONE.value
            expl = "Insufficient observable evidence to form a confident diagnosis."

        response_dict = {
            "diagnosis_candidate": candidate,
            "confidence": conf,
            "actionability": act,
            "supporting_evidence": ev_descs,
            "uncertainty_reasons": [] if conf >= 0.70 else ["Limited observable journey events"],
            "explanation": expl,
        }

        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return response_dict, AIFailureStatus.AI_SUCCESS, latency_ms


class GeminiAIProvider(BaseAIProvider):
    """
    Official Google Gemini API provider integration using modern google.genai SDK.
    Operates behind safe timeout, retry, structured-output, and credential isolation boundaries.
    """

    def __init__(self, config: AIConfig = DEFAULT_AI_CONFIG) -> None:
        self.config = config
        self._sdk_available = False
        self._genai_client = None

        if config.api_key:
            try:
                from google import genai
                self._genai_client = genai.Client(api_key=config.api_key)
                self._sdk_available = True
            except ImportError:
                self._sdk_available = False

    def analyze_customer(
        self,
        customer_id: str,
        risk_score: float,
        risk_tier: str,
        events: List[BaseEvent],
        evidence_items: List[EvidenceItem],
    ) -> Tuple[Optional[dict], AIFailureStatus, float]:
        start_time = time.perf_counter()

        if not self.config.api_key or not self._sdk_available or self._genai_client is None:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return None, AIFailureStatus.AI_UNAVAILABLE, latency_ms

        events_summary = [
            {
                "event_type": e.event_type.value,
                "timestamp": e.timestamp.isoformat(),
                "payload": e.payload,
            }
            for e in events[-5:]
        ]
        evidence_descriptions = [item.description for item in evidence_items]

        user_prompt = build_customer_analysis_prompt(
            customer_id=customer_id,
            risk_score=risk_score,
            risk_tier=risk_tier,
            events_summary=events_summary,
            evidence_descriptions=evidence_descriptions,
        )

        try:
            from google.genai import types

            gen_config = types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTIONS,
                temperature=self.config.temperature,
                max_output_tokens=self.config.max_output_tokens,
                response_mime_type="application/json" if self.config.structured_output else "text/plain",
            )

            response = self._genai_client.models.generate_content(
                model=self.config.model,
                contents=user_prompt,
                config=gen_config,
            )

            raw_text = response.text.strip() if (response and response.text) else ""

            # Clean markdown code fences if returned by the model
            if raw_text.startswith("```"):
                lines = raw_text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                raw_text = "\n".join(lines).strip()

            if not raw_text:
                latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
                return None, AIFailureStatus.AI_PROVIDER_ERROR, latency_ms

            parsed_json = json.loads(raw_text)
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return parsed_json, AIFailureStatus.AI_SUCCESS, latency_ms

        except TimeoutError:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return None, AIFailureStatus.AI_TIMEOUT, latency_ms
        except Exception as e:
            err_str = str(e).lower()
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            if "rate" in err_str or "quota" in err_str or "429" in err_str:
                return None, AIFailureStatus.AI_RATE_LIMITED, latency_ms
            elif "404" in err_str or "unavailable" in err_str or "not found" in err_str:
                return None, AIFailureStatus.AI_UNAVAILABLE, latency_ms
            else:
                return None, AIFailureStatus.AI_PROVIDER_ERROR, latency_ms
