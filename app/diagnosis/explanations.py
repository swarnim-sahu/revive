"""
Deterministic Diagnosis Explanations for Revive (Phase 4).
Generates human-readable, auditable explanations strictly based on structured EvidenceItem objects.
NO LLMs are used for Phase 4 explanations.
"""

from typing import List
from app.diagnosis.schemas import ConfidenceTier, CustomerDiagnosis, DiagnosisCategory, EvidenceItem


class DiagnosisExplainer:
    """Generates concise, auditable text explanations from structured evidence."""

    @staticmethod
    def generate_explanation(
        diagnosis: DiagnosisCategory,
        confidence: float,
        confidence_tier: ConfidenceTier,
        evidence_items: List[EvidenceItem],
    ) -> str:
        """Generate human-readable summary from structured evidence items."""
        if diagnosis == DiagnosisCategory.ALREADY_CONVERTED:
            return "Customer converted naturally before the prediction snapshot."

        if diagnosis == DiagnosisCategory.NO_MEANINGFUL_RISK:
            return "Customer risk score is below the operational threshold; no recovery intervention required."

        if diagnosis == DiagnosisCategory.INSUFFICIENT_EVIDENCE:
            return "Insufficient observable evidence to determine a primary root cause."

        if diagnosis == DiagnosisCategory.MIXED_SIGNALS:
            bullets = [f"  - {ev.description}" for ev in evidence_items]
            ev_text = "\n".join(bullets) if bullets else "  - Multiple conflicting signals present."
            return f"Multiple competing root causes detected with comparable evidence strength:\n{ev_text}"

        header = f"Primary diagnosis: {diagnosis.value} (Confidence: {confidence_tier.value}, {confidence:.2f})\n\nObservable Supporting Evidence:"
        bullets = [f"  - {ev.description}" for ev in evidence_items if ev.strength > 0]

        if not bullets:
            bullets = ["  - Diagnostic inference based on observable usage and intent patterns."]

        return header + "\n" + "\n".join(bullets)
