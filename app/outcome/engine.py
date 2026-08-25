"""
Core Orchestration Engine for Revive Phase 7 Outcome Measurement & Revenue Attribution.
Consumes Phase 6 ExecutionAuditRecords and observable customer events, applies temporal integrity boundaries,
resolves canonical outcomes, determines attribution status, and performs revenue accounting.
"""

from typing import Dict, List, Optional
from app.models.entities import Plan
from app.models.events import BaseEvent
from app.intervention.schemas import InterventionDecision
from app.execution.schemas import ExecutionAuditRecord
from app.outcome.config import DEFAULT_OUTCOME_CONFIG, OutcomeConfig
from app.outcome.observer import EventObserver
from app.outcome.resolver import OutcomeResolver
from app.outcome.attribution import AttributionEngine
from app.outcome.revenue import RevenueCalculator
from app.outcome.schemas import OutcomeRecord


class OutcomeEngine:
    """Core deterministic Phase 7 outcome measurement orchestrator."""

    def __init__(self, config: OutcomeConfig = DEFAULT_OUTCOME_CONFIG) -> None:
        self.config = config
        self._outcome_store: Dict[str, OutcomeRecord] = {}

    def measure_outcome(
        self,
        execution_record: ExecutionAuditRecord,
        decision: InterventionDecision,
        customer_events: List[BaseEvent],
        plan: Optional[Plan] = None,
        observation_window_hours: Optional[float] = None,
        measurement_timestamp: Optional[str] = None,
    ) -> OutcomeRecord:
        """
        Deterministically resolve, attribute, and record outcome for an executed intervention.
        """
        window_hours = observation_window_hours or self.config.default_observation_window_hours
        outcome_id = f"out_{execution_record.customer_id}_{execution_record.execution_id}_{int(window_hours)}h"

        # 1. Idempotency Check: Return existing immutable record
        if outcome_id in self._outcome_store:
            return self._outcome_store[outcome_id]

        measurement_ts = measurement_timestamp or decision.decision_timestamp

        # 2. Event Temporal Partitioning
        pre_events, post_events, exec_dt, obs_end_dt = EventObserver.observe_events(
            events=customer_events,
            execution_timestamp_str=execution_record.execution_timestamp,
            observation_window_hours=window_hours,
        )

        # 3. Outcome Resolution
        outcome_type, confidence, evidence_events, payment_ref = OutcomeResolver.resolve_outcome(
            execution_record=execution_record,
            pre_execution_events=pre_events,
            post_execution_events=post_events,
            execution_dt=exec_dt,
            observation_end_dt=obs_end_dt,
            measurement_timestamp_str=measurement_ts,
        )

        # 4. Attribution Level Determination
        attr_status, attr_method = AttributionEngine.evaluate_attribution(
            outcome=outcome_type,
            execution_record=execution_record,
            evidence_events=evidence_events,
            payment_reference=payment_ref,
        )

        # 5. Revenue Accounting & Reconciliation
        gross_rev, attr_rev, cost, net_rev, risk_at_decision = RevenueCalculator.calculate_revenue(
            outcome=outcome_type,
            attribution_status=attr_status,
            execution_record=execution_record,
            evidence_events=evidence_events,
            decision=decision,
            plan=plan,
            config=self.config,
        )

        # Extract event IDs and timestamps for complete audit lineage
        evidence_ids = [e.event_id for e in evidence_events]
        evidence_ts = [e.timestamp.isoformat() for e in evidence_events]

        record = OutcomeRecord(
            outcome_id=outcome_id,
            customer_id=execution_record.customer_id,
            execution_id=execution_record.execution_id,
            decision_id=execution_record.decision_id,
            action=execution_record.action,
            execution_status=execution_record.status,
            execution_timestamp=execution_record.execution_timestamp,
            observation_window_hours=window_hours,
            observation_start=exec_dt.isoformat(),
            observation_end=obs_end_dt.isoformat(),
            outcome=outcome_type,
            outcome_confidence=confidence,
            attribution_status=attr_status,
            attribution_method=attr_method,
            evidence_event_ids=evidence_ids,
            evidence_timestamps=evidence_ts,
            payment_reference=payment_ref,
            gross_observed_revenue=gross_rev,
            attributable_revenue=attr_rev,
            intervention_cost=cost,
            net_recovered_revenue=net_rev,
            revenue_at_risk_at_decision=risk_at_decision,
            resolution_timestamp=measurement_ts,
            resolver_version=self.config.resolver_version,
        )

        self._outcome_store[outcome_id] = record
        return record

    def get_outcome_record(self, outcome_id: str) -> Optional[OutcomeRecord]:
        """Retrieve a stored outcome record by ID."""
        return self._outcome_store.get(outcome_id)

    def get_customer_outcomes(self, customer_id: str) -> List[OutcomeRecord]:
        """Retrieve all stored outcome records for a customer."""
        return [rec for rec in self._outcome_store.values() if rec.customer_id == customer_id]
