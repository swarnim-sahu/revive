import type {
  DashboardSummaryResponse,
  CustomerEvidenceRecord,
  BenchmarkData,
  RazorpayProofData,
  AuditTimelineData,
  ExceptionCenterData,
  FailureScenarioData,
  GeminiEvaluationData,
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export async function fetchHealth(): Promise<{ status: string; service: string }> {
  const res = await fetch(`${API_BASE_URL}/health`);
  if (!res.ok) {
    throw new Error(`Health check failed with status ${res.status}`);
  }
  return res.json();
}

export async function fetchSummary(): Promise<DashboardSummaryResponse> {
  const res = await fetch(`${API_BASE_URL}/api/dashboard/summary`);
  if (!res.ok) {
    throw new Error(`Failed to fetch dashboard summary (HTTP ${res.status})`);
  }
  return res.json();
}

export async function fetchCustomers(): Promise<CustomerEvidenceRecord[]> {
  const res = await fetch(`${API_BASE_URL}/api/dashboard/customers`);
  if (!res.ok) {
    throw new Error(`Failed to fetch customers queue (HTTP ${res.status})`);
  }
  return res.json();
}

export async function fetchCustomer(customerId: string): Promise<CustomerEvidenceRecord> {
  const res = await fetch(`${API_BASE_URL}/api/dashboard/customers/${customerId}`);
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

export async function fetchCustomerAudit(customerId: string): Promise<AuditTimelineData> {
  const res = await fetch(`${API_BASE_URL}/api/dashboard/audit/${customerId}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch audit timeline for '${customerId}' (HTTP ${res.status})`);
  }
  return res.json();
}

export async function fetchExceptions(): Promise<ExceptionCenterData> {
  const res = await fetch(`${API_BASE_URL}/api/dashboard/exceptions`);
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
