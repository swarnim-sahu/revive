"""
Unified Exception Ledger for REVIVE Phase B.
Tracks, classifies, and reconciles every non-standard case, policy block, escalation, and failure.
Ensures zero exceptions disappear from audit trails and guarantees exact mathematical reconciliation.
"""

from collections import Counter
from decimal import Decimal
from typing import Any, Dict, List, Optional
from app.evaluation.schemas import ExceptionRecord


class ExceptionLedger:
    """
    Append-only audit ledger tracking operational exceptions and governance decisions.
    """

    def __init__(self) -> None:
        self._records: List[ExceptionRecord] = []

    def record_exception(
        self,
        case_id: str,
        stage: str,
        status: str,
        failure_type: str,
        retryable: bool,
        safe_action_taken: str,
        financial_impact: float,
        human_escalation_required: bool,
        reason: str,
    ) -> ExceptionRecord:
        """Create and append an auditable ExceptionRecord."""
        record = ExceptionRecord(
            case_id=case_id,
            stage=stage,
            status=status,
            failure_type=failure_type,
            retryable=retryable,
            safe_action_taken=safe_action_taken,
            financial_impact=round(financial_impact, 2),
            human_escalation_required=human_escalation_required,
            reason=reason,
        )
        self._records.append(record)
        return record

    def get_records(self) -> List[ExceptionRecord]:
        """Return all recorded exception records."""
        return list(self._records)

    def get_summary(self) -> Dict[str, Any]:
        """Generate structured breakdown of exception categories, stages, and financial impact."""
        total_exceptions = len(self._records)
        if total_exceptions == 0:
            return {
                "total_exceptions": 0,
                "retryable_count": 0,
                "terminal_count": 0,
                "human_escalation_count": 0,
                "total_financial_impact": 0.0,
                "by_stage": {},
                "by_failure_type": {},
            }

        retryable_count = sum(1 for r in self._records if r.retryable)
        terminal_count = total_exceptions - retryable_count
        human_esc_count = sum(1 for r in self._records if r.human_escalation_required)
        total_financial_impact = sum(r.financial_impact for r in self._records)

        stage_counts = Counter(r.stage for r in self._records)
        type_counts = Counter(r.failure_type for r in self._records)

        return {
            "total_exceptions": total_exceptions,
            "retryable_count": retryable_count,
            "terminal_count": terminal_count,
            "human_escalation_count": human_esc_count,
            "total_financial_impact": round(total_financial_impact, 2),
            "by_stage": dict(stage_counts),
            "by_failure_type": dict(type_counts),
        }

    @staticmethod
    def verify_reconciliation(
        total_cases: int,
        successful_cases: int,
        stopped_cases: int,
        escalated_cases: int,
        failed_cases: int,
        unresolved_cases: int,
    ) -> bool:
        """
        Verify that all cases reconcile exactly without double counting or omission:
        total == successful + stopped + escalated + failed + unresolved
        """
        reconciled_sum = successful_cases + stopped_cases + escalated_cases + failed_cases + unresolved_cases
        return total_cases == reconciled_sum
