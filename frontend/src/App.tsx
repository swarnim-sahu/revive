import { useEffect, useState, useMemo } from "react";
import { fetchSummary, fetchCustomers } from "./api";
import { CustomerDrawer } from "./CustomerDrawer";
import { formatINR } from "./utils";
import type { DashboardSummaryResponse, CustomerEvidenceRecord } from "./types";
import "./App.css";

export function App() {
  const [summary, setSummary] = useState<DashboardSummaryResponse | null>(null);
  const [customers, setCustomers] = useState<CustomerEvidenceRecord[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedCustomer, setSelectedCustomer] = useState<CustomerEvidenceRecord | null>(null);
  const [reloadTrigger, setReloadTrigger] = useState<number>(0);

  // Table Filters
  const [searchTerm, setSearchTerm] = useState<string>("");
  const [riskFilter, setRiskFilter] = useState<string>("ALL");
  const [diagnosisFilter, setDiagnosisFilter] = useState<string>("ALL");
  const [execFilter, setExecFilter] = useState<string>("ALL");
  const [outcomeFilter, setOutcomeFilter] = useState<string>("ALL");

  useEffect(() => {
    let active = true;
    Promise.all([fetchSummary(), fetchCustomers()])
      .then(([sumData, custData]) => {
        if (active) {
          setSummary(sumData);
          setCustomers(custData);
          setError(null);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (active) {
          if (err instanceof Error) {
            setError(err.message);
          } else {
            setError("An unknown error occurred while connecting to REVIVE API.");
          }
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [reloadTrigger]);

  const handleRetry = () => {
    setLoading(true);
    setReloadTrigger((prev) => prev + 1);
  };

  // Filtered and Sorted Customer Queue
  const filteredCustomers = useMemo(() => {
    let list = [...customers];

    if (searchTerm.trim()) {
      const term = searchTerm.toLowerCase();
      list = list.filter((c) => c.customer_id.toLowerCase().includes(term));
    }

    if (riskFilter !== "ALL") {
      list = list.filter((c) => c.risk_tier.toUpperCase() === riskFilter);
    }

    if (diagnosisFilter !== "ALL") {
      list = list.filter((c) => c.diagnosis === diagnosisFilter);
    }

    if (execFilter !== "ALL") {
      list = list.filter((c) => c.execution_status.toUpperCase() === execFilter);
    }

    if (outcomeFilter !== "ALL") {
      list = list.filter((c) => (c.outcome || "PENDING").toUpperCase() === outcomeFilter);
    }

    // Default sort: High risk score descending
    list.sort((a, b) => b.risk_score - a.risk_score);

    return list;
  }, [customers, searchTerm, riskFilter, diagnosisFilter, execFilter, outcomeFilter]);

  if (loading) {
    return (
      <div className="center-box">
        <div className="spinner"></div>
        <div className="text-secondary font-mono">LOADING REVIVE COMMAND CENTER BENCHMARK...</div>
      </div>
    );
  }

  if (error || !summary) {
    return (
      <div className="center-box">
        <div className="error-card">
          <div className="error-title">REVIVE API UNREACHABLE</div>
          <div className="text-secondary text-sm">{error || "Failed to load benchmark data."}</div>
          <button type="button" className="retry-btn" onClick={handleRetry}>
            RETRY CONNECTION
          </button>
        </div>
      </div>
    );
  }

  const { dataset, risk, diagnosis, policy, expected_recovery, measured_recovery, outcomes, attribution, execution } = summary;

  return (
    <div className="app-container">
      {/* 1. HEADER */}
      <header className="header-bar">
        <div>
          <div className="brand-title">
            REVIVE <span className="brand-badge">PROD API</span>
          </div>
          <div className="header-subtitle">AI REVENUE RECOVERY COMMAND CENTER</div>
        </div>
        <div className="header-status">
          <div className="status-dot"></div>
          <div>
            <div className="status-text">BENCHMARK LIVE</div>
            <div className="benchmark-info">100-Customer Evaluation (Seed 42)</div>
          </div>
        </div>
      </header>

      {/* 2. HERO KPI CARDS */}
      <section className="kpi-grid">
        <div className="kpi-card risk">
          <div className="kpi-title">REVENUE AT RISK</div>
          <div className="kpi-value">{formatINR(expected_recovery.total_revenue_at_risk)}</div>
          <div className="kpi-subtext text-secondary">{risk.high + risk.critical} High/Critical Tiers</div>
        </div>

        <div className="kpi-card expected">
          <div className="kpi-title">EXPECTED RECOVERY</div>
          <div className="kpi-value">{formatINR(expected_recovery.total_expected_recovery)}</div>
          <div className="kpi-subtext text-purple">{expected_recovery.expected_recovery_rate_pct.toFixed(2)}% Expected Rate</div>
        </div>

        <div className="kpi-card measured">
          <div className="kpi-title">MEASURED RECOVERY</div>
          <div className="kpi-value">{formatINR(measured_recovery.net_recovered_revenue)}</div>
          <div className="kpi-subtext text-success">{measured_recovery.measured_recovery_rate_pct.toFixed(2)}% Net Realized Rate</div>
        </div>

        <div className="kpi-card customers">
          <div className="kpi-title">RECOVERED CUSTOMERS</div>
          <div className="kpi-value">{measured_recovery.recovered_customers}</div>
          <div className="kpi-subtext text-cyan">Out of {execution.successful} Executions</div>
        </div>
      </section>

      {/* 3. RECOVERY PIPELINE VISUALIZATION */}
      <section className="pipeline-card">
        <div className="section-title">AUTONOMOUS RECOVERY PIPELINE</div>
        <div className="pipeline-flex">
          <div className="pipeline-step">
            <div className="pipeline-step-name">DETECT</div>
            <div className="pipeline-step-val">{dataset.customers_evaluated}</div>
            <div className="pipeline-step-desc">Customers Evaluated</div>
          </div>
          <div className="pipeline-arrow">→</div>

          <div className="pipeline-step">
            <div className="pipeline-step-name">DIAGNOSE</div>
            <div className="pipeline-step-val">{diagnosis.payment_friction}</div>
            <div className="pipeline-step-desc">Payment Friction</div>
          </div>
          <div className="pipeline-arrow">→</div>

          <div className="pipeline-step">
            <div className="pipeline-step-name">DECIDE</div>
            <div className="pipeline-step-val">{policy.payment_recovery_actions}</div>
            <div className="pipeline-step-desc">Recovery Actions</div>
          </div>
          <div className="pipeline-arrow">→</div>

          <div className="pipeline-step">
            <div className="pipeline-step-name">EXECUTE</div>
            <div className="pipeline-step-val">{execution.successful}</div>
            <div className="pipeline-step-desc">Razorpay Dispatches</div>
          </div>
          <div className="pipeline-arrow">→</div>

          <div className="pipeline-step">
            <div className="pipeline-step-name">MEASURE</div>
            <div className="pipeline-step-val">Phase 7</div>
            <div className="pipeline-step-desc">Attribution Engine</div>
          </div>
          <div className="pipeline-arrow">→</div>

          <div className="pipeline-step">
            <div className="pipeline-step-name">RECOVER</div>
            <div className="pipeline-step-val text-success">{measured_recovery.recovered_customers}</div>
            <div className="pipeline-step-desc">Recovered ({formatINR(measured_recovery.net_recovered_revenue)})</div>
          </div>
        </div>
      </section>

      {/* 4. EXPECTED VS MEASURED & RISK/DIAGNOSIS */}
      <div className="grid-2col">
        {/* EXPECTED VS MEASURED RECOVERY */}
        <div className="card">
          <div className="section-title">EXPECTED vs MEASURED RECOVERY</div>
          <div className="comparison-grid">
            <div className="comp-box expected">
              <div className="comp-title">EXPECTED (POLICY EV)</div>
              <div className="comp-amount">{formatINR(expected_recovery.total_expected_recovery)}</div>
              <div className="comp-rate text-purple">{expected_recovery.expected_recovery_rate_pct.toFixed(2)}% EV Rate</div>
            </div>
            <div className="comp-box measured">
              <div className="comp-title">MEASURED (PHASE 7 ATTRIBUTED)</div>
              <div className="comp-amount">{formatINR(measured_recovery.net_recovered_revenue)}</div>
              <div className="comp-rate text-success">{measured_recovery.measured_recovery_rate_pct.toFixed(2)}% Net Rate</div>
            </div>
          </div>

          <div className="breakdown-list">
            <div className="breakdown-item">
              <span className="breakdown-label">Gross Observed Revenue:</span>
              <span className="breakdown-val">{formatINR(measured_recovery.gross_observed_revenue)}</span>
            </div>
            <div className="breakdown-item">
              <span className="breakdown-label">Attributable Revenue:</span>
              <span className="breakdown-val">{formatINR(measured_recovery.attributable_revenue)}</span>
            </div>
            <div className="breakdown-item">
              <span className="breakdown-label">Direct Execution Cost:</span>
              <span className="breakdown-val">{formatINR(measured_recovery.intervention_cost)}</span>
            </div>
            <div className="breakdown-item">
              <span className="breakdown-label">Net Recovered Revenue:</span>
              <span className="breakdown-val text-success">{formatINR(measured_recovery.net_recovered_revenue)}</span>
            </div>
          </div>

          <div className="note-box">
            Expected recovery represents Phase 5 policy predictions before execution. Measured recovery represents post-intervention evidence attributed through Phase 7 OutcomeEngine.
          </div>
        </div>

        {/* RISK & DIAGNOSIS BREAKDOWN */}
        <div className="card">
          <div className="section-title">RISK & DIAGNOSIS TAXONOMY</div>
          <div className="metrics-grid-2 mb-2">
            <div className="stat-row">
              <span className="stat-label">Critical Tier:</span>
              <span className="stat-val text-rose">{risk.critical}</span>
            </div>
            <div className="stat-row">
              <span className="stat-label">High Tier:</span>
              <span className="stat-val text-amber">{risk.high}</span>
            </div>
            <div className="stat-row">
              <span className="stat-label">Medium Tier:</span>
              <span className="stat-val text-cyan">{risk.medium}</span>
            </div>
            <div className="stat-row">
              <span className="stat-label">Low Tier:</span>
              <span className="stat-val text-success">{risk.low}</span>
            </div>
          </div>

          <div className="breakdown-list">
            <div className="breakdown-item">
              <span className="breakdown-label">Payment Friction Diagnoses:</span>
              <span className="breakdown-val text-cyan">{diagnosis.payment_friction}</span>
            </div>
            <div className="breakdown-item">
              <span className="breakdown-label">Actionable Candidates:</span>
              <span className="breakdown-val">{diagnosis.actionable}</span>
            </div>
            <div className="breakdown-item">
              <span className="breakdown-label">Non-Actionable Cases:</span>
              <span className="breakdown-val">{diagnosis.non_actionable}</span>
            </div>
            <div className="breakdown-item">
              <span className="breakdown-label">Avg Risk Score / Rev:</span>
              <span className="breakdown-val">
                {(risk.average_risk_score * 100).toFixed(1)}% / {formatINR(risk.average_revenue_at_risk)}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* 5. OUTCOMES, ATTRIBUTION, & GOVERNANCE */}
      <div className="grid-3col">
        {/* OUTCOME DISTRIBUTION */}
        <div className="card">
          <div className="section-title">OUTCOME DISTRIBUTION</div>
          {Object.entries(outcomes.distribution).map(([key, count]) => (
            <div key={key} className="stat-row">
              <span className="stat-label">{key}:</span>
              <span className="stat-val">{count}</span>
            </div>
          ))}
        </div>

        {/* ATTRIBUTION DISTRIBUTION */}
        <div className="card">
          <div className="section-title">ATTRIBUTION DISTRIBUTION</div>
          {Object.entries(attribution.distribution).map(([key, count]) => (
            <div key={key} className="stat-row">
              <span className="stat-label">{key}:</span>
              <span className="stat-val">{count}</span>
            </div>
          ))}
        </div>

        {/* EXECUTION & GOVERNANCE */}
        <div className="card">
          <div className="section-title">EXECUTION & GOVERNANCE</div>
          <div className="stat-row">
            <span className="stat-label">Eligible Customers:</span>
            <span className="stat-val text-success">{policy.eligible_customers}</span>
          </div>
          <div className="stat-row">
            <span className="stat-label">Ineligible Customers:</span>
            <span className="stat-val text-muted">{policy.ineligible_customers}</span>
          </div>
          <div className="stat-row">
            <span className="stat-label">Execution Candidates:</span>
            <span className="stat-val">{execution.candidates}</span>
          </div>
          <div className="stat-row">
            <span className="stat-label">Successful Dispatches:</span>
            <span className="stat-val text-success">{execution.successful}</span>
          </div>
          <div className="stat-row">
            <span className="stat-label">Duplicates Prevented:</span>
            <span className="stat-val text-cyan">{execution.duplicates_prevented}</span>
          </div>
        </div>
      </div>

      {/* 6. CUSTOMER RECOVERY QUEUE TABLE */}
      <section className="table-card">
        <div className="table-header-flex">
          <div className="section-title">
            CUSTOMER RECOVERY QUEUE <span className="text-secondary text-sm">({filteredCustomers.length} records)</span>
          </div>

          <div className="filter-bar">
            <input
              type="text"
              className="search-input"
              placeholder="Search Customer ID..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />

            <select className="filter-select" value={riskFilter} onChange={(e) => setRiskFilter(e.target.value)}>
              <option value="ALL">All Risk Tiers</option>
              <option value="CRITICAL">Critical</option>
              <option value="HIGH">High</option>
              <option value="MEDIUM">Medium</option>
              <option value="LOW">Low</option>
            </select>

            <select className="filter-select" value={diagnosisFilter} onChange={(e) => setDiagnosisFilter(e.target.value)}>
              <option value="ALL">All Diagnoses</option>
              <option value="PAYMENT_FRICTION">Payment Friction</option>
              <option value="CHECKOUT_ABANDONMENT">Checkout Abandonment</option>
              <option value="TRIAL_EXPIRATION">Trial Expiration</option>
              <option value="ALREADY_CONVERTED">Already Converted</option>
            </select>

            <select className="filter-select" value={execFilter} onChange={(e) => setExecFilter(e.target.value)}>
              <option value="ALL">All Executions</option>
              <option value="EXECUTED">Executed</option>
              <option value="ESCALATED">Escalated</option>
              <option value="BLOCKED">Blocked</option>
            </select>

            <select className="filter-select" value={outcomeFilter} onChange={(e) => setOutcomeFilter(e.target.value)}>
              <option value="ALL">All Outcomes</option>
              <option value="RECOVERED">Recovered</option>
              <option value="NOT_RECOVERED">Not Recovered</option>
              <option value="ALREADY_CONVERTED">Already Converted</option>
              <option value="NO_OBSERVABLE_OUTCOME">No Observable Outcome</option>
            </select>
          </div>
        </div>

        <div className="table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th>Customer ID</th>
                <th>Risk Tier</th>
                <th>Diagnosis</th>
                <th>AI Status</th>
                <th>Selected Action</th>
                <th>Execution</th>
                <th>Outcome</th>
                <th>Net Recovered</th>
              </tr>
            </thead>
            <tbody>
              {filteredCustomers.length === 0 ? (
                <tr>
                  <td colSpan={8} className="text-center text-muted" style={{ padding: "32px" }}>
                    No customer evidence records match the selected filters.
                  </td>
                </tr>
              ) : (
                filteredCustomers.map((cust) => (
                  <tr key={cust.customer_id} className="table-row" onClick={() => setSelectedCustomer(cust)}>
                    <td className="customer-id-cell">{cust.customer_id}</td>
                    <td>
                      <span className={`badge tier-${cust.risk_tier.toLowerCase()}`}>{cust.risk_tier}</span>
                    </td>
                    <td>{cust.diagnosis}</td>
                    <td>
                      <span className={`badge status-${cust.ai_status.toLowerCase()}`}>{cust.ai_status}</span>
                    </td>
                    <td className="font-highlight">{cust.selected_action}</td>
                    <td>
                      <span className={`badge exec-${cust.execution_status.toLowerCase()}`}>{cust.execution_status}</span>
                    </td>
                    <td>
                      <span className={`badge outcome-${(cust.outcome || "unknown").toLowerCase()}`}>
                        {cust.outcome || "PENDING"}
                      </span>
                    </td>
                    <td className="font-mono font-bold">{formatINR(cust.net_recovered_revenue)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* 7. CUSTOMER DETAIL DRAWER */}
      <CustomerDrawer customer={selectedCustomer} onClose={() => setSelectedCustomer(null)} />
    </div>
  );
}

export default App;
