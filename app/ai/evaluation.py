"""
Evaluation Framework Module for Revive Phase 8 AI Intelligence Layer.
Evaluates AI analysis metrics: schema validity, grounding accuracy, fallback rates,
diagnosis agreement vs deterministic baseline, and ground-truth isolation.
"""

from collections import Counter
from typing import Any, Dict, List, Optional
from app.risk.feature_registry import FORBIDDEN_GROUND_TRUTH_FIELDS
from app.ai.schemas import AIAnalysisResult, AIFailureStatus


class AIEvaluator:
    """Evaluates AI Intelligence performance, safety compliance, and agreement vs deterministic baseline."""

    @classmethod
    def evaluate_ai_results(
        cls,
        results: List[AIAnalysisResult],
        feature_records: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Compute aggregate metrics across batch AI analysis results.
        """
        total = len(results)
        if total == 0:
            return {
                "total_evaluations": 0,
                "schema_validity_rate": 1.0,
                "grounding_accuracy_rate": 1.0,
                "unsupported_claim_rate": 0.0,
                "grounding_rejection_rate": 0.0,
                "fallback_rate": 0.0,
                "ai_proposal_agreements": 0,
                "ai_proposal_comparisons": 0,
                "ai_proposal_agreement_rate": 1.0,
                "final_agreements": 0,
                "final_diagnosis_agreement_rate": 1.0,
                "fallbacks_count": 0,
                "ground_truth_leakage_rate": 0.0,
                "average_latency_ms": 0.0,
                "status_counts": {},
                "raw_ai_proposal_distribution": {},
                "p4_baseline_diagnosis_distribution": {},
                "final_system_diagnosis_distribution": {},
            }

        status_counts = Counter(r.metadata.status.value for r in results)
        fallbacks = sum(1 for r in results if r.metadata.fallback_used)
        fallback_rate = round(fallbacks / total, 4)

        schema_invalid_count = status_counts.get(AIFailureStatus.AI_SCHEMA_INVALID.value, 0)
        schema_validity_rate = round((total - schema_invalid_count) / total, 4)

        grounding_failed_count = status_counts.get(AIFailureStatus.AI_GROUNDING_FAILED.value, 0)
        grounding_accuracy_rate = round((total - grounding_failed_count) / total, 4)
        grounding_rejection_rate = round(grounding_failed_count / total, 4)
        unsupported_claim_rate = rounding_rejection_rate = round(grounding_failed_count / total, 4)

        raw_ai_dist = Counter(r.analysis.diagnosis_candidate.value for r in results if r.analysis is not None)
        p4_base_dist = Counter(r.fallback_diagnosis.diagnosis.value for r in results if r.fallback_diagnosis is not None)
        final_sys_dist = Counter(r.final_diagnosis.diagnosis.value for r in results)

        # 1. Raw AI Proposal Agreement Rate vs Baseline Phase 4
        ai_proposal_agreements = 0
        ai_proposal_count = 0
        for r in results:
            if r.analysis is not None and r.fallback_diagnosis is not None:
                ai_proposal_count += 1
                if r.analysis.diagnosis_candidate == r.fallback_diagnosis.diagnosis:
                    ai_proposal_agreements += 1

        ai_proposal_agreement_rate = (
            round(ai_proposal_agreements / ai_proposal_count, 4) if ai_proposal_count > 0 else 1.0
        )

        # 2. Final System Diagnosis Agreement Rate vs Baseline Phase 4
        final_agreements = 0
        for r in results:
            if r.fallback_diagnosis is not None:
                if r.final_diagnosis.diagnosis == r.fallback_diagnosis.diagnosis:
                    final_agreements += 1
            else:
                final_agreements += 1
        final_agreement_rate = round(final_agreements / total, 4)

        avg_latency = round(sum(r.metadata.latency_ms for r in results) / total, 2)

        # Leakage Verification
        leakage_violations = 0
        if feature_records:
            for f_rec in feature_records:
                for forbidden in FORBIDDEN_GROUND_TRUTH_FIELDS:
                    if forbidden in f_rec:
                        leakage_violations += 1
                        break
            leakage_rate = round(leakage_violations / len(feature_records), 4)
        else:
            leakage_rate = 0.0

        return {
            "total_evaluations": total,
            "schema_validity_rate": schema_validity_rate,
            "grounding_accuracy_rate": grounding_accuracy_rate,
            "unsupported_claim_rate": unsupported_claim_rate,
            "grounding_rejection_rate": grounding_rejection_rate,
            "fallback_rate": fallback_rate,
            "ai_proposal_agreements": ai_proposal_agreements,
            "ai_proposal_comparisons": ai_proposal_count,
            "ai_proposal_agreement_rate": ai_proposal_agreement_rate,
            "final_agreements": final_agreements,
            "final_diagnosis_agreement_rate": final_agreement_rate,
            "fallbacks_count": fallbacks,
            "ground_truth_leakage_rate": leakage_rate,
            "average_latency_ms": avg_latency,
            "status_counts": dict(status_counts),
            "raw_ai_proposal_distribution": dict(raw_ai_dist),
            "p4_baseline_diagnosis_distribution": dict(p4_base_dist),
            "final_system_diagnosis_distribution": dict(final_sys_dist),
        }
