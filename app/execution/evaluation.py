"""
Offline Evaluation Engine for Revive Phase 6 Execution Layer.
Computes execution correctness metrics, safety policy compliance, idempotency rates, and audit completeness.
All metrics are derived dynamically from empirical audit records without hardcoded values.
"""

from collections import Counter
from typing import Any, Dict, List, Optional
from app.risk.feature_registry import FORBIDDEN_GROUND_TRUTH_FIELDS
from app.execution.config import DEFAULT_EXECUTION_CONFIG, ExecutionConfig
from app.execution.schemas import ExecutionAuditRecord, ExecutionStatus, FailureType


class ExecutionEvaluator:
    """Evaluates Phase 6 execution audit records for operational correctness and safety compliance."""

    @classmethod
    def evaluate_execution_records(
        cls,
        audit_records: List[ExecutionAuditRecord],
        feature_records: Optional[List[Dict[str, Any]]] = None,
        config: ExecutionConfig = DEFAULT_EXECUTION_CONFIG,
    ) -> Dict[str, Any]:
        """
        Compute operational execution metrics, retry rates, failure rates, audit completeness, and leakage.
        """
        total_records = len(audit_records)
        if total_records == 0:
            return {
                "total_decisions_processed": 0,
                "executed_count": 0,
                "executed_rate": 0.0,
                "blocked_count": 0,
                "blocked_rate": 0.0,
                "escalated_count": 0,
                "escalated_rate": 0.0,
                "no_action_count": 0,
                "no_action_rate": 0.0,
                "failed_count": 0,
                "failed_rate": 0.0,
                "execution_success_rate": 0.0,
                "retryable_failure_count": 0,
                "retryable_failure_rate": 0.0,
                "non_retryable_failure_count": 0,
                "non_retryable_failure_rate": 0.0,
                "fallback_count": 0,
                "fallback_rate": 0.0,
                "duplicate_execution_count": 0,
                "duplicate_execution_rate": 0.0,
                "retry_budget_compliance_rate": 1.0,
                "audit_completeness_rate": 1.0,
                "test_mode_isolation_rate": 1.0,
                "ground_truth_leakage_rate": 0.0,
            }

        status_counts = Counter(r.status.value for r in audit_records)
        failure_type_counts = Counter(r.failure_type.value for r in audit_records)

        executed_count = status_counts.get("EXECUTED", 0)
        blocked_count = status_counts.get("BLOCKED", 0)
        escalated_count = status_counts.get("ESCALATED", 0)
        no_action_count = status_counts.get("NO_ACTION", 0)
        failed_count = status_counts.get("FAILED", 0)

        retryable_count = failure_type_counts.get("RETRYABLE", 0)
        non_retryable_count = failure_type_counts.get("NON_RETRYABLE", 0)
        fallback_count = sum(1 for r in audit_records if r.fallback_action is not None)

        # Duplicate execution detection: repeated execution IDs in audit input
        seen_ids = set()
        duplicate_count = 0
        for r in audit_records:
            if r.execution_id in seen_ids:
                duplicate_count += 1
            else:
                seen_ids.add(r.execution_id)

        # Configurable retry budget compliance check (attempt_number <= max_allowed_attempts)
        max_allowed_attempts = config.max_retries + 1
        retry_violations = sum(1 for r in audit_records if r.attempt_number > max_allowed_attempts)
        retry_compliance_rate = round((total_records - retry_violations) / total_records, 4)

        # Audit completeness check (all required fields present)
        incomplete_audits = sum(
            1 for r in audit_records
            if not r.execution_id or not r.customer_id or not r.decision_id or not r.action or not r.execution_timestamp
        )
        audit_completeness_rate = round((total_records - incomplete_audits) / total_records, 4)

        # Test-mode isolation calculation: verify payload target_urls use sim://revive/ scheme
        test_mode_violations = 0
        for r in audit_records:
            if r.target_url and not r.target_url.startswith("sim://revive/"):
                test_mode_violations += 1
        test_mode_isolation_rate = round((total_records - test_mode_violations) / total_records, 4)

        # Ground-truth leakage check if feature records are supplied
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
            "total_decisions_processed": total_records,
            "executed_count": executed_count,
            "executed_rate": round(executed_count / total_records, 4),
            "blocked_count": blocked_count,
            "blocked_rate": round(blocked_count / total_records, 4),
            "escalated_count": escalated_count,
            "escalated_rate": round(escalated_count / total_records, 4),
            "no_action_count": no_action_count,
            "no_action_rate": round(no_action_count / total_records, 4),
            "failed_count": failed_count,
            "failed_rate": round(failed_count / total_records, 4),
            "execution_success_rate": round(executed_count / total_records, 4),
            "retryable_failure_count": retryable_count,
            "retryable_failure_rate": round(retryable_count / total_records, 4),
            "non_retryable_failure_count": non_retryable_count,
            "non_retryable_failure_rate": round(non_retryable_count / total_records, 4),
            "fallback_count": fallback_count,
            "fallback_rate": round(fallback_count / total_records, 4),
            "duplicate_execution_count": duplicate_count,
            "duplicate_execution_rate": round(duplicate_count / total_records, 4),
            "retry_budget_compliance_rate": retry_compliance_rate,
            "audit_completeness_rate": audit_completeness_rate,
            "test_mode_isolation_rate": test_mode_isolation_rate,
            "ground_truth_leakage_rate": leakage_rate,
        }
