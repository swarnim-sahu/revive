/**
 * TypeScript Interfaces for REVIVE Dashboard API Responses
 */

// ---------------------------------------------------------------------------
// 1. Operational Batch Models
// ---------------------------------------------------------------------------

export interface DatasetSummary {
  customers_evaluated: number;
  events_processed: number;
  customers_with_payment_failures: number;
}

export interface RiskSummary {
  critical: number;
  high: number;
  medium: number;
  low: number;
  average_risk_score: number;
  average_revenue_at_risk: number;
}

export interface DiagnosisSummary {
  payment_friction: number;
  actionable: number;
  non_actionable: number;
}

export interface PolicySummary {
  eligible_customers: number;
  ineligible_customers: number;
  payment_recovery_actions: number;
  reminder_actions: number;
}

export interface ExpectedRecoverySummary {
  total_revenue_at_risk: number;
  total_expected_recovery: number;
  expected_recovery_rate_pct: number;
}

export interface MeasuredRecoverySummary {
  gross_observed_revenue: number;
  attributable_revenue: number;
  intervention_cost: number;
  net_recovered_revenue: number;
  measured_recovery_rate_pct: number;
  recovered_customers: number;
}

export interface OutcomesSummary {
  distribution: Record<string, number>;
}

export interface AttributionSummary {
  distribution: Record<string, number>;
}

export interface ExecutionSummary {
  candidates: number;
  successful: number;
  failed: number;
  blocked: number;
  duplicates_prevented: number;
}

export interface DashboardSummaryResponse {
  provenance: string;
  dataset: DatasetSummary;
  risk: RiskSummary;
  diagnosis: DiagnosisSummary;
  policy: PolicySummary;
  expected_recovery: ExpectedRecoverySummary;
  measured_recovery: MeasuredRecoverySummary;
  outcomes: OutcomesSummary;
  attribution: AttributionSummary;
  execution: ExecutionSummary;
}

export interface CandidateActionScore {
  action: string;
  expected_value: number;
  recovery_probability: number;
  direct_cost: number;
  eligible: boolean;
  selected: boolean;
  rejection_reason?: string | null;
}

export interface CustomerEvidenceRecord {
  customer_id: string;
  risk_score: number;
  risk_tier: string;
  revenue_at_risk: number;
  plan?: string;
  diagnosis: string;
  diagnosis_confidence: number;
  actionability?: string;
  ai_status: string;
  ai_confidence: number;
  fallback_used: boolean;
  eligibility_status: string;
  policy_version?: string;
  assumption_version?: string;
  selected_action: string;
  expected_value: number;
  decision_reason: string;
  candidate_actions?: CandidateActionScore[];
  execution_status: string;
  failure_reason?: string | null;
  outcome?: string | null;
  outcome_confidence?: number | null;
  attribution_status?: string | null;
  attributable_revenue?: number | null;
  net_recovered_revenue?: number | null;
  payment_reference?: string | null;
  evidence_event_ids: string[];
  risk_signals?: Record<string, boolean>;
}

// ---------------------------------------------------------------------------
// 2. Phase B Benchmark Models
// ---------------------------------------------------------------------------

export interface BenchmarkMetadata {
  experiment_id: string;
  seed: number;
  paired_experimental_units: number;
  control_evaluations: number;
  treatment_evaluations: number;
  total_arm_evaluations: number;
  simulator_version: string;
  policy_version: string;
  assumption_version: string;
  risk_model_version: string;
  python_version: string;
  timestamp: string;
  git_revision?: string | null;
}

export interface BenchmarkEconomics {
  paired_experimental_units: number;
  control_evaluations: number;
  control_conversions: number;
  control_conversion_rate: number;
  control_gross_revenue: number;
  control_net_revenue: number;
  control_revenue_at_risk: number;
  treatment_evaluations: number;
  treatment_total_conversions: number;
  treatment_total_conversion_rate: number;
  treatment_natural_conversions: number;
  treatment_genuine_incremental_recoveries: number;
  treatment_observed_unrecoverable_conversions: number;
  treatment_no_treatment_conversions: number;
  treatment_total_gross_revenue: number;
  gross_revenue_delta_vs_control: number;
  treatment_attributable_recovery_revenue: number;
  treatment_intervention_cost: number;
  treatment_net_recovered_revenue: number;
  treatment_total_net_revenue: number;
  treatment_genuine_incremental_revenue: number;
  treatment_expected_recovery_value: number;
  conversion_lift_points: number;
  conversion_relative_lift_pct: number;
  incremental_net_revenue: number;
  maximum_recoverable_revenue: number;
  recoverable_capture_rate_pct: number;
  recovery_roi: number;
}

export interface BenchmarkDiagnosisAccuracy {
  overall_accuracy: number;
  macro_f1: number;
  macro_precision: number;
  macro_recall: number;
}

