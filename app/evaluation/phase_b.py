"""
Phase B Master Evaluator: Controlled High-Volume Evaluation & Incremental Revenue Benchmark.
Orchestrates paired Control vs Treatment evaluation across paired customer experimental units.
Integrates all Phase 1-9 engines, DiagnosisEvaluator, InterventionEvaluator, OutcomeEngine,
ExceptionLedger, High-Resolution Performance Timers, and Multi-Identity Financial Reconciliation.
"""

from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import os
import platform
import time
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel

from app.models.entities import Customer, Plan
from app.models.events import BaseEvent
from app.simulation.config import ALL_PLANS, SYNTHETIC_MERCHANT
from app.simulation.generator import DatasetGenerator
from app.simulation.ground_truth import GroundTruthRecord
from app.risk.features import CustomerFeatureExtractor
from app.risk.model import ReviveRiskModel
from app.risk.scoring import RiskScorer, ScoredCustomer
from app.diagnosis.engine import DiagnosisEngine
from app.diagnosis.schemas import Actionability, CustomerDiagnosis, DiagnosisCategory
from app.diagnosis.evaluation import DiagnosisEvaluator
from app.ai.config import AIConfig
from app.ai.service import AIService
from app.ai.client import MockAIProvider
from app.intervention.engine import InterventionEngine
from app.intervention.schemas import InterventionAction, InterventionDecision
from app.intervention.evaluation import InterventionEvaluator
from app.execution.engine import ExecutionEngine
from app.execution.schemas import ExecutionAuditRecord, ExecutionStatus
from app.integrations.razorpay.config import RazorpayConfig
from app.integrations.razorpay.client import MockRazorpayClient
from app.integrations.razorpay.dispatcher import RazorpaySandboxDispatcher
from app.outcome.engine import OutcomeEngine
from app.outcome.evaluation import OutcomeEvaluator
from app.outcome.schemas import OutcomeRecord, OutcomeType, AttributionStatus
from app.evaluation.schemas import (
    ComparativeEconomics,
    ControlCaseRecord,
    DecisionFunnelSummary,
    DiagnosisAccuracySummary,
    ExceptionRecord,
    ExperimentMetadata,
    InterventionAppropriatenessSummary,
    PairedCaseResult,
    PhaseBEvaluationResult,
    SafetyGovernanceSummary,
    ThroughputSummary,
    TreatmentCaseRecord,
)
from app.evaluation.control import ControlEvaluator
from app.evaluation.exceptions import ExceptionLedger
from app.evaluation.batch import EvaluationResponseSimulator


class ConversionClassification(BaseModel):
    """Pure evaluation-layer model representing the 4-way conversion classification result."""

    conversion_classification: str
    is_natural_conversion: bool
    is_genuine_incremental_recovery: bool
    is_observed_unrecoverable_conversion: bool


def classify_treatment_conversion(
    natural_conversion: bool,
    recoverable: bool,
    treatment_converted: bool,
) -> ConversionClassification:
    """
    Pure evaluation-layer helper for 4-way conversion outcome classification.
    Determines whether a treatment conversion represents a natural conversion,
    a genuine incremental recovery, or an observed conversion on an unrecoverable case.
    """
    if treatment_converted:
        if natural_conversion:
            return ConversionClassification(
                conversion_classification="NATURAL_CONVERSION",
                is_natural_conversion=True,
                is_genuine_incremental_recovery=False,
                is_observed_unrecoverable_conversion=False,
            )
        elif recoverable:
            return ConversionClassification(
                conversion_classification="GENUINE_INCREMENTAL_RECOVERY",
                is_natural_conversion=False,
                is_genuine_incremental_recovery=True,
                is_observed_unrecoverable_conversion=False,
            )
        else:
            return ConversionClassification(
                conversion_classification="OBSERVED_UNRECOVERABLE_CONVERSION",
                is_natural_conversion=False,
                is_genuine_incremental_recovery=False,
                is_observed_unrecoverable_conversion=True,
            )
    else:
        return ConversionClassification(
            conversion_classification="NO_TREATMENT_CONVERSION",
            is_natural_conversion=False,
            is_genuine_incremental_recovery=False,
            is_observed_unrecoverable_conversion=False,
        )


