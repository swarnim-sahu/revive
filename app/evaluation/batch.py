"""
Batch Recovery Evaluator Module for Revive Phase 9.
Orchestrates deterministic batch evaluation across synthetic customer journeys using Phase 1-9 components.
Integrates Phase 7 OutcomeEngine to measure realized recovery alongside policy expected recovery predictions.
Includes deterministic EvaluationResponseSimulator for offline response modeling.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import os
import random
from typing import Any, Dict, List, Optional

from app.models.entities import Customer, Plan
from app.models.enums import EventType
from app.models.events import BaseEvent
from app.simulation.config import ALL_PLANS, SYNTHETIC_MERCHANT
from app.simulation.generator import DatasetGenerator
from app.risk.features import CustomerFeatureExtractor
from app.risk.model import ReviveRiskModel
from app.risk.scoring import RiskScorer, ScoredCustomer
from app.diagnosis.engine import DiagnosisEngine
from app.diagnosis.schemas import Actionability
from app.ai.config import AIConfig
from app.ai.service import AIService
from app.ai.client import MockAIProvider
from app.ai.schemas import AIFailureStatus
from app.intervention.engine import InterventionEngine
from app.intervention.schemas import InterventionAction, InterventionDecision
from app.execution.engine import ExecutionEngine
from app.execution.schemas import ExecutionAuditRecord, ExecutionStatus
from app.integrations.razorpay.config import RazorpayConfig
from app.integrations.razorpay.client import MockRazorpayClient
from app.integrations.razorpay.dispatcher import RazorpaySandboxDispatcher
from app.outcome.engine import OutcomeEngine
from app.outcome.evaluation import OutcomeEvaluator
from app.outcome.schemas import OutcomeRecord, OutcomeType, AttributionStatus


class EvaluationResponseSimulator:
    """
    Offline evaluation-layer response simulator for executed interventions.

    Determines probabilistic customer responses (PAYMENT_SUCCEEDED vs PAYMENT_FAILED)
    post-intervention based on legitimate observable decision parameters.

    Architectural Boundary:
    - Lives ONLY in the evaluation layer (app/evaluation/batch.py).
    - Operates 100% deterministically using a dedicated seeded Random instance.
    - NEVER accesses hidden simulator ground-truth fields.
    - In production, post-intervention events arrive asynchronously via real Razorpay webhooks
      (payment.captured / payment_link.paid) directly into Phase 7 OutcomeEngine.
    """

    def __init__(self, seed: int = 42) -> None:
        self.rng = random.Random(seed + 777)

    def simulate_response(
        self,
        audit_record: ExecutionAuditRecord,
        decision: InterventionDecision,
        plan: Plan,
    ) -> List[BaseEvent]:
        """
        Simulate observable post-intervention customer response events.

        For executed PAYMENT_RECOVERY actions, uses the decision's baseline
        recovery probability assumption (e.g. 0.382), applies deterministic RNG sampling,
        and returns either a PAYMENT_SUCCEEDED or PAYMENT_FAILED post-execution event.
        """
        if audit_record.status != ExecutionStatus.EXECUTED:
            return []

        if audit_record.action != InterventionAction.PAYMENT_RECOVERY:
            return []

        exec_dt = datetime.fromisoformat(audit_record.execution_timestamp)
        if exec_dt.tzinfo is None:
            exec_dt = exec_dt.replace(tzinfo=timezone.utc)

        # Baseline recovery probability from intervention decision candidate scores
        prob = 0.382  # Default baseline assumption for PAYMENT_RECOVERY
        for candidate in decision.candidate_scores:
            if candidate.action == InterventionAction.PAYMENT_RECOVERY:
                prob = candidate.recovery_probability_assumption
                break

        # Bounded between 0.0 and 1.0
        prob = max(0.0, min(1.0, prob))

        # Deterministic RNG sample
        roll = self.rng.random()
        success = roll < prob

        resp_ts = exec_dt + timedelta(hours=2)
        cid = audit_record.customer_id
        payload_id = audit_record.payload_id or "mock"

        if success:
            resp_evt = BaseEvent(
                event_id=f"evt_{cid}_resp_pay_succ",
                event_type=EventType.PAYMENT_SUCCEEDED,
                schema_version="1.0",
                merchant_id=audit_record.merchant_id or SYNTHETIC_MERCHANT.merchant_id,
                customer_id=cid,
                timestamp=resp_ts,
                source="evaluation_response_simulator",
                payload={
                    "payment_id": f"pay_ref_{payload_id}",
                    "amount": str(plan.price),
                },
            )
        else:
            resp_evt = BaseEvent(
                event_id=f"evt_{cid}_resp_pay_fail",
                event_type=EventType.PAYMENT_FAILED,
                schema_version="1.0",
                merchant_id=audit_record.merchant_id or SYNTHETIC_MERCHANT.merchant_id,
                customer_id=cid,
                timestamp=resp_ts,
                source="evaluation_response_simulator",
                payload={
                    "error_code": "CARD_DECLINED",
                    "amount": str(plan.price),
                },
            )

        return [resp_evt]


@dataclass
class CustomerEvidenceRecord:
    """Per-customer evidence record constructed without leaking secrets or ground truth."""

    customer_id: str
    risk_score: float
    risk_tier: str
    revenue_at_risk: float
    diagnosis: str
    diagnosis_confidence: float
    ai_status: str
    ai_confidence: float
    fallback_used: bool
    eligibility_status: str
    selected_action: str
    expected_value: float
    decision_reason: str
    execution_status: str
    failure_reason: Optional[str] = None
    # Phase 7 Measured Outcome Audit Fields
    outcome: Optional[str] = None
    outcome_confidence: Optional[float] = None
    attribution_status: Optional[str] = None
    attributable_revenue: Optional[float] = None
    net_recovered_revenue: Optional[float] = None
    payment_reference: Optional[str] = None
    evidence_event_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BatchEvaluationResult:
    """Aggregate metrics summary and per-customer evidence records."""

    metadata: Dict[str, Any]
    aggregate_metrics: Dict[str, Any]
    risk_distribution: Dict[str, int]
    diagnosis_distribution: Dict[str, int]
    ai_status_distribution: Dict[str, int]
    action_distribution: Dict[str, int]
    outcome_distribution: Dict[str, int] = field(default_factory=dict)
    attribution_distribution: Dict[str, int] = field(default_factory=dict)
    per_customer_results: List[CustomerEvidenceRecord] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metadata": self.metadata,
            "aggregate_metrics": self.aggregate_metrics,
            "risk_distribution": self.risk_distribution,
            "diagnosis_distribution": self.diagnosis_distribution,
            "ai_status_distribution": self.ai_status_distribution,
            "action_distribution": self.action_distribution,
            "outcome_distribution": self.outcome_distribution,
            "attribution_distribution": self.attribution_distribution,
            "per_customer_results": [r.to_dict() for r in self.per_customer_results],
        }


class BatchRecoveryEvaluator:
    """
    Orchestrates batch recovery evaluation across synthetic customer journeys.
    Reuses existing REVIVE components deterministically and integrates Phase 7 OutcomeEngine.
    """

    def __init__(
        self,
        customers_count: int = 100,
        seed: int = 42,
        snapshot_hours: float = 336.0,
        observation_window_hours: float = 168.0,
        model_path: str = "models/risk/risk_model.joblib",
    ) -> None:
        self.customers_count = customers_count
        self.seed = seed
        self.snapshot_hours = snapshot_hours
        self.observation_window_hours = observation_window_hours
        self.model_path = model_path

    def evaluate(self) -> BatchEvaluationResult:
        """
        Execute deterministic batch recovery evaluation across generated customer journeys.
        Returns complete BatchEvaluationResult containing both Expected and Measured Recovery.
        """
        if self.customers_count <= 0:
            return self._empty_result()

        # 1. Generate Dataset using DatasetGenerator
        temp_output = f"data/temp_batch_{self.seed}_{self.customers_count}"
        generator = DatasetGenerator(
            customers_count=self.customers_count,
            seed=self.seed,
            output_dir=temp_output,
        )

        # Build in-memory customer journey pairs
        pairs = generator._allocate_plans_and_segments()
        
        customers: List[Customer] = []
        events_by_customer: Dict[str, List[BaseEvent]] = {}
        all_events_count = 0

        for idx, (segment, plan_id) in enumerate(pairs, start=1):
            customer_id = f"cus_{idx:06d}"
            plan = ALL_PLANS[plan_id]
            gt = generator.rng.choice([True, False])  # dummy choice for rng sequence consistency
            
            # Generate customer journey
            from app.simulation.journey import generate_customer_journey
            from app.simulation.segments import create_ground_truth
            from app.simulation.behaviour import sample_behaviour

            gt_rec = create_ground_truth(customer_id, segment, plan, generator.rng)
            behaviour = sample_behaviour(segment, gt_rec.natural_conversion, generator.rng)
            cus, trl, evts, pay, sub = generate_customer_journey(
                customer_id=customer_id,
                merchant_id=SYNTHETIC_MERCHANT.merchant_id,
                plan=plan,
                behaviour=behaviour,
                rng=generator.rng,
            )
            customers.append(cus)
            events_by_customer[customer_id] = evts
            all_events_count += len(evts)

        # 2. Instantiate Phase 1-9 Pipeline Components
        if os.path.exists(self.model_path):
            risk_model = ReviveRiskModel.load(self.model_path)
        else:
            raise FileNotFoundError(f"Risk model artifact not found at '{self.model_path}'")

        risk_scorer = RiskScorer(model=risk_model)
        feature_extractor = CustomerFeatureExtractor(snapshot_hours=self.snapshot_hours)
        diagnosis_engine = DiagnosisEngine()
        
        ai_config = AIConfig(provider="mock")
        ai_service = AIService(config=ai_config, provider=MockAIProvider(config=ai_config))

        intervention_engine = InterventionEngine()

        rzp_config = RazorpayConfig(
            environment="sandbox",
            key_id="rzp_test_MOCK12345",
            key_secret="SECRET_MOCK_99999",
        )
        mock_rzp_client = MockRazorpayClient(config=rzp_config)
        dispatcher = RazorpaySandboxDispatcher(config=rzp_config, client=mock_rzp_client)
        exec_engine = ExecutionEngine(dispatcher=dispatcher)

        # Phase 7 Outcome Measurement Engine & Evaluation Response Simulator
        outcome_engine = OutcomeEngine()
        response_simulator = EvaluationResponseSimulator(seed=self.seed)

        # 3. Process Each Customer
        per_customer_records: List[CustomerEvidenceRecord] = []
        outcome_records: List[OutcomeRecord] = []

        risk_counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
        diag_counts: Dict[str, int] = {}
        ai_status_counts: Dict[str, int] = {}
        action_counts: Dict[str, int] = {act.value: 0 for act in InterventionAction}

        cust_with_pay_failures = 0
        actionable_diag_count = 0
        non_actionable_diag_count = 0
        ai_fallback_count = 0

        total_risk_score_sum = 0.0
        total_rev_at_risk = Decimal("0.00")
        total_ev_recovered = Decimal("0.00")
        total_ai_confidence_sum = 0.0

        eligible_count = 0
        ineligible_count = 0
        execution_candidates = 0
        successful_executions = 0
        failed_executions = 0
        blocked_executions = 0

        for cust in customers:
            cid = cust.customer_id
            plan = ALL_PLANS[cust.plan_id]
            evts = list(events_by_customer.get(cid, []))

            has_pay_fail = any(e.event_type.value == "payment_failed" for e in evts)
            if has_pay_fail:
                cust_with_pay_failures += 1

            # Feature extraction
            feat_rec, status_str = feature_extractor.extract_features(cust, evts, plan)
            if status_str != "OK":
                continue

            # Risk scoring
            scored_cust = risk_scorer.score_customer(feat_rec)
            risk_counts[scored_cust.risk_tier] += 1
            total_risk_score_sum += scored_cust.risk_score
            total_rev_at_risk += scored_cust.revenue_at_risk

            # Diagnosis
            base_diag = diagnosis_engine.diagnose_customer(scored_cust, cust, evts, plan, feat_rec)
            diag_val = base_diag.diagnosis.value
            diag_counts[diag_val] = diag_counts.get(diag_val, 0) + 1

            if base_diag.actionability == Actionability.CANDIDATE:
                actionable_diag_count += 1
            else:
                non_actionable_diag_count += 1

            # AI Service
            ai_res = ai_service.analyze_and_diagnose(scored_cust, cust, evts, plan, feat_rec)
            ai_stat = ai_res.metadata.status.value
            ai_status_counts[ai_stat] = ai_status_counts.get(ai_stat, 0) + 1
            total_ai_confidence_sum += ai_res.final_diagnosis.confidence

            if ai_res.metadata.fallback_used:
                ai_fallback_count += 1

            # Intervention Policy
            decision = intervention_engine.decide_intervention(
                scored_customer=scored_cust,
                diagnosis=ai_res.final_diagnosis,
                plan=plan,
                feature_record=feat_rec,
            )
            act_val = decision.selected_action.value
            action_counts[act_val] += 1

            if decision.eligibility_status == "ELIGIBLE":
                eligible_count += 1
            else:
                ineligible_count += 1

            # Execution Engine Dispatch
            if decision.selected_action != InterventionAction.NO_ACTION:
                execution_candidates += 1

            audit_rec = exec_engine.execute_decision(decision)
            
            if audit_rec.status == ExecutionStatus.EXECUTED:
                successful_executions += 1
                total_ev_recovered += decision.expected_value
            elif audit_rec.status == ExecutionStatus.FAILED:
                failed_executions += 1
            elif audit_rec.status == ExecutionStatus.BLOCKED:
                blocked_executions += 1

            # Deterministic Evaluation-Layer Response Simulation (Zero Ground Truth Access)
            post_events = response_simulator.simulate_response(
                audit_record=audit_rec,
                decision=decision,
                plan=plan,
            )

            all_cust_events = evts + post_events

            # Phase 7 OutcomeEngine Measurement
            outcome_rec = outcome_engine.measure_outcome(
                execution_record=audit_rec,
                decision=decision,
                customer_events=all_cust_events,
                plan=plan,
                observation_window_hours=self.observation_window_hours,
            )
            outcome_records.append(outcome_rec)

            # Build CustomerEvidenceRecord
            rec = CustomerEvidenceRecord(
                customer_id=cid,
                risk_score=scored_cust.risk_score,
                risk_tier=scored_cust.risk_tier,
                revenue_at_risk=float(scored_cust.revenue_at_risk),
                diagnosis=base_diag.diagnosis.value,
                diagnosis_confidence=base_diag.confidence,
                ai_status=ai_stat,
                ai_confidence=ai_res.final_diagnosis.confidence,
                fallback_used=ai_res.metadata.fallback_used,
                eligibility_status=decision.eligibility_status,
                selected_action=act_val,
                expected_value=float(decision.expected_value),
                decision_reason=decision.decision_reason,
                execution_status=audit_rec.status.value,
                failure_reason=audit_rec.failure_reason,
                outcome=outcome_rec.outcome.value,
                outcome_confidence=outcome_rec.outcome_confidence,
                attribution_status=outcome_rec.attribution_status.value,
                attributable_revenue=float(outcome_rec.attributable_revenue),
                net_recovered_revenue=float(outcome_rec.net_recovered_revenue),
                payment_reference=outcome_rec.payment_reference,
                evidence_event_ids=outcome_rec.evidence_event_ids,
            )
            per_customer_records.append(rec)

        # 4. Calculate Aggregate Metrics using OutcomeEvaluator
        eval_metrics = OutcomeEvaluator.evaluate_outcome_records(outcome_records)

        total_eval = len(per_customer_records)
        avg_risk_score = round(total_risk_score_sum / total_eval, 4) if total_eval > 0 else 0.0
        avg_rev_at_risk = round(float(total_rev_at_risk) / total_eval, 2) if total_eval > 0 else 0.0
        avg_ai_confidence = round(total_ai_confidence_sum / total_eval, 4) if total_eval > 0 else 0.0

        # Formula: expected_recovery_rate = (total_ev_recovered / total_revenue_at_risk) * 100.0
        if total_rev_at_risk > Decimal("0.00"):
            exp_recovery_rate = round(float((total_ev_recovered / total_rev_at_risk) * Decimal("100.0")), 2)
        else:
            exp_recovery_rate = 0.0

        # Phase 7 Measured Recovery Accounting Metrics
        total_gross_obs_rev = eval_metrics.get("gross_observed_revenue", 0.0)
        total_attr_rev = eval_metrics.get("attributable_revenue", 0.0)
        total_cost = eval_metrics.get("intervention_cost", 0.0)
        total_net_rev = eval_metrics.get("net_recovered_revenue", 0.0)

        # Measured recovery rate = (total_net_recovered_revenue / total_revenue_at_risk) * 100.0
        if total_rev_at_risk > Decimal("0.00"):
            meas_recovery_rate = round((total_net_rev / float(total_rev_at_risk)) * 100.0, 2)
        else:
            meas_recovery_rate = 0.0

        recovered_cust_count = eval_metrics.get("outcome_counts", {}).get("RECOVERED", 0)

        duplicates_prevented = len(mock_rzp_client.processed_idempotency_keys) - len(mock_rzp_client.created_links)

        metadata = {
            "customers_requested": self.customers_count,
            "seed": self.seed,
            "evaluation_engine_version": "v1.0.0",
        }

        aggregate_metrics = {
            "total_customers": total_eval,
            "total_events": all_events_count,
            "customers_with_payment_failures": cust_with_pay_failures,
            "average_risk_score": avg_risk_score,
            "average_revenue_at_risk": avg_rev_at_risk,
            "total_revenue_at_risk": float(total_rev_at_risk),
            "payment_friction_count": diag_counts.get("PAYMENT_FRICTION", 0),
            "actionable_diagnosis_count": actionable_diag_count,
            "non_actionable_diagnosis_count": non_actionable_diag_count,
            "ai_success_count": ai_status_counts.get("AI_SUCCESS", 0),
            "ai_fallback_count": ai_fallback_count,
            "ai_schema_invalid_count": ai_status_counts.get("AI_SCHEMA_INVALID", 0),
            "ai_grounding_failed_count": ai_status_counts.get("AI_GROUNDING_FAILED", 0),
            "ai_low_confidence_count": ai_status_counts.get("AI_LOW_CONFIDENCE", 0),
            "average_ai_confidence": avg_ai_confidence,
            "eligible_customers": eligible_count,
            "ineligible_customers": ineligible_count,
            "execution_candidates": execution_candidates,
            "simulated_successful_executions": successful_executions,
            "simulated_failed_executions": failed_executions,
            "blocked_executions": blocked_executions,
            "duplicates_prevented": duplicates_prevented,
            # Policy Expected Recovery
            "total_expected_recovery_value": float(total_ev_recovered),
            "expected_recovery_rate_pct": exp_recovery_rate,
            # Phase 7 Measured Recovery (Attributed via OutcomeEngine)
            "total_gross_observed_revenue": total_gross_obs_rev,
            "total_attributable_revenue": total_attr_rev,
            "total_intervention_cost": total_cost,
            "total_net_recovered_revenue": total_net_rev,
            "measured_recovery_rate_pct": meas_recovery_rate,
            "recovered_customer_count": recovered_cust_count,
        }

        return BatchEvaluationResult(
            metadata=metadata,
            aggregate_metrics=aggregate_metrics,
            risk_distribution=risk_counts,
            diagnosis_distribution=diag_counts,
            ai_status_distribution=ai_status_counts,
            action_distribution=action_counts,
            outcome_distribution=eval_metrics.get("outcome_counts", {}),
            attribution_distribution=eval_metrics.get("attribution_counts", {}),
            per_customer_results=per_customer_records,
        )

    def _empty_result(self) -> BatchEvaluationResult:
        return BatchEvaluationResult(
            metadata={"customers_requested": 0, "seed": self.seed},
            aggregate_metrics={"total_customers": 0, "total_events": 0},
            risk_distribution={},
            diagnosis_distribution={},
            ai_status_distribution={},
            action_distribution={},
            outcome_distribution={},
            attribution_distribution={},
            per_customer_results=[],
        )
