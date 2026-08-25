"""
Structured Output Schema Validator Module for Revive Phase 8 AI Intelligence Layer.
Validates structured AI outputs against diagnosis taxonomy, confidence bounds, and actionability contracts.
"""

from typing import Optional, Tuple
from app.diagnosis.schemas import Actionability, DiagnosisCategory
from app.ai.schemas import AIAnalysis


class AISchemaValidator:
    """Validates structured AI output against Revive Phase 4 taxonomy and boundary constraints."""

    @classmethod
    def validate_schema(
        cls,
        analysis_data: dict,
        min_confidence_threshold: float = 0.50,
    ) -> Tuple[bool, Optional[AIAnalysis], Optional[str]]:
        """
        Validate raw dict response against AIAnalysis Pydantic schema and taxonomy.

        Returns:
            (is_valid, parsed_ai_analysis, error_message)
        """
        if not isinstance(analysis_data, dict):
            return False, None, "Invalid response type: expected JSON object / dict"

        # 1. Taxonomy check for diagnosis candidate
        raw_diag = analysis_data.get("diagnosis_candidate")
        try:
            diag_cat = DiagnosisCategory(raw_diag)
        except Exception:
            return False, None, f"Invalid diagnosis_candidate '{raw_diag}' not in DiagnosisCategory taxonomy"

        # 2. Actionability check
        raw_action = analysis_data.get("actionability")
        try:
            actionability = Actionability(raw_action)
        except Exception:
            return False, None, f"Invalid actionability '{raw_action}' not in Actionability enum"

        # 3. Confidence check
        confidence = analysis_data.get("confidence")
        if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
            return False, None, f"Invalid confidence '{confidence}': must be float between 0.0 and 1.0"

        # 4. Non-empty explanation check
        explanation = analysis_data.get("explanation")
        if not explanation or not isinstance(explanation, str) or not explanation.strip():
            return False, None, "Missing or empty explanation string"

        try:
            analysis_obj = AIAnalysis(
                diagnosis_candidate=diag_cat,
                confidence=round(float(confidence), 4),
                actionability=actionability,
                supporting_evidence=list(analysis_data.get("supporting_evidence", [])),
                uncertainty_reasons=list(analysis_data.get("uncertainty_reasons", [])),
                explanation=explanation.strip(),
            )
            return True, analysis_obj, None
        except Exception as e:
            return False, None, f"Pydantic validation error: {str(e)}"
