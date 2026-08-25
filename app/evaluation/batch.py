"""
Batch Recovery Evaluator Module for Revive Phase 9.
Orchestrates deterministic batch evaluation across synthetic customer journeys using Phase 1-9 components.
Computes aggregate metrics, risk distributions, diagnosis distributions, policy actions, EV formulas,
and per-customer evidence records.
"""

from dataclasses import asdict, dataclass, field
from decimal import Decimal, ROUND_HALF_UP
import os
from typing import Any, Dict, List, Optional

from app.models.entities import Customer, Plan
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
from app.execution.schemas import ExecutionStatus
from app.integrations.razorpay.config import RazorpayConfig
from app.integrations.razorpay.client import MockRazorpayClient
from app.integrations.razorpay.dispatcher import RazorpaySandboxDispatcher


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
    per_customer_results: List[CustomerEvidenceRecord] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metadata": self.metadata,
            "aggregate_metrics": self.aggregate_metrics,
            "risk_distribution": self.risk_distribution,
            "diagnosis_distribution": self.diagnosis_distribution,
            "ai_status_distribution": self.ai_status_distribution,
            "action_distribution": self.action_distribution,
            "per_customer_results": [r.to_dict() for r in self.per_customer_results],
        }


class BatchRecoveryEvaluator:
    """
    Orchestrates batch recovery evaluation across synthetic customer journeys.
    Reuses existing REVIVE components deterministically.
    """

    def __init__(
        self,
        customers_count: int = 100,
        seed: int = 42,
        snapshot_hours: float = 336.0,
        model_path: str = "models/risk/risk_model.joblib",
    ) -> None:
        self.customers_count = customers_count
        self.seed = seed
        self.snapshot_hours = snapshot_hours
        self.model_path = model_path

    def evaluate(self) -> BatchEvaluationResult:
        """
        Execute deterministic batch recovery evaluation across generated customer journeys.
        Returns complete BatchEvaluationResult.
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
            gt = generator.rng.choice([True, False]) # dummy choice for rng sequence consistency
            
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

        # 3. Process Each Customer
        per_customer_records: List[CustomerEvidenceRecord] = []

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
            evts = events_by_customer.get(cid, [])

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
            )
            per_customer_records.append(rec)

        # 4. Calculate Aggregate Metrics
        total_eval = len(per_customer_records)
        avg_risk_score = round(total_risk_score_sum / total_eval, 4) if total_eval > 0 else 0.0
        avg_rev_at_risk = round(float(total_rev_at_risk) / total_eval, 2) if total_eval > 0 else 0.0
        avg_ai_confidence = round(total_ai_confidence_sum / total_eval, 4) if total_eval > 0 else 0.0

        # Formula: expected_recovery_rate = (total_ev_recovered / total_revenue_at_risk) * 100.0
        if total_rev_at_risk > Decimal("0.00"):
            exp_recovery_rate = round(float((total_ev_recovered / total_rev_at_risk) * Decimal("100.0")), 2)
        else:
            exp_recovery_rate = 0.0

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
            "total_expected_recovery_value": float(total_ev_recovered),
            "expected_recovery_rate_pct": exp_recovery_rate,
        }

        return BatchEvaluationResult(
            metadata=metadata,
            aggregate_metrics=aggregate_metrics,
            risk_distribution=risk_counts,
            diagnosis_distribution=diag_counts,
            ai_status_distribution=ai_status_counts,
            action_distribution=action_counts,
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
            per_customer_results=[],
        )
