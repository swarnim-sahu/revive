import type {
  DashboardSummaryResponse,
  CustomerEvidenceRecord,
  BenchmarkData,
  RazorpayProofData,
  AuditTimelineData,
  ExceptionCenterData,
  FailureScenarioData,
  GeminiEvaluationData,
  CohortControls,
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

function buildQuery(controls?: CohortControls): string {
  if (!controls) return "";
  const params = new URLSearchParams();
  if (controls.seed !== undefined) params.set("seed", controls.seed.toString());
  if (controls.cohortSize !== undefined) {
    params.set("cohort_size", controls.cohortSize.toString());
    params.set("customers_count", controls.cohortSize.toString());
  }
  if (controls.snapshotHours !== undefined) params.set("snapshot_hours", controls.snapshotHours.toString());
  const str = params.toString();
  return str ? `?${str}` : "";
}

export async function fetchHealth(): Promise<{ status: string; service: string }> {
  const res = await fetch(`${API_BASE_URL}/health`);
  if (!res.ok) {
    throw new Error(`Health check failed with status ${res.status}`);
  }
  return res.json();
}

export async function fetchSummary(controls?: CohortControls): Promise<DashboardSummaryResponse> {
  const res = await fetch(`${API_BASE_URL}/api/dashboard/summary${buildQuery(controls)}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch dashboard summary (HTTP ${res.status})`);
  }
  return res.json();
}

export async function fetchCustomers(controls?: CohortControls): Promise<CustomerEvidenceRecord[]> {
  const res = await fetch(`${API_BASE_URL}/api/dashboard/customers${buildQuery(controls)}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch customers queue (HTTP ${res.status})`);
  }
  return res.json();
}

export async function fetchCustomer(customerId: string, controls?: CohortControls): Promise<CustomerEvidenceRecord> {
  const res = await fetch(`${API_BASE_URL}/api/dashboard/customers/${customerId}${buildQuery(controls)}`);
  if (!res.ok) {
    throw new Error(`Customer '${customerId}' not found (HTTP ${res.status})`);
  }
  return res.json();
}

export async function fetchBenchmark(): Promise<BenchmarkData> {
  const res = await fetch(`${API_BASE_URL}/api/dashboard/benchmark`);
  if (!res.ok) {
    throw new Error(`Failed to fetch Phase B benchmark (HTTP ${res.status})`);
  }
  return res.json();
}

export async function fetchRazorpayProof(): Promise<RazorpayProofData> {
  const res = await fetch(`${API_BASE_URL}/api/dashboard/razorpay-proof`);
  if (!res.ok) {
    throw new Error(`Failed to fetch Razorpay Test Mode proof (HTTP ${res.status})`);
  }
  return res.json();
}

export async function fetchCustomerAudit(customerId: string, controls?: CohortControls): Promise<AuditTimelineData> {
  const res = await fetch(`${API_BASE_URL}/api/dashboard/audit/${customerId}${buildQuery(controls)}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch audit timeline for '${customerId}' (HTTP ${res.status})`);
  }
  return res.json();
}

export async function fetchExceptions(controls?: CohortControls): Promise<ExceptionCenterData> {
  const res = await fetch(`${API_BASE_URL}/api/dashboard/exceptions${buildQuery(controls)}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch exceptions ledger (HTTP ${res.status})`);
  }
  return res.json();
}

export async function fetchFailureScenarios(): Promise<FailureScenarioData[]> {
  const res = await fetch(`${API_BASE_URL}/api/dashboard/failure-scenarios`);
  if (!res.ok) {
    throw new Error(`Failed to fetch failure scenarios (HTTP ${res.status})`);
  }
  return res.json();
}

export async function fetchGeminiEvaluation(): Promise<GeminiEvaluationData> {
  const res = await fetch(`${API_BASE_URL}/api/dashboard/gemini-evaluation`);
  if (!res.ok) {
    throw new Error(`Failed to fetch Phase D Gemini evaluation (HTTP ${res.status})`);
  }
  return res.json();
}
