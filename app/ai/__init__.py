"""
Phase 8 AI Intelligence Package for Revive.
Export key configuration, schemas, client providers, validators, grounding, service, and evaluation modules.
"""

from app.ai.config import DEFAULT_AI_CONFIG, AIConfig
from app.ai.schemas import (
    AIAnalysis,
    AIAnalysisMetadata,
    AIAnalysisResult,
    AIFailureStatus,
)
from app.ai.client import BaseAIProvider, GeminiAIProvider, MockAIProvider
from app.ai.grounding import GroundingValidator
from app.ai.prompts import PROMPT_VERSION, SCHEMA_VERSION, build_customer_analysis_prompt
from app.ai.validator import AISchemaValidator
from app.ai.service import AIService
from app.ai.evaluation import AIEvaluator

__all__ = [
    "AIConfig",
    "DEFAULT_AI_CONFIG",
    "AIFailureStatus",
    "AIAnalysis",
    "AIAnalysisMetadata",
    "AIAnalysisResult",
    "BaseAIProvider",
    "MockAIProvider",
    "GeminiAIProvider",
    "GroundingValidator",
    "AISchemaValidator",
    "AIService",
    "AIEvaluator",
    "PROMPT_VERSION",
    "SCHEMA_VERSION",
    "build_customer_analysis_prompt",
]