def determine_paired_increment(
    treatment_converted: bool,
    control_converted: bool,
    is_genuine_incremental_recovery: bool,
) -> bool:
    """
    Pure evaluation-layer helper for determining whether a paired experimental unit represents
    a genuine incremental conversion (Treatment converted, Control did not, and case is genuinely recoverable).
    """
    return bool(treatment_converted and not control_converted and is_genuine_incremental_recovery)


class PhaseBEvaluator:
    """
    Master Controlled Experiment Runner for REVIVE Phase B.
    Runs paired Control vs Treatment arms across a shared seeded population.
    """

    def __init__(
        self,
        total_population: int = 20000,
        control_count: Optional[int] = None,
        treatment_count: Optional[int] = None,
        seed: int = 42,
        snapshot_hours: float = 336.0,
        observation_window_hours: float = 168.0,
        model_path: str = "models/risk/risk_model.joblib",
    ) -> None:
        if control_count is not None:
            self.paired_units = control_count
        elif total_population > 1 and total_population % 2 == 0:
            self.paired_units = total_population // 2
        else:
            self.paired_units = max(1, total_population)

        self.control_count = self.paired_units
        self.treatment_count = self.paired_units
        self.total_arm_evaluations = self.paired_units * 2
        self.seed = seed
        self.snapshot_hours = snapshot_hours
        self.observation_window_hours = observation_window_hours
        self.model_path = model_path
        self.exception_ledger = ExceptionLedger()

    def run_evaluation(
        self,
        case_callback: Optional[Callable[[PairedCaseResult], None]] = None,
        exception_callback: Optional[Callable[[ExceptionRecord], None]] = None,
    ) -> PhaseBEvaluationResult:
        """
        Execute the full Phase B paired controlled evaluation.
        Supports streaming callbacks for per-case audit persistence.
        """
        start_wall_time = datetime.now(timezone.utc).isoformat()
        t_start = time.perf_counter()

        # 1. Generate Shared Seeded Population of exactly paired_units
        temp_dir = f"data/temp_phase_b_{self.seed}_{self.paired_units}"
        generator = DatasetGenerator(
            customers_count=self.paired_units,
            seed=self.seed,
            output_dir=temp_dir,
        )

        pairs = generator._allocate_plans_and_segments()

        customers: List[Customer] = []
        events_by_customer: Dict[str, List[BaseEvent]] = {}
        ground_truth_by_customer: Dict[str, GroundTruthRecord] = {}
        plans_map = ALL_PLANS

        for idx, (segment, plan_id) in enumerate(pairs, start=1):
            customer_id = f"cus_{idx:06d}"
            plan = ALL_PLANS[plan_id]

            from app.simulation.journey import generate_customer_journey
            from app.simulation.segments import create_ground_truth
            from app.simulation.behaviour import sample_behaviour

            gt_rec = create_ground_truth(customer_id, segment, plan, generator.rng)
            ground_truth_by_customer[customer_id] = gt_rec

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

        # 2. Instantiate Phase 1-9 Treatment Pipeline Components
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Risk model artifact not found at '{self.model_path}'")

        risk_model = ReviveRiskModel.load(self.model_path)
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

        outcome_engine = OutcomeEngine()
        response_simulator = EvaluationResponseSimulator(seed=self.seed)

        # 3. Paired Cohort Processing
        eval_customers = customers[:self.paired_units]

        paired_results: List[PairedCaseResult] = []
        treatment_diagnoses: List[CustomerDiagnosis] = []
        treatment_decisions: List[InterventionDecision] = []
        treatment_feature_records: Dict[str, Dict[str, Any]] = {}
        treatment_outcome_records: List[OutcomeRecord] = []

        case_latencies_ms: List[float] = []

        # Tracking counters for Funnel & Lifecycle Reconciliation
        successful_cases = 0
        stopped_cases = 0
        escalated_cases = 0
        failed_cases = 0
        unresolved_cases = 0

        # Event counts tracking
        initial_journey_events_count = 0
        post_treatment_events_count = 0

        # Control Arm Totals
        control_conversions_count = 0
        control_gross_revenue_sum = 0.0
        control_net_revenue_sum = 0.0
        control_risk_sum = 0.0

        # Treatment Arm Totals
        treatment_total_conversions_count = 0
        treatment_natural_conversions_count = 0
        treatment_genuine_incremental_recoveries_count = 0
        treatment_observed_unrecoverable_conversions_count = 0
        treatment_gross_obs_sum = 0.0
        treatment_attr_rev_sum = 0.0
        treatment_cost_sum = 0.0
        treatment_net_rec_rev_sum = 0.0
        treatment_total_net_rev_sum = 0.0
        treatment_genuine_incremental_revenue_sum = 0.0
        treatment_ev_sum = 0.0
        total_max_recoverable_revenue = 0.0

        for cust in eval_customers:
            t_case_start = time.perf_counter()
            cid = cust.customer_id
            plan = plans_map[cust.plan_id]
            plan_price = float(plan.price)
            evts = events_by_customer.get(cid, [])
            initial_journey_events_count += len(evts)
            gt = ground_truth_by_customer[cid]

            if gt.recoverable:
                total_max_recoverable_revenue += float(gt.maximum_recoverable_revenue)

            # --- ARM A: CONTROL EVALUATION (No REVIVE Intervention, ₹0 Cost) ---
            ctrl_rec = ControlEvaluator.evaluate_control_case(cust, plan, gt)
            if ctrl_rec.control_converted:
                control_conversions_count += 1
            control_gross_revenue_sum += ctrl_rec.control_gross_revenue
            control_net_revenue_sum += ctrl_rec.control_net_revenue
            control_risk_sum += ctrl_rec.control_revenue_at_risk

            # --- ARM B: TREATMENT EVALUATION (Full REVIVE Pipeline) ---
            feat_rec, status_str = feature_extractor.extract_features(cust, evts, plan)

            if status_str != "OK":
                exc = self.exception_ledger.record_exception(
                    case_id=f"case_treat_{cid}",
                    stage="RISK_FEATURE_EXTRACTION",
                    status="FAILED",
                    failure_type="invalid_input",
                    retryable=False,
                    safe_action_taken="NO_ACTION",
                    financial_impact=plan_price,
                    human_escalation_required=False,
                    reason=f"Feature extraction failed with status '{status_str}'",
                )
                if exception_callback:
                    exception_callback(exc)
                failed_cases += 1
                continue

            treatment_feature_records[cid] = feat_rec

            # 1. Risk Scoring
            scored_cust = risk_scorer.score_customer(feat_rec)

            # 2. Diagnosis
            base_diag = diagnosis_engine.diagnose_customer(scored_cust, cust, evts, plan, feat_rec)

            # 3. AI Service
            ai_res = ai_service.analyze_and_diagnose(scored_cust, cust, evts, plan, feat_rec)
            final_diag = ai_res.final_diagnosis
            treatment_diagnoses.append(final_diag)

            if ai_res.metadata.fallback_used:
                exc = self.exception_ledger.record_exception(
                    case_id=f"case_treat_{cid}",
                    stage="AI_SERVICE",
                    status="FALLBACK",
                    failure_type="ai_fallback",
                    retryable=True,
                    safe_action_taken="DETERMINISTIC_HEURISTIC_FALLBACK",
                    financial_impact=0.0,
                    human_escalation_required=False,
                    reason="AI Service utilized deterministic fallback rules",
                )
                if exception_callback:
                    exception_callback(exc)

            # 4. Intervention Policy Decision
            decision = intervention_engine.decide_intervention(
                scored_customer=scored_cust,
                diagnosis=final_diag,
                plan=plan,
                feature_record=feat_rec,
            )
            treatment_decisions.append(decision)

            # Lifecycle State & Stopping Tracking
            if decision.selected_action == InterventionAction.NO_ACTION:
                stopped_cases += 1
                exc = self.exception_ledger.record_exception(
                    case_id=f"case_treat_{cid}",
                    stage="INTERVENTION_POLICY",
                    status="STOPPED",
                    failure_type="policy_block",
                    retryable=False,
                    safe_action_taken="NO_ACTION",
                    financial_impact=0.0,
                    human_escalation_required=False,
                    reason=f"Policy selected NO_ACTION: {decision.decision_reason}",
                )
                if exception_callback:
                    exception_callback(exc)
            elif decision.selected_action == InterventionAction.HUMAN_REVIEW:
                escalated_cases += 1
                exc = self.exception_ledger.record_exception(
                    case_id=f"case_treat_{cid}",
                    stage="INTERVENTION_POLICY",
                    status="ESCALATED",
                    failure_type="policy_block",
                    retryable=True,
                    safe_action_taken="HUMAN_REVIEW",
                    financial_impact=0.0,
                    human_escalation_required=True,
                    reason=f"Policy escalated to human review: {decision.decision_reason}",
                )
                if exception_callback:
                    exception_callback(exc)

            # 5. Execution Dispatch Simulation
            audit_rec = exec_engine.execute_decision(decision)

            if audit_rec.status == ExecutionStatus.FAILED:
                failed_cases += 1
                exc = self.exception_ledger.record_exception(
                    case_id=f"case_treat_{cid}",
                    stage="EXECUTION",
                    status="FAILED",
                    failure_type="execution_failure",
                    retryable=True,
                    safe_action_taken="EXECUTION_FAILURE_HANDLING",
                    financial_impact=plan_price,
                    human_escalation_required=False,
                    reason=f"Execution dispatch failed: {audit_rec.failure_reason}",
                )
                if exception_callback:
                    exception_callback(exc)
            elif audit_rec.status == ExecutionStatus.EXECUTED:
                treatment_ev_sum += float(decision.expected_value)

            # 6. Evaluation Response Simulation (Zero Ground Truth Access)
            post_events = response_simulator.simulate_response(
                audit_record=audit_rec,
                decision=decision,
                plan=plan,
            )
            post_treatment_events_count += len(post_events)

            all_cust_events = evts + post_events

            # 7. Phase 7 OutcomeEngine Measurement
            outcome_rec = outcome_engine.measure_outcome(
                execution_record=audit_rec,
                decision=decision,
                customer_events=all_cust_events,
                plan=plan,
                observation_window_hours=self.observation_window_hours,
            )
            treatment_outcome_records.append(outcome_rec)

            # 8. Mutually Exclusive Lifecycle & Disjoint Status Resolution
            if decision.selected_action not in {InterventionAction.NO_ACTION, InterventionAction.HUMAN_REVIEW} and audit_rec.status != ExecutionStatus.FAILED:
                if outcome_rec.outcome == OutcomeType.UNKNOWN:
                    unresolved_cases += 1
                    exc = self.exception_ledger.record_exception(
                        case_id=f"case_treat_{cid}",
                        stage="OUTCOME",
                        status="UNRESOLVED",
                        failure_type="unresolved",
                        retryable=False,
                        safe_action_taken="AUDIT_LOG_UNRESOLVED",
                        financial_impact=plan_price,
                        human_escalation_required=True,
                        reason="Outcome could not be deterministically resolved within observation window",
                    )
                    if exception_callback:
                        exception_callback(exc)
                else:
                    successful_cases += 1

            # 9. Realized Treatment Conversion & Revenue Accounting
            if decision.selected_action in {InterventionAction.NO_ACTION, InterventionAction.HUMAN_REVIEW}:
                cost = 0.0
                attr_rev = 0.0
                net_rec_rev = 0.0
                if gt.natural_conversion:
                    treat_converted = True
                    gross_obs = plan_price
                    total_net_rev = plan_price
                else:
                    treat_converted = False
                    gross_obs = 0.0
                    total_net_rev = 0.0
            else:
                # Active Automated Action
                cost = float(outcome_rec.intervention_cost)
                attr_rev = float(outcome_rec.attributable_revenue)
                net_rec_rev = float(outcome_rec.net_recovered_revenue)

                if outcome_rec.outcome in {OutcomeType.RECOVERED, OutcomeType.CONVERTED}:
                    treat_converted = True
                    gross_obs = float(outcome_rec.gross_observed_revenue)
                    total_net_rev = gross_obs - cost
                elif outcome_rec.outcome == OutcomeType.ALREADY_CONVERTED:
                    treat_converted = True
                    gross_obs = plan_price
                    attr_rev = 0.0
                    net_rec_rev = 0.0
                    total_net_rev = plan_price - cost
                else:
                    # NOT_RECOVERED, EXPIRED, NO_OBSERVABLE_OUTCOME, UNKNOWN
                    attr_rev = 0.0
                    net_rec_rev = -cost
                    if gt.natural_conversion:
                        treat_converted = True
                        gross_obs = plan_price
                        total_net_rev = plan_price - cost
                    else:
                        treat_converted = False
                        gross_obs = 0.0
                        total_net_rev = -cost

            # Call extracted production classification helper
            cls_res = classify_treatment_conversion(
                natural_conversion=gt.natural_conversion,
                recoverable=gt.recoverable,
                treatment_converted=treat_converted,
            )
            conv_class = cls_res.conversion_classification
            is_natural = cls_res.is_natural_conversion
            is_genuine_rec = cls_res.is_genuine_incremental_recovery
            is_unrec_conv = cls_res.is_observed_unrecoverable_conversion

            if treat_converted:
                treatment_total_conversions_count += 1
                if is_natural:
                    treatment_natural_conversions_count += 1
                elif is_genuine_rec:
                    treatment_genuine_incremental_recoveries_count += 1
                    treatment_genuine_incremental_revenue_sum += plan_price
                elif is_unrec_conv:
                    treatment_observed_unrecoverable_conversions_count += 1

            treatment_gross_obs_sum += gross_obs
            treatment_attr_rev_sum += attr_rev
            treatment_cost_sum += cost
            treatment_net_rec_rev_sum += net_rec_rev
            treatment_total_net_rev_sum += total_net_rev

            treat_rec = TreatmentCaseRecord(
                case_id=f"case_treat_{cid}",
                customer_id=cid,
                risk_score=scored_cust.risk_score,
                risk_tier=scored_cust.risk_tier,
                revenue_at_risk=float(scored_cust.revenue_at_risk),
                diagnosis=final_diag.diagnosis.value,
                diagnosis_confidence=final_diag.confidence,
                diagnosis_actionability=final_diag.actionability.value,
                ai_status=ai_res.metadata.status.value,
                ai_confidence=ai_res.final_diagnosis.confidence,
                fallback_used=ai_res.metadata.fallback_used,
                eligibility_status=decision.eligibility_status,
                selected_action=decision.selected_action.value,
                expected_value=float(decision.expected_value),
                decision_reason=decision.decision_reason,
                execution_status=audit_rec.status.value,
                failure_reason=audit_rec.failure_reason,
                outcome=outcome_rec.outcome.value,
                outcome_confidence=outcome_rec.outcome_confidence,
                attribution_status=outcome_rec.attribution_status.value,
                treatment_converted=treat_converted,
                conversion_classification=conv_class,
                is_natural_conversion=is_natural,
                is_genuine_incremental_recovery=is_genuine_rec,
                is_observed_unrecoverable_conversion=is_unrec_conv,
                gross_observed_revenue=gross_obs,
                attributable_revenue=attr_rev,
                intervention_cost=cost,
                net_recovered_revenue=net_rec_rev,
                total_net_revenue=total_net_rev,
                payment_reference=outcome_rec.payment_reference,
            )

            # Call extracted production paired increment helper
            is_inc_conv = determine_paired_increment(
                treatment_converted=treat_converted,
                control_converted=ctrl_rec.control_converted,
                is_genuine_incremental_recovery=is_genuine_rec,
            )
            inc_net_rev = total_net_rev - ctrl_rec.control_net_revenue

            paired_res = PairedCaseResult(
                case_id=f"paired_{cid}",
                customer_id=cid,
                plan_id=cust.plan_id,
                plan_price=plan_price,
                control=ctrl_rec,
                treatment=treat_rec,
                conversion_classification=conv_class,
                is_incremental_conversion=is_inc_conv,
                incremental_net_revenue=inc_net_rev,
            )
            paired_results.append(paired_res)

            if case_callback:
                case_callback(paired_res)

            t_case_end = time.perf_counter()
            case_latencies_ms.append((t_case_end - t_case_start) * 1000.0)

        t_end = time.perf_counter()
        elapsed_sec = max(0.0001, round(t_end - t_start, 4))
        end_wall_time = datetime.now(timezone.utc).isoformat()

        # 4. Compute Diagnosis Quality Metrics
        gt_raw_map = {c.customer_id: ground_truth_by_customer[c.customer_id].true_root_cause for c in eval_customers}
        diag_eval_res = DiagnosisEvaluator.evaluate_diagnoses(
            diagnoses=treatment_diagnoses,
            ground_truth_map=gt_raw_map,
            customer_events_map={c.customer_id: events_by_customer[c.customer_id] for c in eval_customers},
            feature_records_map=treatment_feature_records,
        )

        diag_summary = DiagnosisAccuracySummary(
            overall_accuracy=diag_eval_res["overall_accuracy"],
            macro_precision=diag_eval_res["macro_precision"],
            macro_recall=diag_eval_res["macro_recall"],
            macro_f1=diag_eval_res["macro_f1"],
            uncertain_rate=diag_eval_res["uncertain_rate"],
            per_class_report=diag_eval_res["per_class_report"],
            confusion_matrix=diag_eval_res["confusion_matrix"],
            labels=diag_eval_res["labels"],
        )

        # 5. Compute Intervention Appropriateness & NO_ACTION Analysis
        active_decisions = [
            d for d in treatment_decisions
            if d.selected_action not in {InterventionAction.NO_ACTION, InterventionAction.HUMAN_REVIEW}
        ]
        no_action_decisions = [
            d for d in treatment_decisions
            if d.selected_action == InterventionAction.NO_ACTION
        ]

        # Active intervention classification
        targeted_rec = sum(
            1 for d in active_decisions
            if ground_truth_by_customer[d.customer_id].recoverable and not ground_truth_by_customer[d.customer_id].natural_conversion
        )
        unnecessary_nat = sum(
            1 for d in active_decisions
            if ground_truth_by_customer[d.customer_id].natural_conversion
        )
        ineffective_unrec = sum(
            1 for d in active_decisions
            if not ground_truth_by_customer[d.customer_id].recoverable and not ground_truth_by_customer[d.customer_id].natural_conversion
        )

        n_active = len(active_decisions)
        targeted_rec_rate = (targeted_rec / n_active) if n_active > 0 else 0.0
        unnecessary_nat_rate = (unnecessary_nat / n_active) if n_active > 0 else 0.0
        ineffective_unrec_rate = (ineffective_unrec / n_active) if n_active > 0 else 0.0

        # NO_ACTION classification
        no_act_nat = sum(
            1 for d in no_action_decisions
            if ground_truth_by_customer[d.customer_id].natural_conversion
        )
        no_act_unrec = sum(
            1 for d in no_action_decisions
            if not ground_truth_by_customer[d.customer_id].natural_conversion and not ground_truth_by_customer[d.customer_id].recoverable
        )
        no_act_rec_missed = sum(
            1 for d in no_action_decisions
            if not ground_truth_by_customer[d.customer_id].natural_conversion and ground_truth_by_customer[d.customer_id].recoverable
        )

        n_no_action = len(no_action_decisions)
        no_act_safe_avoidance_rate = ((no_act_nat + no_act_unrec) / n_no_action) if n_no_action > 0 else 1.0
        no_act_missed_opp_rate = (no_act_rec_missed / n_no_action) if n_no_action > 0 else 0.0

        # Independent Safety Policy Compliance Verification
        diag_map = {d.customer_id: d for d in treatment_diagnoses}
        interv_eval_res = InterventionEvaluator.evaluate_decisions(
            decisions=treatment_decisions,
            diagnoses_map=diag_map,
            feature_records_map=treatment_feature_records,
        )

        interv_summary = InterventionAppropriatenessSummary(
            active_interventions_count=n_active,
            targeted_recoverable_count=targeted_rec,
            targeted_recoverable_rate=round(targeted_rec_rate, 4),
            unnecessary_on_natural_count=unnecessary_nat,
            unnecessary_on_natural_rate=round(unnecessary_nat_rate, 4),
            ineffective_on_unrecoverable_count=ineffective_unrec,
            ineffective_on_unrecoverable_rate=round(ineffective_unrec_rate, 4),
            safety_policy_compliance_rate=interv_eval_res["safety_policy_compliance_rate"],
            evidence_action_consistency_rate=interv_eval_res["evidence_action_consistency_rate"],
            no_action_count=n_no_action,
            no_action_rate=round(n_no_action / self.paired_units, 4) if self.paired_units > 0 else 0.0,
            no_action_on_natural_count=no_act_nat,
            no_action_on_non_recoverable_count=no_act_unrec,
            no_action_on_recoverable_missed_count=no_act_rec_missed,
            no_action_safe_avoidance_rate=round(no_act_safe_avoidance_rate, 4),
            no_action_missed_opportunity_rate=round(no_act_missed_opp_rate, 4),
        )

        # 6. Compute Decision Funnel (Case-Insensitive Actionability Alignment)
        diagnosable_pop = sum(
            1 for d in treatment_decisions
            if d.diagnosis_actionability.upper() in {"CANDIDATE"}
        )
        eligible_pop = sum(
            1 for d in treatment_decisions
            if d.eligibility_status == "ELIGIBLE"
        )

        funnel_summary = DecisionFunnelSummary(
            total_population=self.paired_units,
            at_risk_population=interv_eval_res["at_risk_population"],
            diagnosable_population=diagnosable_pop,
            eligible_population=eligible_pop,
            no_action_count=interv_eval_res["no_action_count"],
            no_action_rate=interv_eval_res["no_action_rate"],
            human_review_count=interv_eval_res["human_review_count"],
            human_review_rate=interv_eval_res["human_review_rate"],
            automated_intervention_count=interv_eval_res["automated_intervention_count"],
            automated_intervention_rate=interv_eval_res["automated_intervention_rate"],
            per_action_distribution=interv_eval_res["per_action_distribution"],
        )

        safety_summary = SafetyGovernanceSummary(
            stop_rate=interv_eval_res["no_action_rate"],
            escalation_rate=interv_eval_res["human_review_rate"],
            blocked_ineligible_rate=round(1.0 - (eligible_pop / self.paired_units), 4) if self.paired_units > 0 else 0.0,
            unnecessary_intervention_rate=round(unnecessary_nat_rate, 4),
            execution_failure_rate=round(failed_cases / self.paired_units, 4) if self.paired_units > 0 else 0.0,
            retryable_failure_count=self.exception_ledger.get_summary()["retryable_count"],
            terminal_failure_count=self.exception_ledger.get_summary()["terminal_count"],
        )

        # 7. Comparative Economic Accounting
        ctrl_conv_rate = (control_conversions_count / self.paired_units) if self.paired_units > 0 else 0.0
        treat_conv_rate = (treatment_total_conversions_count / self.paired_units) if self.paired_units > 0 else 0.0

        conv_lift_pts = round((treat_conv_rate - ctrl_conv_rate) * 100.0, 2)
        rel_lift_pct = round(((treat_conv_rate - ctrl_conv_rate) / ctrl_conv_rate) * 100.0, 2) if ctrl_conv_rate > 0 else 0.0

        inc_net_revenue = round(treatment_total_net_rev_sum - control_net_revenue_sum, 2)
        rec_capture_rate = round((treatment_genuine_incremental_revenue_sum / total_max_recoverable_revenue) * 100.0, 2) if total_max_recoverable_revenue > 0 else 0.0
        roi = round((inc_net_revenue / treatment_cost_sum), 2) if treatment_cost_sum > 0 else 0.0

        economics = ComparativeEconomics(
            paired_experimental_units=self.paired_units,
            control_evaluations=self.paired_units,
            control_conversions=control_conversions_count,
            control_conversion_rate=round(ctrl_conv_rate, 4),
            control_gross_revenue=round(control_gross_revenue_sum, 2),
            control_net_revenue=round(control_net_revenue_sum, 2),
            control_revenue_at_risk=round(control_risk_sum, 2),
            treatment_evaluations=self.paired_units,
            treatment_total_conversions=treatment_total_conversions_count,
            treatment_total_conversion_rate=round(treat_conv_rate, 4),
            treatment_natural_conversions=treatment_natural_conversions_count,
            treatment_genuine_incremental_recoveries=treatment_genuine_incremental_recoveries_count,
            treatment_observed_unrecoverable_conversions=treatment_observed_unrecoverable_conversions_count,
            treatment_total_gross_revenue=round(treatment_gross_obs_sum, 2),
            treatment_attributable_recovery_revenue=round(treatment_attr_rev_sum, 2),
            treatment_intervention_cost=round(treatment_cost_sum, 2),
            treatment_net_recovered_revenue=round(treatment_net_rec_rev_sum, 2),
            treatment_total_net_revenue=round(treatment_total_net_rev_sum, 2),
            treatment_genuine_incremental_revenue=round(treatment_genuine_incremental_revenue_sum, 2),
            treatment_expected_recovery_value=round(treatment_ev_sum, 2),
            conversion_lift_points=conv_lift_pts,
            conversion_relative_lift_pct=rel_lift_pct,
            incremental_net_revenue=inc_net_revenue,
            maximum_recoverable_revenue=round(total_max_recoverable_revenue, 2),
            recoverable_capture_rate_pct=rec_capture_rate,
            recovery_roi=roi,
        )

        # 8. High-Resolution Throughput Measurement
        total_arm_evals = self.paired_units * 2
        avg_lat = float(sum(case_latencies_ms) / len(case_latencies_ms)) if case_latencies_ms else 0.0
        sorted_lats = sorted(case_latencies_ms)
        p95_idx = int(len(sorted_lats) * 0.95)
        p95_lat = float(sorted_lats[p95_idx]) if sorted_lats else 0.0

        total_events_processed_count = initial_journey_events_count + post_treatment_events_count
        paired_units_per_sec = round(self.paired_units / elapsed_sec, 2) if elapsed_sec > 0 else 0.0
        total_evals_per_sec = round(total_arm_evals / elapsed_sec, 2) if elapsed_sec > 0 else 0.0
        events_per_sec = round(total_events_processed_count / elapsed_sec, 2) if elapsed_sec > 0 else 0.0
        initial_events_per_sec = round(initial_journey_events_count / elapsed_sec, 2) if elapsed_sec > 0 else 0.0

        throughput = ThroughputSummary(
            start_time=start_wall_time,
            end_time=end_wall_time,
            elapsed_seconds=elapsed_sec,
            paired_experimental_units=self.paired_units,
            control_arm_evaluations=self.paired_units,
            treatment_arm_evaluations=self.paired_units,
            total_arm_evaluations=total_arm_evals,
            initial_journey_events=initial_journey_events_count,
            post_treatment_events=post_treatment_events_count,
            events_processed=total_events_processed_count,
            paired_units_per_second=paired_units_per_sec,
            total_evaluations_per_second=total_evals_per_sec,
            events_per_second=events_per_sec,
            initial_journey_events_per_second=initial_events_per_sec,
            average_case_latency_ms=round(avg_lat, 2),
            p95_case_latency_ms=round(p95_lat, 2),
        )

        # 9. Multi-Identity Accounting & Operational Reconciliation
        # Identity 1: Treatment Total Net Revenue = Total Gross - Total Cost
        fin_id1 = abs((treatment_gross_obs_sum - treatment_cost_sum) - treatment_total_net_rev_sum) < 0.01
        # Identity 2: Treatment Net Recovered Revenue = Attributable Recovery Revenue - Total Cost
        fin_id2 = abs((treatment_attr_rev_sum - treatment_cost_sum) - treatment_net_rec_rev_sum) < 0.01
        # Identity 3: Net Revenue Delta vs Control = Treatment Total Net Revenue - Control Net Revenue
        fin_id3 = abs((treatment_total_net_rev_sum - control_net_revenue_sum) - inc_net_revenue) < 0.01
        # Identity 4: Conversion Composition
        conv_comp = (
            treatment_total_conversions_count ==
            treatment_natural_conversions_count +
            treatment_genuine_incremental_recoveries_count +
            treatment_observed_unrecoverable_conversions_count
        )

        exc_reconciles = ExceptionLedger.verify_reconciliation(
            total_cases=self.paired_units,
            successful_cases=successful_cases,
            stopped_cases=stopped_cases,
            escalated_cases=escalated_cases,
            failed_cases=failed_cases,
            unresolved_cases=unresolved_cases,
        )

        funnel_valid = (eligible_pop <= diagnosable_pop)

        all_reconciliation_passed = (fin_id1 and fin_id2 and fin_id3 and conv_comp and exc_reconciles and funnel_valid)

        metadata = ExperimentMetadata(
            experiment_id=f"exp_phase_b_{self.seed}_{self.paired_units}",
            seed=self.seed,
            paired_experimental_units=self.paired_units,
            control_evaluations=self.paired_units,
            treatment_evaluations=self.paired_units,
            total_arm_evaluations=total_arm_evals,
            simulator_version="v2.0.0",
            policy_version="Phase 5 Bounded EV v1.0",
            assumption_version="Recovery Probability v1.0",
            risk_model_version="RandomForest-v1.0.0",
            python_version=platform.python_version(),
            timestamp=start_wall_time,
            git_revision=None,
        )

        outcome_dist = dict(Counter(r.outcome.value for r in treatment_outcome_records))
        attr_dist = dict(Counter(r.attribution_status.value for r in treatment_outcome_records))

        return PhaseBEvaluationResult(
            metadata=metadata,
            economics=economics,
            diagnosis_accuracy=diag_summary,
            intervention_appropriateness=interv_summary,
            decision_funnel=funnel_summary,
            safety_governance=safety_summary,
            throughput=throughput,
            outcome_distribution=outcome_dist,
            attribution_distribution=attr_dist,
            exception_summary=self.exception_ledger.get_summary(),
            reconciliation_passed=all_reconciliation_passed,
        )
