"""
AI Service Orchestrator Module for Revive Phase 8.
Orchestrates AI intelligence analysis, schema validation, evidence grounding,
auditable failure classification, and safe fallback to deterministic Phase 4 diagnosis.
"""

from datetime import datetime, timezone
import time
from typing import Any, Dict, List, Optional
import uuid

from app.models.entities import Customer, Plan
from app.models.events import BaseEvent
from app.risk.scoring import ScoredCustomer
from app.diagnosis.engine import DiagnosisEngine, determine_confidence_tier
from app.diagnosis.schemas import CustomerDiagnosis
from app.ai.client import BaseAIProvider, GeminiAIProvider, MockAIProvider
from app.ai.config import AIConfig, DEFAULT_AI_CONFIG
from app.ai.grounding import GroundingValidator
from app.ai.prompts import PROMPT_VERSION, SCHEMA_VERSION
from app.ai.schemas import (
    AIAnalysis,
    AIAnalysisMetadata,
    AIAnalysisResult,
    AIFailureStatus,
)
from app.ai.validator import AISchemaValidator


class AIService:
    """Orchestrates AI intelligence analysis and enforces safety, grounding, and fallback boundaries."""

    def __init__(
        self,
        config: AIConfig = DEFAULT_AI_CONFIG,
        provider: Optional[BaseAIProvider] = None,
        diagnosis_engine: Optional[DiagnosisEngine] = None,
    ) -> None:
        self.config = config
        self.diagnosis_engine = diagnosis_engine or DiagnosisEngine()

        if provider is not None:
            self.provider = provider
        elif config.provider == "gemini":
            self.provider = GeminiAIProvider(config=config)
        else:
            self.provider = MockAIProvider(config=config)

    def analyze_and_diagnose(
        self,
        scored_customer: ScoredCustomer,
        customer: Customer,
        events: List[BaseEvent],
        plan: Plan,
        feature_record: Dict[str, Any],
    ) -> AIAnalysisResult:
        """
        Analyze customer journey using AI intelligence provider.
        Enforces schema validation, grounding validation, confidence thresholds, and safe Phase 4 fallback.
        """
        analysis_id = f"ai_anl_{scored_customer.customer_id}_{uuid.uuid4().hex[:8]}"
        context_ts = scored_customer.prediction_timestamp

        # 1. Obtain baseline deterministic Phase 4 diagnosis
        deterministic_diagnosis = self.diagnosis_engine.diagnose_customer(
            scored_customer, customer, events, plan, feature_record
        )

        # 2. Check if terminal state in deterministic diagnosis (e.g. ALREADY_CONVERTED, NO_MEANINGFUL_RISK)
        if deterministic_diagnosis.diagnosis in {
            self.diagnosis_engine.config.already_converted_category if hasattr(self.diagnosis_engine.config, "already_converted_category") else "ALREADY_CONVERTED",
            "NO_MEANINGFUL_RISK",
            "ALREADY_CONVERTED",
        }:
            metadata = AIAnalysisMetadata(
                analysis_id=analysis_id,
                customer_id=scored_customer.customer_id,
                context_timestamp=context_ts,
                provider=self.config.provider,
                model=self.config.model,
                prompt_version=PROMPT_VERSION,
                schema_version=SCHEMA_VERSION,
                status=AIFailureStatus.AI_SUCCESS,
                latency_ms=0.0,
                confidence=deterministic_diagnosis.confidence,
                fallback_used=False,
                validation_status="TERMINAL_DETERMINISTIC_PASS_THROUGH",
            )
            return AIAnalysisResult(
                analysis=None,
                metadata=metadata,
                fallback_diagnosis=None,
                final_diagnosis=deterministic_diagnosis,
            )

        # 3. Call AI provider
        raw_dict, failure_status, latency_ms = self.provider.analyze_customer(
            scored_customer.customer_id,
            scored_customer.risk_score,
            scored_customer.risk_tier,
            events,
            deterministic_diagnosis.supporting_evidence,
        )

        # 4. Handle provider failure -> Fallback to deterministic Phase 4
        if failure_status != AIFailureStatus.AI_SUCCESS or raw_dict is None:
            metadata = AIAnalysisMetadata(
                analysis_id=analysis_id,
                customer_id=scored_customer.customer_id,
                context_timestamp=context_ts,
                provider=self.config.provider,
                model=self.config.model,
                prompt_version=PROMPT_VERSION,
                schema_version=SCHEMA_VERSION,
                status=failure_status,
                latency_ms=latency_ms,
                confidence=0.0,
                fallback_used=True,
                validation_status=f"PROVIDER_FAILURE: {failure_status.value}",
            )
            return AIAnalysisResult(
                analysis=None,
                metadata=metadata,
                fallback_diagnosis=deterministic_diagnosis,
                final_diagnosis=deterministic_diagnosis,
            )

        # 5. Schema Validation
        is_valid_schema, ai_analysis, schema_err = AISchemaValidator.validate_schema(
            raw_dict, self.config.min_confidence_threshold
        )
        if not is_valid_schema or ai_analysis is None:
            metadata = AIAnalysisMetadata(
                analysis_id=analysis_id,
                customer_id=scored_customer.customer_id,
                context_timestamp=context_ts,
                provider=self.config.provider,
                model=self.config.model,
                prompt_version=PROMPT_VERSION,
                schema_version=SCHEMA_VERSION,
                status=AIFailureStatus.AI_SCHEMA_INVALID,
                latency_ms=latency_ms,
                confidence=0.0,
                fallback_used=True,
                validation_status=f"SCHEMA_INVALID: {schema_err}",
            )
            return AIAnalysisResult(
                analysis=None,
                metadata=metadata,
                fallback_diagnosis=deterministic_diagnosis,
                final_diagnosis=deterministic_diagnosis,
            )

        # 6. Evidence Grounding Validation
        is_grounded, validated_evidence, grounding_err = GroundingValidator.validate_grounding(
            ai_analysis, deterministic_diagnosis.supporting_evidence, events
        )
        if not is_grounded:
            metadata = AIAnalysisMetadata(
                analysis_id=analysis_id,
                customer_id=scored_customer.customer_id,
                context_timestamp=context_ts,
                provider=self.config.provider,
                model=self.config.model,
                prompt_version=PROMPT_VERSION,
                schema_version=SCHEMA_VERSION,
                status=AIFailureStatus.AI_GROUNDING_FAILED,
                latency_ms=latency_ms,
                confidence=ai_analysis.confidence,
                fallback_used=True,
                validation_status=f"GROUNDING_FAILED: {grounding_err}",
            )
            return AIAnalysisResult(
                analysis=ai_analysis,
                metadata=metadata,
                fallback_diagnosis=deterministic_diagnosis,
                final_diagnosis=deterministic_diagnosis,
            )

        # 7. Low Confidence Threshold Check
        if ai_analysis.confidence < self.config.min_confidence_threshold:
            metadata = AIAnalysisMetadata(
                analysis_id=analysis_id,
                customer_id=scored_customer.customer_id,
                context_timestamp=context_ts,
                provider=self.config.provider,
                model=self.config.model,
                prompt_version=PROMPT_VERSION,
                schema_version=SCHEMA_VERSION,
                status=AIFailureStatus.AI_LOW_CONFIDENCE,
                latency_ms=latency_ms,
                confidence=ai_analysis.confidence,
                fallback_used=True,
                validation_status=f"LOW_CONFIDENCE: {ai_analysis.confidence:.2f} < {self.config.min_confidence_threshold:.2f}",
            )
            return AIAnalysisResult(
                analysis=ai_analysis,
                metadata=metadata,
                fallback_diagnosis=deterministic_diagnosis,
                final_diagnosis=deterministic_diagnosis,
            )

        # 8. All AI Validations Passed -> Construct AI-Assisted CustomerDiagnosis
        ai_assisted_diagnosis = CustomerDiagnosis(
            customer_id=scored_customer.customer_id,
            prediction_timestamp=scored_customer.prediction_timestamp,
            risk_score=scored_customer.risk_score,
            risk_tier=scored_customer.risk_tier,
            diagnosis=ai_analysis.diagnosis_candidate,
            confidence=ai_analysis.confidence,
            confidence_tier=determine_confidence_tier(ai_analysis.confidence, self.diagnosis_engine.config),
            actionability=ai_analysis.actionability,
            candidate_causes=deterministic_diagnosis.candidate_causes,
            supporting_evidence=deterministic_diagnosis.supporting_evidence,
            explanation=f"[AI Assisted] {ai_analysis.explanation}",
        )

        metadata = AIAnalysisMetadata(
            analysis_id=analysis_id,
            customer_id=scored_customer.customer_id,
            context_timestamp=context_ts,
            provider=self.config.provider,
            model=self.config.model,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            status=AIFailureStatus.AI_SUCCESS,
            latency_ms=latency_ms,
            confidence=ai_analysis.confidence,
            fallback_used=False,
            validation_status="PASSED",
        )

        return AIAnalysisResult(
            analysis=ai_analysis,
            metadata=metadata,
            fallback_diagnosis=deterministic_diagnosis,
            final_diagnosis=ai_assisted_diagnosis,
        )
