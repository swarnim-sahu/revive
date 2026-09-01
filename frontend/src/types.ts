/**
 * TypeScript Interfaces for REVIVE Dashboard API Responses
 */

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

export interface CustomerEvidenceRecord {
  customer_id: string;
  risk_score: number;
  risk_tier: string;
  revenue_at_risk: number;
  diagnosis: string;
  diagnosis_confidence: number;
  ai_status: string;
  ai_confidence: number;
  fallback_used: boolean;
  eligibility_status: string;
  selected_action: string;
  expected_value: number;
  decision_reason: string;
  execution_status: string;
  failure_reason?: string | null;
  outcome?: string | null;
  outcome_confidence?: number | null;
  attribution_status?: string | null;
  attributable_revenue?: number | null;
  net_recovered_revenue?: number | null;
  payment_reference?: string | null;
  evidence_event_ids: string[];
}
