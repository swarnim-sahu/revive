"""
Dashboard Presentation Service & Route Handlers for REVIVE API.
Provides read-only presentation endpoints backed by BatchRecoveryEvaluator.
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException

from app.evaluation.batch import BatchEvaluationResult, BatchRecoveryEvaluator
from app.api.schemas import (
    AttributionSummary,
    CustomerEvidenceResponse,
    DashboardSummaryResponse,
    DatasetSummary,
    ExecutionSummary,
    ExpectedRecoverySummary,
    MeasuredRecoverySummary,
    DiagnosisSummary,
    OutcomesSummary,
    PolicySummary,
    RiskSummary,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# In-memory evaluation cache for benchmark stability and performance
_cached_result: Optional[BatchEvaluationResult] = None


def get_evaluation_result(
    customers_count: int = 100, seed: int = 42, snapshot_hours: float = 336.0
) -> BatchEvaluationResult:
    """Retrieve or compute the deterministic batch evaluation result."""
    global _cached_result
    if (
        _cached_result is None
        or _cached_result.metadata.get("customers_requested") != customers_count
        or _cached_result.metadata.get("seed") != seed
    ):
        evaluator = BatchRecoveryEvaluator(
            customers_count=customers_count,
            seed=seed,
            snapshot_hours=snapshot_hours,
        )
        _cached_result = evaluator.evaluate()
    return _cached_result


@router.get("/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary() -> DashboardSummaryResponse:
    """Return validated benchmark summary metrics in clean JSON structure."""
    res = get_evaluation_result(customers_count=100, seed=42, snapshot_hours=336.0)
    agg = res.aggregate_metrics
    risk_dist = res.risk_distribution
    diag_dist = res.diagnosis_distribution
    act_dist = res.action_distribution
    outcome_dist = res.outcome_distribution
    attr_dist = res.attribution_distribution

    return DashboardSummaryResponse(
        dataset=DatasetSummary(
            customers_evaluated=agg.get("total_customers", 0),
            events_processed=agg.get("total_events", 0),
            customers_with_payment_failures=agg.get("customers_with_payment_failures", 0),
        ),
        risk=RiskSummary(
            critical=risk_dist.get("CRITICAL", 0),
            high=risk_dist.get("HIGH", 0),
            medium=risk_dist.get("MEDIUM", 0),
            low=risk_dist.get("LOW", 0),
            average_risk_score=agg.get("average_risk_score", 0.0),
            average_revenue_at_risk=agg.get("average_revenue_at_risk", 0.0),
        ),
        diagnosis=DiagnosisSummary(
            payment_friction=diag_dist.get("PAYMENT_FRICTION", 0),
            actionable=agg.get("actionable_diagnosis_count", 0),
            non_actionable=agg.get("non_actionable_diagnosis_count", 0),
        ),
        policy=PolicySummary(
            eligible_customers=agg.get("eligible_customers", 0),
            ineligible_customers=agg.get("ineligible_customers", 0),
            payment_recovery_actions=act_dist.get("PAYMENT_RECOVERY", 0),
            reminder_actions=act_dist.get("REMINDER", 0),
        ),
        expected_recovery=ExpectedRecoverySummary(
            total_revenue_at_risk=agg.get("total_revenue_at_risk", 0.0),
            total_expected_recovery=agg.get("total_expected_recovery_value", 0.0),
            expected_recovery_rate_pct=agg.get("expected_recovery_rate_pct", 0.0),
        ),
        measured_recovery=MeasuredRecoverySummary(
            gross_observed_revenue=agg.get("total_gross_observed_revenue", 0.0),
            attributable_revenue=agg.get("total_attributable_revenue", 0.0),
            intervention_cost=agg.get("total_intervention_cost", 0.0),
            net_recovered_revenue=agg.get("total_net_recovered_revenue", 0.0),
            measured_recovery_rate_pct=agg.get("measured_recovery_rate_pct", 0.0),
            recovered_customers=agg.get("recovered_customer_count", 0),
        ),
        outcomes=OutcomesSummary(distribution=outcome_dist),
        attribution=AttributionSummary(distribution=attr_dist),
        execution=ExecutionSummary(
            candidates=agg.get("execution_candidates", 0),
            successful=agg.get("simulated_successful_executions", 0),
            failed=agg.get("simulated_failed_executions", 0),
            blocked=agg.get("blocked_executions", 0),
            duplicates_prevented=agg.get("duplicates_prevented", 0),
        ),
    )


@router.get("/customers", response_model=List[CustomerEvidenceResponse])
def get_dashboard_customers() -> List[CustomerEvidenceResponse]:
    """Return all safe, auditable per-customer evidence records."""
    res = get_evaluation_result(customers_count=100, seed=42, snapshot_hours=336.0)
    return [CustomerEvidenceResponse(**rec.to_dict()) for rec in res.per_customer_results]


@router.get("/customers/{customer_id}", response_model=CustomerEvidenceResponse)
def get_dashboard_customer(customer_id: str) -> CustomerEvidenceResponse:
    """Return matching safe customer evidence record by customer_id or HTTP 404."""
    res = get_evaluation_result(customers_count=100, seed=42, snapshot_hours=336.0)
    for rec in res.per_customer_results:
        if rec.customer_id == customer_id:
            return CustomerEvidenceResponse(**rec.to_dict())
    raise HTTPException(status_code=404, detail=f"Customer evidence record '{customer_id}' not found")