export interface BenchmarkInterventionAppropriateness {
  active_interventions_count: number;
  targeted_recoverable_count: number;
  targeted_recoverable_rate: number;
  unnecessary_on_natural_count: number;
  unnecessary_on_natural_rate: number;
  ineffective_on_unrecoverable_count: number;
  ineffective_on_unrecoverable_rate: number;
  safety_policy_compliance_rate: number;
  evidence_action_consistency_rate: number;
  no_action_count: number;
  no_action_rate: number;
  no_action_on_natural_count: number;
  no_action_on_non_recoverable_count: number;
  no_action_on_recoverable_missed_count: number;
  no_action_safe_avoidance_rate: number;
  no_action_missed_opportunity_rate: number;
}

export interface BenchmarkActionStat {
  count: number;
  rate: number;
}

export interface BenchmarkDecisionFunnel {
  total_population: number;
  at_risk_population: number;
  diagnosable_population: number;
  eligible_population: number;
  no_action_count: number;
  no_action_rate: number;
  human_review_count: number;
  human_review_rate: number;
  automated_intervention_count: number;
  automated_intervention_rate: number;
  per_action_distribution: Record<string, BenchmarkActionStat>;
}

export interface BenchmarkSafetyGovernance {
  stop_rate: number;
  escalation_rate: number;
  blocked_ineligible_rate: number;
  unnecessary_intervention_rate: number;
  execution_failure_rate: number;
  retryable_failure_count: number;
  terminal_failure_count: number;
}

export interface BenchmarkThroughput {
  start_time: string;
  end_time: string;
  elapsed_seconds: number;
  paired_experimental_units: number;
  control_arm_evaluations: number;
  treatment_arm_evaluations: number;
  total_arm_evaluations: number;
  initial_journey_events: number;
  post_treatment_events: number;
  events_processed: number;
  paired_units_per_second: number;
  total_evaluations_per_second: number;
  events_per_second: number;
  initial_journey_events_per_second: number;
  average_case_latency_ms: number;
  p95_case_latency_ms: number;
}

export interface BenchmarkData {
  available: boolean;
  diagnostic_message?: string | null;
  provenance: string;
  source_artifact: string;
  metadata?: BenchmarkMetadata | null;
  economics?: BenchmarkEconomics | null;
  diagnosis_accuracy?: BenchmarkDiagnosisAccuracy | null;
  intervention_appropriateness?: BenchmarkInterventionAppropriateness | null;
  decision_funnel?: BenchmarkDecisionFunnel | null;
  safety_governance?: BenchmarkSafetyGovernance | null;
  throughput?: BenchmarkThroughput | null;
  exception_summary?: Record<string, unknown> | null;
  reconciliation_passed?: boolean | null;
}

// ---------------------------------------------------------------------------
// 3. Phase A Real Razorpay Test Mode Proof Models
// ---------------------------------------------------------------------------

export interface RazorpayProofData {
  proof_type: string;
  status: string;
  environment: string;
  payment_link_id: string;
  payment_id: string;
  webhook_event_id: string;
  reference_id: string;
  correlated_customer_id: string;
  plan_id: string;
  plan_name: string;
  plan_price: number;
  currency: string;
  outcome: string;
  outcome_confidence: number;
  attribution_status: string;
  attributable_revenue: number;
  intervention_cost: number;
  net_recovered_revenue: number;
  duplicate_delivery_status: string;
  proof_timestamp: string;
  signature_verification: string;
  disclosure: string;
  provenance: string;
}

// ---------------------------------------------------------------------------
// 4. 9-Stage Chronological Audit Timeline Models
// ---------------------------------------------------------------------------

export interface AuditStage {
  stage_index: number;
  stage_name: string;
  status: string;
  timestamp?: string | null;
  summary: string;
  details: Record<string, unknown>;
}

export interface AuditTimelineData {
  customer_id: string;
  provenance: string;
  total_stages: number;
  completed_stages: number;
  final_status: string;
  stages: AuditStage[];
}

// ---------------------------------------------------------------------------
// 5. Exceptions & Governed Non-Actions Models
// ---------------------------------------------------------------------------

export interface ExceptionItem {
  category: string;
  customer_id?: string | null;
  decision: string;
  reason: string;
  policy_action: string;
  financial_impact: number;
  retryable: boolean;
}

export interface ExceptionCenterData {
  provenance: string;
  total_exceptions: number;
  retryable_count: number;
  terminal_count: number;
  human_escalation_count: number;
  total_financial_impact: number;
  by_stage: Record<string, number>;
  by_failure_type: Record<string, number>;
  sample_exceptions: ExceptionItem[];
}

// ---------------------------------------------------------------------------
// 6. Controlled Failure Demonstration Models
// ---------------------------------------------------------------------------

export interface FailureScenarioStep {
  step_number: number;
  step_name: string;
  status: string;
  description: string;
  state_snapshot: Record<string, unknown>;
}

export interface FailureScenarioData {
  scenario_id: string;
  title: string;
  category: string;
  label: string;
  customer_id: string;
  action: string;
  failure_reason: string;
  failure_type: string;
  retryable: boolean;
  attempt_count: number;
  max_retries: number;
  safe_action: string;
  final_state: string;
  financial_exposure: number;
  steps: FailureScenarioStep[];
}
