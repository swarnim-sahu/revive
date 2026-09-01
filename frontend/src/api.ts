import type { DashboardSummaryResponse, CustomerEvidenceRecord } from "./types";

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
