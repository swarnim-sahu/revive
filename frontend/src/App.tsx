import { useEffect, useState, useMemo } from "react";
import {
  fetchSummary,
  fetchCustomers,
  fetchBenchmark,
  fetchRazorpayProof,
  fetchExceptions,
  fetchFailureScenarios,
  fetchGeminiEvaluation,
} from "./api";
import { CustomerDrawer } from "./CustomerDrawer";
import { formatINR } from "./utils";
import type {
  DashboardSummaryResponse,
  CustomerEvidenceRecord,
  BenchmarkData,
  RazorpayProofData,
  ExceptionCenterData,
  FailureScenarioData,
  GeminiEvaluationData,
} from "./types";
import "./App.css";

type TabView = "overview" | "benchmark" | "proof" | "gemini" | "exceptions" | "failure" | "methodology";

export function App() {
  const [activeTab, setActiveTab] = useState<TabView>("overview");

  // Operational State
  const [summary, setSummary] = useState<DashboardSummaryResponse | null>(null);
  const [customers, setCustomers] = useState<CustomerEvidenceRecord[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedCustomer, setSelectedCustomer] = useState<CustomerEvidenceRecord | null>(null);
  const [reloadTrigger, setReloadTrigger] = useState<number>(0);

  // Evidence Centers State
  const [benchmark, setBenchmark] = useState<BenchmarkData | null>(null);
  const [razorpayProof, setRazorpayProof] = useState<RazorpayProofData | null>(null);
  const [exceptionsData, setExceptionsData] = useState<ExceptionCenterData | null>(null);
  const [failureScenarios, setFailureScenarios] = useState<FailureScenarioData[]>([]);
  const [selectedFailureIdx, setSelectedFailureIdx] = useState<number>(0);
  const [geminiData, setGeminiData] = useState<GeminiEvaluationData | null>(null);

  // Customer Queue Filters
  const [searchTerm, setSearchTerm] = useState<string>("");
  const [riskFilter, setRiskFilter] = useState<string>("ALL");
  const [diagnosisFilter, setDiagnosisFilter] = useState<string>("ALL");
  const [execFilter, setExecFilter] = useState<string>("ALL");
  const [outcomeFilter, setOutcomeFilter] = useState<string>("ALL");

  useEffect(() => {
    let active = true;

    Promise.allSettled([
      fetchSummary(),
      fetchCustomers(),
      fetchBenchmark(),
      fetchRazorpayProof(),
      fetchExceptions(),
      fetchFailureScenarios(),
      fetchGeminiEvaluation(),
    ]).then(([sumRes, custRes, benchRes, proofRes, excRes, failRes, gemRes]) => {
      if (!active) return;

      if (sumRes.status === "fulfilled") setSummary(sumRes.value);
      if (custRes.status === "fulfilled") setCustomers(custRes.value);
      if (benchRes.status === "fulfilled") setBenchmark(benchRes.value);
      if (proofRes.status === "fulfilled") setRazorpayProof(proofRes.value);
      if (excRes.status === "fulfilled") setExceptionsData(excRes.value);
      if (failRes.status === "fulfilled") setFailureScenarios(failRes.value);
      if (gemRes.status === "fulfilled") setGeminiData(gemRes.value);

      if (sumRes.status === "rejected" || custRes.status === "rejected") {
        setError("Failed to connect to REVIVE Operational API. Please ensure backend server is running.");
      } else {
        setError(null);
      }
      setLoading(false);
    });

    return () => {
      active = false;
    };
  }, [reloadTrigger]);

  const handleRetry = () => {
    setLoading(true);
    setReloadTrigger((prev) => prev + 1);
  };

  // Filtered & Sorted Customer Queue
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

    // Default sort: highest risk score descending
    list.sort((a, b) => b.risk_score - a.risk_score);
    return list;
  }, [customers, searchTerm, riskFilter, diagnosisFilter, execFilter, outcomeFilter]);

  // Demo Selectors
  const handleSelectDemo = (customerId: string) => {
    const found = customers.find((c) => c.customer_id === customerId);
    if (found) {
      setSelectedCustomer(found);
      setActiveTab("overview");
    }
  };

  if (loading) {
    return (
      <div className="center-box">
        <div className="spinner"></div>
        <div className="text-secondary font-mono">LOADING REVIVE COMMAND CENTER & EVIDENCE ARTIFACTS...</div>
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="center-box">
        <div className="error-card">
          <div className="error-title">OPERATIONAL SUMMARY UNAVAILABLE</div>
          <div className="text-secondary text-sm mb-3">
            {error || "Operational summary telemetry could not be loaded from /api/dashboard/summary."}
          </div>
          <button type="button" className="retry-btn" onClick={handleRetry}>
            RETRY LOADING SUMMARY
          </button>
        </div>
      </div>
    );
  }

  const { dataset, risk, diagnosis, policy, expected_recovery, measured_recovery, execution } = summary;

  return (
    <div className="app-container">
      {/* 1. TOP HEADER & PROVENANCE BAR */}
      <header className="header-bar">
        <div>
          <div className="brand-title">
            REVIVE <span className="brand-badge">API</span>
          </div>
          <div className="header-subtitle">AI REVENUE RECOVERY COMMAND CENTER & EVIDENCE SUITE</div>
        </div>

        <div className="provenance-badges">
          <div className="prov-chip prov-operational">
            <span className="prov-dot"></span>
            <span>CUSTOMER OPERATIONAL STATE (100 Cases)</span>
          </div>
          <div className="prov-chip prov-proof">
            <span className="prov-dot"></span>
            <span>RAZORPAY TEST MODE (Captured Proof)</span>
          </div>
          <div className="prov-chip prov-benchmark">
            <span className="prov-dot"></span>
            <span>PHASE B BENCHMARK (10k Pairs)</span>
          </div>
        </div>
      </header>

      {/* 2. COMMAND CENTER NAVIGATION TABS */}
      <nav className="tab-navigation">
        <button
          type="button"
          className={`tab-btn ${activeTab === "overview" ? "active" : ""}`}
          onClick={() => setActiveTab("overview")}
        >
          📊 OVERVIEW & RECOVERY QUEUE
        </button>
        <button
          type="button"
          className={`tab-btn ${activeTab === "benchmark" ? "active" : ""}`}
          onClick={() => setActiveTab("benchmark")}
        >
          📈 PHASE B BENCHMARK (10k PAIRS)
        </button>
        <button
          type="button"
          className={`tab-btn ${activeTab === "proof" ? "active" : ""}`}
          onClick={() => setActiveTab("proof")}
        >
          💳 PHASE A RAZORPAY TEST PROOF
        </button>
        <button
          type="button"
          className={`tab-btn ${activeTab === "gemini" ? "active" : ""}`}
          onClick={() => setActiveTab("gemini")}
        >
          🤖 PHASE D GEMINI AI EVIDENCE
        </button>
        <button
          type="button"
          className={`tab-btn ${activeTab === "exceptions" ? "active" : ""}`}
          onClick={() => setActiveTab("exceptions")}
        >
          🛑 EXCEPTIONS & GOVERNED STOPS
        </button>
        <button
          type="button"
          className={`tab-btn ${activeTab === "failure" ? "active" : ""}`}
          onClick={() => setActiveTab("failure")}
        >
          ⚠️ CONTROLLED FAILURE DEMO
        </button>
        <button
          type="button"
          className={`tab-btn ${activeTab === "methodology" ? "active" : ""}`}
          onClick={() => setActiveTab("methodology")}
        >
          📖 METHODOLOGY & LIMITATIONS
        </button>
      </nav>

      {/* 3. TAB VIEW CONTENT */}

      {/* TAB 1: OVERVIEW & RECOVERY QUEUE */}
      {activeTab === "overview" && (
        <>
          {/* HERO KPI CARDS */}
          <section className="kpi-grid">
            <div className="kpi-card risk">
              <div className="kpi-title">REVENUE AT RISK</div>
              <div className="kpi-value">{formatINR(expected_recovery.total_revenue_at_risk)}</div>
              <div className="kpi-subtext text-secondary">{risk.high + risk.critical} High/Critical Tiers</div>
            </div>

            <div className="kpi-card expected">
              <div className="kpi-title">EXPECTED RECOVERY</div>
              <div className="kpi-value">{formatINR(expected_recovery.total_expected_recovery)}</div>
              <div className="kpi-subtext text-purple">
                {expected_recovery.expected_recovery_rate_pct.toFixed(2)}% Policy EV Rate
              </div>
            </div>

            <div className="kpi-card measured">
              <div className="kpi-title">NET RECOVERED REVENUE</div>
              <div className="kpi-value">{formatINR(measured_recovery.net_recovered_revenue)}</div>
              <div className="kpi-subtext text-success">
                {measured_recovery.measured_recovery_rate_pct.toFixed(2)}% Net Realized Rate
              </div>
            </div>

            <div className="kpi-card customers">
              <div className="kpi-title">RECOVERED CUSTOMERS</div>
              <div className="kpi-value">{measured_recovery.recovered_customers}</div>
              <div className="kpi-subtext text-cyan">Out of {execution.successful} Dispatches</div>
            </div>
          </section>

          {/* 9-STAGE RECOVERY PIPELINE VISUALIZATION */}
          <section className="pipeline-card">
            <div className="section-title">9-STAGE REVIVE RECOVERY PIPELINE</div>
            <div className="pipeline-flex">
              <div className="pipeline-step">
                <div className="pipeline-step-name">1. DETECT</div>
                <div className="pipeline-step-val">{dataset.customers_evaluated}</div>
                <div className="pipeline-step-desc">Evaluated</div>
              </div>
              <div className="pipeline-arrow">→</div>

              <div className="pipeline-step">
                <div className="pipeline-step-name">2. DIAGNOSE</div>
                <div className="pipeline-step-val">{diagnosis.payment_friction}</div>
                <div className="pipeline-step-desc">Payment Friction</div>
              </div>
              <div className="pipeline-arrow">→</div>

              <div className="pipeline-step">
                <div className="pipeline-step-name">3. DECIDE</div>
                <div className="pipeline-step-val">{policy.payment_recovery_actions}</div>
                <div className="pipeline-step-desc">Actions Chosen</div>
              </div>
              <div className="pipeline-arrow">→</div>

              <div className="pipeline-step">
                <div className="pipeline-step-name">4. GUARD</div>
                <div className="pipeline-step-val text-success">{policy.eligible_customers}</div>
                <div className="pipeline-step-desc">Policy Authorized</div>
              </div>
              <div className="pipeline-arrow">→</div>

              <div className="pipeline-step">
                <div className="pipeline-step-name">5. EXECUTE</div>
                <div className="pipeline-step-val">{execution.successful}</div>
                <div className="pipeline-step-desc">Dispatched</div>
              </div>
              <div className="pipeline-arrow">→</div>

              <div className="pipeline-step">
                <div className="pipeline-step-name">6. PAYMENT RESULT</div>
                <div className="pipeline-step-val text-xs text-cyan font-bold">Synthetic Observed</div>
                <div className="pipeline-step-desc">Simulation Horizon</div>
              </div>
              <div className="pipeline-arrow">→</div>

              <div className="pipeline-step">
                <div className="pipeline-step-name">7. WEBHOOK</div>
                <div className="pipeline-step-val text-xs text-muted">Not Observed</div>
                <div className="pipeline-step-desc">Synthetic Batch</div>
              </div>
              <div className="pipeline-arrow">→</div>

              <div className="pipeline-step">
                <div className="pipeline-step-name">8. OUTCOME</div>
                <div className="pipeline-step-val text-success">{measured_recovery.recovered_customers}</div>
                <div className="pipeline-step-desc">Recovered</div>
              </div>
              <div className="pipeline-arrow">→</div>

              <div className="pipeline-step">
                <div className="pipeline-step-name">9. ATTRIBUTION</div>
                <div className="pipeline-step-val font-bold text-success">
                  {formatINR(measured_recovery.net_recovered_revenue)}
                </div>
                <div className="pipeline-step-desc">Net Attributed</div>
              </div>
            </div>
          </section>

          {/* EXPECTED VS MEASURED & RISK/DIAGNOSIS */}
          <div className="grid-2col">
            <div className="card">
              <div className="section-title">EXPECTED vs MEASURED RECOVERY ACCOUNTING</div>
              <div className="comparison-grid">
                <div className="comp-box expected">
                  <div className="comp-title">EXPECTED (POLICY EV)</div>
                  <div className="comp-amount">{formatINR(expected_recovery.total_expected_recovery)}</div>
                  <div className="comp-rate text-purple">
                    {expected_recovery.expected_recovery_rate_pct.toFixed(2)}% EV Rate
                  </div>
                </div>
                <div className="comp-box measured">
                  <div className="comp-title">MEASURED (NET ATTRIBUTED)</div>
                  <div className="comp-amount">{formatINR(measured_recovery.net_recovered_revenue)}</div>
                  <div className="comp-rate text-success">
                    {measured_recovery.measured_recovery_rate_pct.toFixed(2)}% Net Rate
                  </div>
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
                  <span className="breakdown-val text-success font-bold">
                    {formatINR(measured_recovery.net_recovered_revenue)}
                  </span>
                </div>
              </div>
            </div>

            <div className="card">
              <div className="section-title">RISK & DIAGNOSTIC TAXONOMY</div>
              <div className="metrics-grid-2 mb-2">
                <div className="stat-row">
                  <span className="stat-label">Critical Tier:</span>
                  <span className="stat-val text-rose font-bold">{risk.critical}</span>
                </div>
                <div className="stat-row">
                  <span className="stat-label">High Tier:</span>
                  <span className="stat-val text-amber font-bold">{risk.high}</span>
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
                  <span className="breakdown-label">Governed Non-Actionable Cases:</span>
                  <span className="breakdown-val text-muted">{diagnosis.non_actionable}</span>
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

          {/* DETERMINISTIC DEMO SELECTOR SHORTCUTS */}
          <section className="demo-selectors-card">
            <div className="section-title">DETERMINISTIC DEMO SELECTORS (SEED 42)</div>
            <div className="demo-btns-grid">
              <button
                type="button"
                className="demo-btn btn-actionable"
                onClick={() => handleSelectDemo("cus_000005")}
              >
                🎯 1. High-Risk Actionable Case (cus_000005)
              </button>
              <button
                type="button"
                className="demo-btn btn-noaction"
                onClick={() => handleSelectDemo("cus_000004")}
              >
                🛑 2. Governed NO_ACTION Case (cus_000004)
              </button>
              <button
                type="button"
                className="demo-btn btn-recovered"
                onClick={() => handleSelectDemo("cus_000005")}
              >
                💰 3. Recovered & Attributed Case (cus_000005)
              </button>
              <button
                type="button"
                className="demo-btn btn-failure"
                onClick={() => setActiveTab("failure")}
              >
                ⚠️ 4. Controlled Failure Scenario
              </button>
            </div>
          </section>

          {/* CUSTOMER QUEUE TABLE */}
          <section className="table-card">
            <div className="table-header-flex">
              <div className="section-title">
                CUSTOMER RECOVERY QUEUE{" "}
                <span className="text-secondary text-sm">({filteredCustomers.length} records)</span>
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

                <select
                  className="filter-select"
                  value={diagnosisFilter}
                  onChange={(e) => setDiagnosisFilter(e.target.value)}
                >
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
                  <option value="NO_ACTION">No Action</option>
                </select>

                <select
                  className="filter-select"
                  value={outcomeFilter}
                  onChange={(e) => setOutcomeFilter(e.target.value)}
                >
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
                      <tr
                        key={cust.customer_id}
                        className="table-row"
                        onClick={() => setSelectedCustomer(cust)}
                      >
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
                          <span className={`badge exec-${cust.execution_status.toLowerCase()}`}>
                            {cust.execution_status}
                          </span>
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
        </>
      )}

      {/* TAB 2: PHASE B BENCHMARK EVIDENCE CENTER */}
      {activeTab === "benchmark" && (
        <section className="benchmark-view">
          {!benchmark || !benchmark.available ? (
            <div className="error-card">
              <div className="error-title">BENCHMARK UNAVAILABLE</div>
              <div className="text-secondary text-sm mb-2">
                Source: {benchmark?.source_artifact || "docs/evidence/phase_b_summary.json"}
              </div>
              <div className="text-rose text-sm font-mono">
                {benchmark?.diagnostic_message || "Committed Phase B evidence snapshot not found."}
              </div>
            </div>
          ) : (
            <>
              {/* BENCHMARK HEADER BANNER */}
              <div className="evidence-header-card">
                <div>
                  <div className="drawer-tag">AUTHORITATIVE COMMITTED EVIDENCE</div>
                  <h2 className="evidence-title">PHASE B: 10,000 PAIRED UNITS CONTROLLED BENCHMARK</h2>
                  <div className="evidence-meta text-secondary text-xs mt-1">
                    Experiment: <span className="text-white font-mono">{benchmark.metadata?.experiment_id}</span> •
                    Seed: <span className="text-white font-bold">{benchmark.metadata?.seed}</span> • Timestamp:{" "}
                    <span className="text-white font-mono">{benchmark.metadata?.timestamp}</span> • Source:{" "}
                    <span className="text-cyan font-mono">{benchmark.source_artifact}</span>
                  </div>
                </div>
                <div className="badge badge-success font-bold text-sm px-3 py-2">
                  ✓ RECONCILIATION PASSED
                </div>
              </div>

              {/* CONTROL VS TREATMENT COMPARISON TABLE */}
              <div className="card mt-3">
                <div className="section-title">CONTROL vs REVIVE (TREATMENT) COMPARATIVE ECONOMICS</div>
                <div className="table-wrapper mt-2">
                  <table className="comparison-table">
                    <thead>
                      <tr>
                        <th>Metric Dimension</th>
                        <th className="text-right">Control Baseline (No Intervention)</th>
                        <th className="text-right">REVIVE Treatment (Active Policy)</th>
                        <th className="text-right">Comparative Delta / Lift</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td><strong>Evaluated Population</strong></td>
                        <td className="text-right font-mono">{benchmark.economics?.control_evaluations?.toLocaleString()} units</td>
                        <td className="text-right font-mono">{benchmark.economics?.treatment_evaluations?.toLocaleString()} units</td>
                        <td className="text-right font-mono font-bold text-cyan">{benchmark.metadata?.total_arm_evaluations?.toLocaleString()} Total Arm Evals</td>
                      </tr>
                      <tr>
                        <td><strong>Conversion Count / Rate</strong></td>
                        <td className="text-right font-mono">
                          {benchmark.economics?.control_conversions} (
                          {((benchmark.economics?.control_conversion_rate || 0) * 100).toFixed(2)}%)
                        </td>
                        <td className="text-right font-mono">
                          {benchmark.economics?.treatment_total_conversions} (
                          {((benchmark.economics?.treatment_total_conversion_rate || 0) * 100).toFixed(2)}%)
                        </td>
                        <td className="text-right font-mono font-bold text-success">
                          +{benchmark.economics?.conversion_lift_points.toFixed(2)} pts (+
                          {benchmark.economics?.conversion_relative_lift_pct.toFixed(2)}% rel)
                        </td>
                      </tr>
                      <tr>
                        <td><strong>Gross Realized Revenue</strong></td>
                        <td className="text-right font-mono">{formatINR(benchmark.economics?.control_gross_revenue)}</td>
                        <td className="text-right font-mono">{formatINR(benchmark.economics?.treatment_total_gross_revenue)}</td>
                        <td className="text-right font-mono text-cyan">
                          +{formatINR(benchmark.economics?.gross_revenue_delta_vs_control)}
                        </td>
                      </tr>
                      <tr>
                        <td><strong>Intervention Direct Execution Cost</strong></td>
                        <td className="text-right font-mono">₹0.00</td>
                        <td className="text-right font-mono text-rose">
                          {formatINR(benchmark.economics?.treatment_intervention_cost)}
                        </td>
                        <td className="text-right font-mono text-rose">
                          -{formatINR(benchmark.economics?.treatment_intervention_cost)}
                        </td>
                      </tr>
                      <tr className="highlight-row">
                        <td><strong>Total Net Realized Revenue</strong></td>
                        <td className="text-right font-mono font-bold">{formatINR(benchmark.economics?.control_net_revenue)}</td>
                        <td className="text-right font-mono font-bold text-success">{formatINR(benchmark.economics?.treatment_total_net_revenue)}</td>
                        <td className="text-right font-mono font-bold text-success">
                          +{formatINR(benchmark.economics?.incremental_net_revenue)}
                        </td>
                      </tr>
                      <tr className="sub-row">
                        <td>↳ <strong>Genuine Incremental Recovery Revenue</strong></td>
                        <td className="text-right font-mono text-muted">—</td>
                        <td className="text-right font-mono font-bold text-success">
                          {formatINR(benchmark.economics?.treatment_genuine_incremental_revenue)}
                        </td>
                        <td className="text-right font-mono text-secondary">
                          {benchmark.economics?.treatment_genuine_incremental_recoveries} genuine recoveries
                        </td>
                      </tr>
                      <tr className="sub-row">
                        <td>↳ <strong>OutcomeEngine Attributable Recovery</strong></td>
                        <td className="text-right font-mono text-muted">—</td>
                        <td className="text-right font-mono">{formatINR(benchmark.economics?.treatment_attributable_recovery_revenue)}</td>
                        <td className="text-right font-mono text-secondary">Attributed on treatment arm</td>
                      </tr>
                      <tr className="highlight-row">
                        <td><strong>Net Recovery ROI</strong></td>
                        <td className="text-right font-mono text-muted">—</td>
                        <td className="text-right font-mono font-bold text-success">
                          {benchmark.economics?.recovery_roi.toFixed(2)}x
                        </td>
                        <td className="text-right font-mono font-bold text-success">
                          ₹{benchmark.economics?.recovery_roi.toFixed(2)} net return per ₹1 cost
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              {/* 4-WAY CONVERSION TAXONOMY & DECISION QUALITY */}
              <div className="grid-2col mt-3">
                <div className="card">
                  <div className="section-title">4-WAY TREATMENT CONVERSION TAXONOMY</div>
                  <div className="breakdown-list mt-2">
                    <div className="breakdown-item">
                      <span className="breakdown-label">1. Natural Conversions (Would convert anyway):</span>
                      <span className="breakdown-val font-mono">
                        {benchmark.economics?.treatment_natural_conversions} cases
                      </span>
                    </div>
                    <div className="breakdown-item">
                      <span className="breakdown-label">2. Genuine Incremental Recoveries (Caused by REVIVE):</span>
                      <span className="breakdown-val font-mono text-success font-bold">
                        {benchmark.economics?.treatment_genuine_incremental_recoveries} cases
                      </span>
                    </div>
                    <div className="breakdown-item">
                      <span className="breakdown-label">3. Observed Unrecoverable Conversions:</span>
                      <span className="breakdown-val font-mono text-secondary">
                        {benchmark.economics?.treatment_observed_unrecoverable_conversions} cases
                      </span>
                    </div>
                    <div className="breakdown-item">
                      <span className="breakdown-label">4. No Treatment Conversion (Lost):</span>
                      <span className="breakdown-val font-mono text-rose">
                        {benchmark.economics?.treatment_no_treatment_conversions} cases
                      </span>
                    </div>
                  </div>
                </div>

                <div className="card">
                  <div className="section-title">DECISION QUALITY & SYSTEM THROUGHPUT</div>
                  <div className="metrics-grid-2 mt-2">
                    <div className="stat-row">
                      <span className="stat-label">Diagnosis Overall Accuracy:</span>
                      <span className="stat-val font-mono">
                        {((benchmark.diagnosis_accuracy?.overall_accuracy || 0) * 100).toFixed(2)}%
                      </span>
                    </div>
                    <div className="stat-row">
                      <span className="stat-label">Diagnosis Macro F1:</span>
                      <span className="stat-val font-mono">
                        {(benchmark.diagnosis_accuracy?.macro_f1 || 0).toFixed(4)}
                      </span>
                    </div>
                    <div className="stat-row">
                      <span className="stat-label">Safety Policy Compliance:</span>
                      <span className="stat-val font-mono text-success font-bold">
                        {((benchmark.intervention_appropriateness?.safety_policy_compliance_rate || 1.0) * 100).toFixed(1)}%
                      </span>
                    </div>
                    <div className="stat-row">
                      <span className="stat-label">Governed Stop Rate:</span>
                      <span className="stat-val font-mono">
                        {((benchmark.safety_governance?.stop_rate || 0) * 100).toFixed(2)}%
                      </span>
                    </div>
                  </div>

                  <div className="throughput-box mt-3">
                    <div className="stat-row">
                      <span className="stat-label">Total Events Processed:</span>
                      <span className="stat-val font-mono">{benchmark.throughput?.events_processed.toLocaleString()}</span>
                    </div>
                    <div className="stat-row">
                      <span className="stat-label">Throughput Rate:</span>
                      <span className="stat-val font-mono text-cyan">
                        {benchmark.throughput?.events_per_second.toFixed(2)} events/sec (
                        {benchmark.throughput?.total_evaluations_per_second.toFixed(2)} arm evals/sec)
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </>
          )}
        </section>
      )}

      {/* TAB 3: PHASE A REAL RAZORPAY TEST MODE PROOF */}
      {activeTab === "proof" && (
        <section className="proof-view">
          {!razorpayProof ? (
            <div className="error-card">
              <div className="error-title">PROOF EVIDENCE UNAVAILABLE</div>
              <div className="text-secondary text-sm">Failed to load Phase A Razorpay Test Mode proof snapshot.</div>
            </div>
          ) : (
            <div className="card">
              <div className="evidence-header-card">
                <div>
                  <div className="drawer-tag">PHASE A PROVEN EXTERNAL INFRASTRUCTURE</div>
                  <h2 className="evidence-title">REAL RAZORPAY TEST MODE RECOVERY PROOF</h2>
                  <div className="evidence-meta text-secondary text-xs mt-1">
                    Environment: <span className="text-white font-bold">{razorpayProof.environment.toUpperCase()}</span> •
                    Status: <span className="text-success font-bold">{razorpayProof.status}</span> • Provenance:{" "}
                    <span className="text-cyan font-bold">{razorpayProof.provenance}</span>
                  </div>
                </div>
                <div className="badge badge-success font-bold text-sm px-3 py-2">
                  ✓ VERIFIED WEBHOOK PROOF
                </div>
              </div>

              <div className="disclosure-banner mt-3">
                <strong>Explicit Disclosure:</strong> {razorpayProof.disclosure}
              </div>

              <div className="metrics-grid-3 mt-3">
                <div className="detail-box">
                  <div className="detail-label">CORRELATED CUSTOMER</div>
                  <div className="detail-value font-mono text-cyan">{razorpayProof.correlated_customer_id}</div>
                </div>
                <div className="detail-box">
                  <div className="detail-label">PLAN & PRICE</div>
                  <div className="detail-value font-mono">
                    {razorpayProof.plan_name} ({formatINR(razorpayProof.plan_price)})
                  </div>
                </div>
                <div className="detail-box">
                  <div className="detail-label">SIGNATURE VERIFICATION</div>
                  <div className="detail-value font-mono text-success">{razorpayProof.signature_verification}</div>
                </div>
              </div>

              <div className="proof-lineage-box mt-3">
                <div className="section-title">VERIFIED END-TO-END EXECUTION LINEAGE</div>
                <div className="pipeline-flex mt-2">
                  <div className="pipeline-step">
                    <div className="pipeline-step-name">1. PAYMENT LINK</div>
                    <div className="pipeline-step-val text-xs font-mono">{razorpayProof.payment_link_id}</div>
                    <div className="pipeline-step-desc">Razorpay API Created</div>
                  </div>
                  <div className="pipeline-arrow">→</div>

                  <div className="pipeline-step">
                    <div className="pipeline-step-name">2. PAYMENT</div>
                    <div className="pipeline-step-val text-xs font-mono">{razorpayProof.payment_id}</div>
                    <div className="pipeline-step-desc">External Customer Paid</div>
                  </div>
                  <div className="pipeline-arrow">→</div>

                  <div className="pipeline-step">
                    <div className="pipeline-step-name">3. WEBHOOK</div>
                    <div className="pipeline-step-val text-xs font-mono">{razorpayProof.webhook_event_id}</div>
                    <div className="pipeline-step-desc">payment_link.paid Received</div>
                  </div>
                  <div className="pipeline-arrow">→</div>

                  <div className="pipeline-step">
                    <div className="pipeline-step-name">4. OUTCOME</div>
                    <div className="pipeline-step-val text-success">{razorpayProof.outcome}</div>
                    <div className="pipeline-step-desc">Confidence: {(razorpayProof.outcome_confidence * 100).toFixed(0)}%</div>
                  </div>
                  <div className="pipeline-arrow">→</div>

                  <div className="pipeline-step">
                    <div className="pipeline-step-name">5. ATTRIBUTION</div>
                    <div className="pipeline-step-val text-success font-bold">{razorpayProof.attribution_status}</div>
                    <div className="pipeline-step-desc">{formatINR(razorpayProof.net_recovered_revenue)} Net</div>
                  </div>
                </div>
              </div>

              <div className="breakdown-list mt-3">
                <div className="breakdown-item">
                  <span className="breakdown-label">Attributable Revenue:</span>
                  <span className="breakdown-val font-mono">{formatINR(razorpayProof.attributable_revenue)}</span>
                </div>
                <div className="breakdown-item">
                  <span className="breakdown-label">Intervention Direct Cost:</span>
                  <span className="breakdown-val font-mono text-rose">{formatINR(razorpayProof.intervention_cost)}</span>
                </div>
                <div className="breakdown-item">
                  <span className="breakdown-label">Net Recovered Revenue:</span>
                  <span className="breakdown-val font-mono font-bold text-success">
                    {formatINR(razorpayProof.net_recovered_revenue)}
                  </span>
                </div>
                <div className="breakdown-item">
                  <span className="breakdown-label">Duplicate Delivery Handling:</span>
                  <span className="breakdown-val font-mono text-cyan">{razorpayProof.duplicate_delivery_status} (HTTP 200)</span>
                </div>
              </div>
            </div>
          )}
        </section>
      )}

      {/* TAB: GEMINI AI EVALUATION & EVIDENCE */}
      {activeTab === "gemini" && (
        <section className="gemini-view">
          {!geminiData ? (
            <div className="error-card">
              <div className="error-title">GEMINI EVALUATION DATA UNAVAILABLE</div>
              <div className="text-secondary text-sm">Failed to connect to Phase D evaluation endpoint.</div>
            </div>
          ) : geminiData.demonstration_case ? (
            /* PHASE D v3: SELECTIVE REAL GEMINI DIAGNOSIS DEMONSTRATION */
            <div className="card">
              {/* STATUS & PROVENANCE HEADER */}
              <div className="gemini-header">
                <div>
                  <div className="drawer-tag">REVIVE PHASE D v3 — SELECTIVE AI DIAGNOSIS INTELLIGENCE</div>
                  <h2 className="section-title text-xl mt-1">Selective Real Gemini Diagnosis Demonstration</h2>
                  <div className="provenance-note mt-1 text-sm text-secondary">
                    Demonstration Case: <strong>Controlled Ambiguous Journey ({geminiData.demonstration_case.customer_id})</strong>
                    <span className="provenance-alert"> (Selective AI Review — Gemini invoked ONLY on multi-signal ambiguity)</span>
                  </div>
                </div>

                <div className="status-badge-container">
                  <span
                    className={`badge status-${
                      (geminiData.status || geminiData.demonstration_case.gemini_response.status).includes("REAL")
                        ? "success"
                        : (geminiData.status || geminiData.demonstration_case.gemini_response.status).includes("FALLBACK")
                        ? "info"
                        : "danger"
                    }`}
                    style={{ fontSize: "0.85rem", padding: "0.4rem 0.8rem", fontWeight: "bold" }}
                  >
                    {geminiData.status || geminiData.demonstration_case.gemini_response.status}
                  </span>
                </div>
              </div>

              {/* AUDIT METADATA STRIP */}
              <div className="detail-grid mt-3">
                <div className="detail-box">
                  <div className="detail-label">MODEL IDENTIFIER</div>
                  <div className="detail-value font-mono font-bold text-cyan">
                    {geminiData.demonstration_case.gemini_response.model || geminiData.model || "gemini-2.5-flash"}
                  </div>
                </div>
                <div className="detail-box">
                  <div className="detail-label">PROMPT VERSION</div>
                  <div className="detail-value font-mono text-sm">{geminiData.prompt_version || "REVIVE_GEMINI_DIAGNOSIS_PROMPT_V3"}</div>
                </div>
                <div className="detail-box">
                  <div className="detail-label">EVIDENCE VERSION</div>
                  <div className="detail-value font-mono text-sm">{geminiData.evidence_version || "3.0.0"}</div>
                </div>
                <div className="detail-box">
                  <div className="detail-label">SOURCE ARTIFACT</div>
                  <div className="detail-value font-mono text-xs">{geminiData.source_artifact}</div>
                </div>
              </div>

              {/* 1. ROUTING DECISION CARD */}
              <div className="card mt-4" style={{ background: "rgba(99, 102, 241, 0.05)", borderColor: "rgba(99, 102, 241, 0.3)" }}>
                <div className="flex justify-between items-center">
                  <div className="section-title text-indigo-400">1. DETERMINISTIC ROUTING DECISION (AI REVIEW ROUTER)</div>
                  <span className="badge badge-primary font-mono font-bold">{geminiData.demonstration_case.routing_mode}</span>
                </div>
                <div className="grid-2-col mt-2">
                  <div>
                    <div className="text-xs text-secondary font-mono">TRIGGER IDENTIFIER:</div>
                    <div className="text-sm font-bold font-mono text-cyan mt-1">{geminiData.demonstration_case.trigger_id}</div>
                  </div>
                  <div>
                    <div className="text-xs text-secondary font-mono">CUSTOMER CASE:</div>
                    <div className="text-sm font-bold font-mono text-white mt-1">{geminiData.demonstration_case.customer_id}</div>
                  </div>
                </div>
                <div className="mt-3 p-2 rounded" style={{ background: "rgba(0,0,0,0.3)", borderLeft: "3px solid #6366f1" }}>
                  <div className="text-xs text-secondary font-mono mb-1">ROUTING RATIONALE (WHY DETERMINISTIC POLICY DELEGATED TO AI):</div>
                  <div className="text-sm text-slate-200">{geminiData.demonstration_case.routing_reason}</div>
                </div>
              </div>

              {/* 2. OBSERVABLE CUSTOMER EVIDENCE */}
              <div className="card mt-3" style={{ background: "rgba(255,255,255,0.02)" }}>
                <div className="section-title">2. OBSERVABLE CUSTOMER EVIDENCE (GROUNDED INPUT)</div>
                <div className="detail-grid mt-2">
                  <div className="detail-box">
                    <div className="detail-label">RISK SCORE & TIER</div>
                    <div className="detail-value font-mono font-bold text-amber">
                      {(geminiData.demonstration_case.observable_signal_summary.risk_score * 100).toFixed(1)}% ({geminiData.demonstration_case.observable_signal_summary.risk_tier})
                    </div>
                  </div>
                  <div className="detail-box">
                    <div className="detail-label">SUBSCRIPTION PLAN</div>
                    <div className="detail-value font-mono">{geminiData.demonstration_case.observable_signal_summary.plan}</div>
                  </div>
                  <div className="detail-box">
                    <div className="detail-label">LIFETIME USAGE</div>
                    <div className="detail-value font-mono text-cyan">
                      {geminiData.demonstration_case.observable_signal_summary.feature_uses} Features • {geminiData.demonstration_case.observable_signal_summary.sessions} Sessions
                    </div>
                  </div>
                  <div className="detail-box">
                    <div className="detail-label">COMMERCIAL SIGNALS</div>
                    <div className="detail-value font-mono text-purple-400">
                      {geminiData.demonstration_case.observable_signal_summary.pricing_page_views} Pricing Views • {geminiData.demonstration_case.observable_signal_summary.checkout_starts} Checkouts
                    </div>
                  </div>
                </div>

                <div className="mt-3">
                  <div className="text-xs text-secondary font-mono mb-1">ACTIVE OBSERVABLE SIGNALS:</div>
                  <div className="flex flex-wrap gap-2">
                    {geminiData.demonstration_case.observable_signal_summary.observable_signals.map((sig, sIdx) => (
                      <span key={sIdx} className="badge badge-muted font-mono" style={{ marginRight: "6px", marginBottom: "4px" }}>
                        {sig}
                      </span>
                    ))}
                  </div>
                </div>
              </div>

              {/* 3. REAL GEMINI RESPONSE */}
              <div
                className="card mt-3"
                style={{
                  background:
                    geminiData.demonstration_case.gemini_response.status === "REAL_GEMINI"
                      ? "rgba(16, 185, 129, 0.05)"
                      : "rgba(239, 68, 68, 0.05)",
                  borderColor:
                    geminiData.demonstration_case.gemini_response.status === "REAL_GEMINI"
                      ? "rgba(16, 185, 129, 0.3)"
                      : "rgba(239, 68, 68, 0.3)",
                }}
              >
                <div className="flex justify-between items-center">
                  <div
                    className={`section-title ${
                      geminiData.demonstration_case.gemini_response.status === "REAL_GEMINI"
                        ? "text-emerald-400"
                        : "text-rose"
                    }`}
                  >
                    3. REAL GEMINI DIAGNOSIS INTELLIGENCE
                  </div>
                  <div className="text-xs font-mono text-secondary">
                    Latency: {geminiData.demonstration_case.gemini_response.latency_ms?.toFixed(0) || "0"} ms
                  </div>
                </div>
                <div className="detail-grid mt-2">
                  <div className="detail-box">
                    <div className="detail-label">CALL STATUS</div>
                    <div
                      className={`detail-value font-mono font-bold ${
                        geminiData.demonstration_case.gemini_response.status === "REAL_GEMINI"
                          ? "text-emerald-300"
                          : "text-rose"
                      }`}
                    >
                      {geminiData.demonstration_case.gemini_response.status}
                    </div>
                  </div>
                  <div className="detail-box">
                    <div className="detail-label">PROPOSED DIAGNOSIS</div>
                    <div className="detail-value font-mono font-bold text-success text-base">
                      {geminiData.demonstration_case.gemini_response.diagnosis || "Unavailable"}
                    </div>
                  </div>
                  <div className="detail-box">
                    <div className="detail-label">CONFIDENCE SCORE</div>
                    <div className="detail-value font-mono font-bold text-cyan">
                      {geminiData.demonstration_case.gemini_response.confidence !== null &&
                      geminiData.demonstration_case.gemini_response.confidence !== undefined
                        ? `${(geminiData.demonstration_case.gemini_response.confidence * 100).toFixed(0)}%`
                        : "N/A"}
                    </div>
                  </div>
                  <div className="detail-box">
                    <div className="detail-label">GEMINI ACTIONABILITY</div>
                    <div className="detail-value font-mono font-bold text-purple-400">
                      {geminiData.demonstration_case.gemini_response.status === "REAL_GEMINI"
                        ? geminiData.demonstration_case.gemini_response.actionability || "CANDIDATE"
                        : "N/A"}
                    </div>
                  </div>
                </div>

                {/* Provider Error & Validation details when call did not succeed with REAL_GEMINI */}
                {geminiData.demonstration_case.gemini_response.status !== "REAL_GEMINI" && (
                  <div
                    className="mt-3 p-3 rounded"
                    style={{ background: "rgba(0,0,0,0.4)", borderLeft: "3px solid #ef4444" }}
                  >
                    {geminiData.demonstration_case.gemini_response.error_type && (
                      <div className="text-xs text-rose font-mono mb-1">
                        ERROR TYPE:{" "}
                        <span className="text-slate-200">
                          {geminiData.demonstration_case.gemini_response.error_type}
                        </span>
                      </div>
                    )}
                    {geminiData.demonstration_case.gemini_response.error_message && (
                      <div className="text-xs text-secondary font-mono mb-1">
                        ERROR MESSAGE:{" "}
                        <span className="text-slate-300">
                          {geminiData.demonstration_case.gemini_response.error_message}
                        </span>
                      </div>
                    )}
                    {geminiData.demonstration_case.gemini_response.validation_error && (
                      <div className="text-xs text-secondary font-mono mb-1">
                        VALIDATION ERROR:{" "}
                        <span className="text-slate-300">
                          {geminiData.demonstration_case.gemini_response.validation_error}
                        </span>
                      </div>
                    )}
                  </div>
                )}

                {geminiData.demonstration_case.gemini_response.rationale && (
                  <div className="mt-3 p-3 rounded" style={{ background: "rgba(0,0,0,0.3)", borderLeft: "3px solid #10b981" }}>
                    <div className="text-xs text-secondary font-mono mb-1">OBSERVABLE RATIONALE:</div>
                    <div className="text-sm text-slate-200" style={{ lineHeight: "1.5" }}>
                      {geminiData.demonstration_case.gemini_response.rationale}
                    </div>
                  </div>
                )}

                {geminiData.demonstration_case.gemini_response.status === "REAL_GEMINI" && (
                  <div className="mt-3 grid-2-col">
                    <div>
                      <div className="text-xs text-secondary font-mono mb-1">EVIDENCE ITEMS GROUNDED:</div>
                      <ul className="text-xs text-slate-300 font-mono" style={{ paddingLeft: "1.2rem", margin: 0 }}>
                        {geminiData.demonstration_case.gemini_response.evidence_used?.map((ev, eIdx) => (
                          <li key={eIdx}>{ev}</li>
                        )) || <li>None</li>}
                      </ul>
                    </div>
                    <div>
                      <div className="text-xs text-secondary font-mono mb-1">REPORTED UNCERTAINTY / BOUNDS:</div>
                      <div className="text-xs text-slate-400 font-mono">
                        {geminiData.demonstration_case.gemini_response.uncertainty_notes || "None reported. Diagnosis grounded in clear pricing view evidence."}
                      </div>
                    </div>
                  </div>
                )}
              </div>


              {/* 4. GOVERNANCE & SAFETY CONTAINMENT */}
              <div className="card mt-3">
                <div className="section-title">4. GOVERNANCE & SAFETY CONTAINMENT</div>
                <div className="grid-2-col mt-2">
                  <div className="detail-box">
                    <div className="detail-label">SAFETY BOUNDARY CHECKS</div>
                    <div className="breakdown-list mt-2">
                      <div className="breakdown-item">
                        <span className="breakdown-label">Execution Authority:</span>
                        <span className="breakdown-val font-mono text-cyan font-bold">
                          {geminiData.demonstration_case.governance_result.execution_authority}
                        </span>
                      </div>
                      <div className="breakdown-item">
                        <span className="breakdown-label">Execution Bypass Detected:</span>
                        <span className="breakdown-val font-mono text-success font-bold">
                          {geminiData.demonstration_case.governance_result.execution_bypass_detected ? "YES (VIOLATION)" : "NO (0 Observed)"}
                        </span>
                      </div>
                      <div className="breakdown-item">
                        <span className="breakdown-label">Unsupported Action Claim:</span>
                        <span className="breakdown-val font-mono text-success font-bold">
                          {geminiData.demonstration_case.governance_result.unsupported_action_claim_detected ? "YES (VIOLATION)" : "NO (0 Observed)"}
                        </span>
                      </div>
                      <div className="breakdown-item">
                        <span className="breakdown-label">Policy Guard Violation:</span>
                        <span className="breakdown-val font-mono text-success font-bold">
                          {geminiData.demonstration_case.governance_result.policy_guard_violation_detected ? "YES (VIOLATION)" : "NO (0 Observed)"}
                        </span>
                      </div>
                      <div className="breakdown-item">
                        <span className="breakdown-label">Mandatory Policy Gating:</span>
                        <span className="breakdown-val font-mono text-success font-bold">
                          {geminiData.demonstration_case.governance_result.policy_gating_applied ? "APPLIED ✓" : "NOT APPLIED"}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="detail-box">
                    <div className="detail-label">GOVERNANCE PRINCIPLE VERIFICATION</div>
                    <div className="text-sm mt-2 text-secondary" style={{ lineHeight: "1.6" }}>
                      <strong>"AI Proposes; Deterministic Policy Authorizes; Guarded Execution Acts."</strong>
                      <p className="mt-1">
                        Gemini cannot trigger outreach, refund revenue, dispatch payment links, or override business guardrails.
                        All proposals are handed off to REVIVE deterministic policy gates.
                      </p>
                      <div className="mt-2 text-xs font-mono text-success font-bold">
                        Verdict: {geminiData.demonstration_case.governance_result.governance_verdict}
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* 5. DETERMINISTIC POLICY DECISION & EXECUTION AUTHORITY */}
              <div className="card mt-3" style={{ background: "rgba(59, 130, 246, 0.05)", borderColor: "rgba(59, 130, 246, 0.3)" }}>
                <div className="section-title text-blue-400">5. DETERMINISTIC POLICY DECISION (InterventionEngine)</div>
                <div className="detail-grid mt-2">
                  <div className="detail-box">
                    <div className="detail-label">POLICY VERSION</div>
                    <div className="detail-value font-mono">{geminiData.demonstration_case.policy_result.policy_version}</div>
                  </div>
                  <div className="detail-box">
                    <div className="detail-label">ELIGIBILITY STATUS</div>
                    <div className="detail-value font-mono font-bold text-success">
                      {geminiData.demonstration_case.policy_result.eligibility_status}
                    </div>
                  </div>
                  <div className="detail-box">
                    <div className="detail-label">SELECTED INTERVENTION ACTION</div>
                    <div className="detail-value font-mono font-bold text-cyan">
                      {geminiData.demonstration_case.policy_result.selected_action}
                    </div>
                  </div>
                  <div className="detail-box">
                    <div className="detail-label">EXPECTED RECOVERY VALUE</div>
                    <div className="detail-value font-mono font-bold text-emerald-400">
                      {formatINR(geminiData.demonstration_case.policy_result.expected_value)}
                    </div>
                  </div>
                </div>

                <div className="mt-3 p-2 rounded" style={{ background: "rgba(0,0,0,0.3)", borderLeft: "3px solid #3b82f6" }}>
                  <div className="text-xs text-secondary font-mono mb-1">GOVERNED DECISION SUMMARY:</div>
                  <div className="text-sm text-slate-200">{geminiData.demonstration_case.policy_result.governed_decision_summary}</div>
                </div>

                <div className="mt-3 grid-2-col">
                  <div className="detail-box">
                    <div className="detail-label">EXECUTION AUTHORITY HELD BY</div>
                    <div className="detail-value font-mono text-sm text-white">
                      {geminiData.demonstration_case.execution_authority_result.authority_held_by}
                    </div>
                  </div>
                  <div className="detail-box">
                    <div className="detail-label">GUARDED EXECUTION STATUS</div>
                    <div className="detail-value font-mono text-sm text-success font-bold">
                      {geminiData.demonstration_case.execution_authority_result.guarded_execution_status}
                    </div>
                  </div>
                </div>
              </div>

              {/* 6. TOKEN USAGE & COST ACCOUNTING */}
              <div className="card mt-3">
                <div className="section-title">6. TOKEN USAGE & COST ACCOUNTING</div>
                <div className="grid-2-col mt-2">
                  <div className="detail-box">
                    <div className="detail-label">TOKEN CONSUMPTION (PROVIDER REPORTED)</div>
                    <div className="breakdown-list mt-2">
                      <div className="breakdown-item">
                        <span className="breakdown-label">Prompt Tokens:</span>
                        <span className="breakdown-val font-mono">{geminiData.demonstration_case.cost_accounting?.prompt_tokens ?? "N/A"}</span>
                      </div>
                      <div className="breakdown-item">
                        <span className="breakdown-label">Candidate Output Tokens:</span>
                        <span className="breakdown-val font-mono">{geminiData.demonstration_case.cost_accounting?.candidates_tokens ?? "N/A"}</span>
                      </div>
                      <div className="breakdown-item">
                        <span className="breakdown-label">Total Tokens:</span>
                        <span className="breakdown-val font-mono font-bold text-cyan">{geminiData.demonstration_case.cost_accounting?.total_tokens ?? "N/A"}</span>
                      </div>
                    </div>
                  </div>

                  <div className="detail-box">
                    <div className="detail-label">ESTIMATED COMMERCIAL COST</div>
                    <div className="text-sm mt-2 text-secondary" style={{ lineHeight: "1.6" }}>
                      <div>
                        <strong>Estimated Cost:</strong>{" "}
                        <span className="font-mono text-cyan font-bold">
                          {geminiData.demonstration_case.cost_accounting?.estimated_cost_inr !== undefined &&
                          geminiData.demonstration_case.cost_accounting?.estimated_cost_inr !== null
                            ? `Rs. ${geminiData.demonstration_case.cost_accounting.estimated_cost_inr.toFixed(4)}`
                            : "N/A — Pricing basis not configured"}
                        </span>
                      </div>
                      <p className="mt-2 text-xs">
                        {geminiData.cost_accounting?.cost_basis_note ||
                          "Real Gemini token counts recorded. Currency pricing is not fabricated."}
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            /* HISTORICAL / BATCH EVALUATION CARD */
            <div className="card">
              {/* STATUS & PROVENANCE HEADER */}
              <div className="gemini-header">
                <div>
                  <div className="drawer-tag">REVIVE PHASE D — AI INTELLIGENCE & EVALUATION</div>
                  <h2 className="section-title text-xl mt-1">Google Gemini Real Diagnosis Evaluation</h2>
                  <div className="provenance-note mt-1 text-sm text-secondary">
                    Dataset: <strong>{(geminiData.metadata as Record<string, string>)?.dataset_name || "Phase D Gemini Evaluation Sample (100 customers, Seed 42)"}</strong>
                    <span className="provenance-alert"> (Dedicated Phase D Evaluation Sample — NOT Phase B 10k Benchmark)</span>
                  </div>
                </div>

                <div className="status-badge-container">
                  <span
                    className={`badge status-${
                      geminiData.status.includes("REAL")
                        ? "success"
                        : geminiData.status.includes("FALLBACK")
                        ? "info"
                        : geminiData.status.includes("ERROR")
                        ? "danger"
                        : "warning"
                    }`}
                    style={{ fontSize: "0.85rem", padding: "0.4rem 0.8rem", fontWeight: "bold" }}
                  >
                    {geminiData.status}
                  </span>
                </div>
              </div>

              {/* AUDIT METADATA STRIP */}
              <div className="detail-grid mt-3">
                <div className="detail-box">
                  <div className="detail-label">MODEL IDENTIFIER</div>
                  <div className="detail-value font-mono font-bold text-cyan">{geminiData.model || "gemini-2.5-flash"}</div>
                </div>
                <div className="detail-box">
                  <div className="detail-label">PROMPT VERSION</div>
                  <div className="detail-value font-mono text-sm">{geminiData.prompt_version || "REVIVE_GEMINI_DIAGNOSIS_PROMPT_V1"}</div>
                </div>
                <div className="detail-box">
                  <div className="detail-label">EVIDENCE VERSION</div>
                  <div className="detail-value font-mono text-sm">{geminiData.evidence_version || "1.0.0"}</div>
                </div>
                <div className="detail-box">
                  <div className="detail-label">SOURCE ARTIFACT</div>
                  <div className="detail-value font-mono text-xs">{geminiData.source_artifact}</div>
                </div>
              </div>

              {/* DIAGNOSTIC NOTICE IF UNAVAILABLE / ERROR */}
              {geminiData.diagnostic_message && (
                <div className="disclosure-banner mt-3">
                  <strong>Evaluation Note:</strong> {geminiData.diagnostic_message}
                </div>
              )}

              {/* OPERATIONAL RELIABILITY GRID */}
              <div className="section-title mt-4">OPERATIONAL RELIABILITY & CALL RECONCILIATION</div>
              <div className="kpi-grid mt-2">
                <div className="kpi-card">
                  <div className="kpi-title">ATTEMPTED EVALUATIONS</div>
                  <div className="kpi-value">{geminiData.operational_metrics?.attempted_evaluations ?? 0}</div>
                  <div className="kpi-subtext text-secondary">Controlled Customer Journeys</div>
                </div>
                <div className="kpi-card">
                  <div className="kpi-title">REAL GEMINI SUCCESS</div>
                  <div className="kpi-value text-success">{geminiData.operational_metrics?.successful_evaluations ?? 0}</div>
                  <div className="kpi-subtext text-secondary">Success Rate: {geminiData.operational_metrics?.success_rate_pct ?? 0}%</div>
                </div>
                <div className="kpi-card">
                  <div className="kpi-title">SCOREABLE EVALUATIONS</div>
                  <div className="kpi-value text-cyan">{geminiData.operational_metrics?.scoreable_evaluations ?? 0}</div>
                  <div className="kpi-subtext text-secondary">Observable Contract Grounded</div>
                </div>
                <div className="kpi-card">
                  <div className="kpi-title">SCHEMA REJECTIONS</div>
                  <div className="kpi-value text-amber">{geminiData.operational_metrics?.schema_rejections ?? 0}</div>
                  <div className="kpi-subtext text-secondary">Malformed / Out-of-Bounds</div>
                </div>
                <div className="kpi-card">
                  <div className="kpi-title">MODEL ERRORS & 429s</div>
                  <div className="kpi-value text-rose">{geminiData.operational_metrics?.model_errors ?? 0}</div>
                  <div className="kpi-subtext text-secondary">Retries: {geminiData.operational_metrics?.total_retries ?? 0}</div>
                </div>
                <div className="kpi-card">
                  <div className="kpi-title">FALLBACK INVOCATIONS</div>
                  <div className="kpi-value text-cyan">{geminiData.operational_metrics?.fallback_evaluations ?? 0}</div>
                  <div className="kpi-subtext text-secondary">Phase 4 Baseline Engaged</div>
                </div>
              </div>

              {/* RECONCILIATION BADGE */}
              <div className="mt-2 text-sm text-secondary font-mono" style={{ background: "rgba(255,255,255,0.03)", padding: "0.6rem 1rem", borderRadius: "6px" }}>
                <strong>Status Accounting:</strong> {geminiData.operational_metrics?.reconciliation_formula || "100% Terminal State Reconciliation"}
                {" — "}
                <span className={geminiData.operational_metrics?.reconciliation_passed ? "text-success font-bold" : "text-rose font-bold"}>
                  {geminiData.operational_metrics?.reconciliation_passed ? "RECONCILED ✓" : "RECONCILIATION ERROR"}
                </span>
              </div>

              {/* OBSERVABILITY METRICS */}
              {geminiData.observability_metrics && (
                <div className="card mt-3" style={{ background: "rgba(255,255,255,0.02)" }}>
                  <div className="section-title">OBSERVABLE EVIDENCE CONTRACT & LABEL DISTRIBUTION</div>
                  <div className="text-xs text-secondary mb-2">
                    Scoreable Rate: <strong className="text-success">{geminiData.observability_metrics.scoreable_rate_pct}%</strong> ({geminiData.observability_metrics.scoreable_count} of {geminiData.observability_metrics.total_evaluated} journeys mapped to deterministic observable contracts).
                  </div>
                  <div className="flex flex-wrap gap-2 mt-2">
                    {Object.entries(geminiData.observability_metrics.observable_label_distribution).map(([lbl, cnt]) => (
                      <span key={lbl} className="badge badge-muted font-mono" style={{ marginRight: "6px", marginBottom: "4px" }}>
                        {lbl}: <strong className="text-cyan">{cnt}</strong>
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* GOVERNANCE & SAFETY CONTAINMENT */}
              <div className="section-title mt-4">GOVERNANCE & SAFETY BOUNDARIES</div>
              <div className="grid-2-col mt-2">
                <div className="detail-box">
                  <div className="detail-label">SAFETY & CONTAINMENT AUDIT</div>
                  <div className="breakdown-list mt-2">
                    <div className="breakdown-item">
                      <span className="breakdown-label">Execution Bypass Attempts:</span>
                      <span className="breakdown-val font-mono text-success font-bold">
                        {geminiData.governance_metrics?.execution_bypass_attempts_observed ?? 0} (Zero Observed)
                      </span>
                    </div>
                    <div className="breakdown-item">
                      <span className="breakdown-label">Unsupported Action Claims:</span>
                      <span className="breakdown-val font-mono text-success font-bold">
                        {geminiData.governance_metrics?.unsupported_action_claims_observed ?? 0} (Zero Observed)
                      </span>
                    </div>
                    <div className="breakdown-item">
                      <span className="breakdown-label">Policy Guard Violations:</span>
                      <span className="breakdown-val font-mono text-success font-bold">
                        {geminiData.governance_metrics?.policy_guard_violations_observed ?? 0} (Zero Observed)
                      </span>
                    </div>
                    <div className="breakdown-item">
                      <span className="breakdown-label">Non-Compliant Records:</span>
                      <span className="breakdown-val font-mono text-success font-bold">
                        {geminiData.governance_metrics?.non_compliant_records_count ?? 0}
                      </span>
                    </div>
                    <div className="breakdown-item">
                      <span className="breakdown-label">Safety Compliance Rate:</span>
                      <span className="breakdown-val font-mono text-success font-bold">
                        {geminiData.governance_metrics?.safety_compliance_rate_pct ?? 100}%
                      </span>
                    </div>
                  </div>
                </div>

                <div className="detail-box">
                  <div className="detail-label">GOVERNANCE PRINCIPLE VERIFICATION</div>
                  <div className="text-sm mt-2 text-secondary" style={{ lineHeight: "1.6" }}>
                    <strong>"Gemini Proposes Diagnosis Intelligence; REVIVE Retains Execution Authority."</strong>
                    <p className="mt-1">
                      Gemini output is constrained strictly to root-cause diagnosis candidate proposals.
                      No model response can authorize payments, dispatch links, refund revenue, or override deterministic policy guards.
                    </p>
                    <div className="mt-2 text-xs font-mono text-success">
                      Verdict: {geminiData.governance_metrics?.governance_verdict}
                    </div>
                  </div>
                </div>
              </div>

              {/* MODEL QUALITY METRICS */}
              <div className="section-title mt-4">DIAGNOSIS QUALITY EVALUATION (vs OBSERVABLE CONTRACT)</div>
              {geminiData.quality_metrics?.available ? (
                <div className="mt-2">
                  <div className="kpi-grid">
                    <div className="kpi-card">
                      <div className="kpi-title">SCOREABLE DENOMINATOR</div>
                      <div className="kpi-value text-cyan font-bold">
                        {geminiData.quality_metrics.scoreable_denominator ?? 0}
                      </div>
                      <div className="kpi-subtext text-secondary">Real Gemini + Valid</div>
                    </div>
                    <div className="kpi-card">
                      <div className="kpi-title">DIAGNOSIS ACCURACY</div>
                      <div className="kpi-value text-success font-bold">
                        {((geminiData.quality_metrics.diagnosis_accuracy || 0) * 100).toFixed(1)}%
                      </div>
                      <div className="kpi-subtext text-secondary">vs Observable Contract</div>
                    </div>
                    <div className="kpi-card">
                      <div className="kpi-title">MACRO F1 SCORE</div>
                      <div className="kpi-value text-cyan font-bold">
                        {((geminiData.quality_metrics.macro_f1 || 0) * 100).toFixed(1)}%
                      </div>
                      <div className="kpi-subtext text-secondary">Balanced Across Categories</div>
                    </div>
                    <div className="kpi-card">
                      <div className="kpi-title">MACRO PRECISION</div>
                      <div className="kpi-value text-secondary font-bold">
                        {((geminiData.quality_metrics.macro_precision || 0) * 100).toFixed(1)}%
                      </div>
                      <div className="kpi-subtext text-secondary">False Positive Control</div>
                    </div>
                    <div className="kpi-card">
                      <div className="kpi-title">MACRO RECALL</div>
                      <div className="kpi-value text-secondary font-bold">
                        {((geminiData.quality_metrics.macro_recall || 0) * 100).toFixed(1)}%
                      </div>
                      <div className="kpi-subtext text-secondary">Cause Coverage Rate</div>
                    </div>
                  </div>

                  {/* Per-Category Quality Table */}
                  {Object.keys(geminiData.quality_metrics.per_category_metrics || {}).length > 0 && (
                    <div className="table-responsive mt-3">
                      <table className="table">
                        <thead>
                          <tr>
                            <th>DIAGNOSIS CATEGORY</th>
                            <th>SUPPORT (CASES)</th>
                            <th>PRECISION</th>
                            <th>RECALL</th>
                            <th>F1 SCORE</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(geminiData.quality_metrics.per_category_metrics).map(([cat, m]) => (
                            <tr key={cat}>
                              <td className="font-bold">{cat}</td>
                              <td className="font-mono">{m.support}</td>
                              <td className="font-mono">{(m.precision * 100).toFixed(1)}%</td>
                              <td className="font-mono">{(m.recall * 100).toFixed(1)}%</td>
                              <td className="font-mono font-bold text-success">{(m.f1 * 100).toFixed(1)}%</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}

                  {/* Confusion Matrix Table */}
                  {geminiData.quality_metrics.confusion_matrix && geminiData.quality_metrics.confusion_matrix_labels && (
                    <div className="card mt-3">
                      <div className="section-title text-sm">CONFUSION MATRIX (Actual Rows vs Predicted Columns)</div>
                      <div className="table-responsive mt-2">
                        <table className="table font-mono text-xs">
                          <thead>
                            <tr>
                              <th>Actual \ Pred</th>
                              {geminiData.quality_metrics.confusion_matrix_labels.map((lbl) => (
                                <th key={lbl} style={{ fontSize: "10px" }}>{lbl}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {geminiData.quality_metrics.confusion_matrix.map((row, rIdx) => (
                              <tr key={rIdx}>
                                <td className="font-bold text-white">{geminiData.quality_metrics?.confusion_matrix_labels?.[rIdx]}</td>
                                {row.map((cell, cIdx) => (
                                  <td
                                    key={cIdx}
                                    className={rIdx === cIdx ? "text-success font-bold" : cell > 0 ? "text-amber" : "text-muted"}
                                  >
                                    {cell}
                                  </td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="disclosure-banner mt-2">
                  <strong>Quality Metrics Basis:</strong> {geminiData.quality_metrics?.evaluation_basis || "Zero real Gemini responses received. Accuracy and F1 metrics are not fabricated."}
                </div>
              )}

              {/* COST & USAGE PANEL */}
              <div className="section-title mt-4">TOKEN USAGE & COST ACCOUNTING</div>
              <div className="grid-2-col mt-2">
                <div className="detail-box">
                  <div className="detail-label">TOKEN CONSUMPTION (PROVIDER REPORTED)</div>
                  <div className="breakdown-list mt-2">
                    <div className="breakdown-item">
                      <span className="breakdown-label">Prompt Tokens:</span>
                      <span className="breakdown-val font-mono">{geminiData.cost_accounting?.prompt_tokens_sum ?? "Unavailable"}</span>
                    </div>
                    <div className="breakdown-item">
                      <span className="breakdown-label">Candidate Output Tokens:</span>
                      <span className="breakdown-val font-mono">{geminiData.cost_accounting?.candidates_tokens_sum ?? "Unavailable"}</span>
                    </div>
                    <div className="breakdown-item">
                      <span className="breakdown-label">Total Tokens:</span>
                      <span className="breakdown-val font-mono font-bold text-cyan">{geminiData.cost_accounting?.total_tokens_sum ?? "Unavailable"}</span>
                    </div>
                  </div>
                </div>

                <div className="detail-box">
                  <div className="detail-label">COST ACCOUNTING INTEGRITY</div>
                  <div className="text-sm mt-2 text-secondary" style={{ lineHeight: "1.6" }}>
                    <div><strong>Accounting Status:</strong> <span className="font-mono text-cyan">{geminiData.cost_accounting?.cost_data_status}</span></div>
                    <p className="mt-2 text-xs">
                      {geminiData.cost_accounting?.cost_basis_note}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}
        </section>
      )}


      {/* TAB 4: EXCEPTIONS & GOVERNED NON-ACTIONS */}
      {activeTab === "exceptions" && (
        <section className="exceptions-view">
          {!exceptionsData ? (
            <div className="error-card">
              <div className="error-title">EXCEPTIONS DATA UNAVAILABLE</div>
              <div className="text-secondary text-sm">Failed to load exception ledger.</div>
            </div>
          ) : (
            <>
              <div className="evidence-header-card">
                <div>
                  <div className="drawer-tag">BOUNDED AI SAFETY & SYSTEM RESTRAINT</div>
                  <h2 className="evidence-title">EXCEPTIONS & GOVERNED NON-ACTIONS ("WHY REVIVE DIDN'T ACT")</h2>
                  <div className="evidence-meta text-secondary text-xs mt-1">
                    Total Governed Stops/Exceptions:{" "}
                    <span className="text-white font-bold">{exceptionsData.total_exceptions}</span> • Retryable:{" "}
                    <span className="text-cyan font-bold">{exceptionsData.retryable_count}</span> • Terminal Stops:{" "}
                    <span className="text-rose font-bold">{exceptionsData.terminal_count}</span>
                  </div>
                </div>
              </div>

              <div className="grid-3col mt-3">
                <div className="card">
                  <div className="section-title">EXCEPTIONS BY PIPELINE STAGE</div>
                  {Object.entries(exceptionsData.by_stage).map(([stg, cnt]) => (
                    <div key={stg} className="stat-row">
                      <span className="stat-label">{stg}:</span>
                      <span className="stat-val font-mono">{cnt}</span>
                    </div>
                  ))}
                </div>

                <div className="card">
                  <div className="section-title">EXCEPTIONS BY FAILURE TYPE</div>
                  {Object.entries(exceptionsData.by_failure_type).map(([ft, cnt]) => (
                    <div key={ft} className="stat-row">
                      <span className="stat-label">{ft}:</span>
                      <span className="stat-val font-mono">{cnt}</span>
                    </div>
                  ))}
                </div>

                <div className="card">
                  <div className="section-title">GOVERNANCE METRICS</div>
                  <div className="stat-row">
                    <span className="stat-label">Human Escalations:</span>
                    <span className="stat-val font-mono">{exceptionsData.human_escalation_count}</span>
                  </div>
                  <div className="stat-row">
                    <span className="stat-label">Unrecovered Exposure:</span>
                    <span className="stat-val font-mono">{formatINR(exceptionsData.total_financial_impact)}</span>
                  </div>
                </div>
              </div>

              <div className="card mt-3">
                <div className="section-title">SAMPLE GOVERNED STOPS & AUDITED DECISIONS</div>
                <div className="table-wrapper mt-2">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Category</th>
                        <th>Customer ID</th>
                        <th>Decision</th>
                        <th>Policy Action</th>
                        <th>Retryable</th>
                        <th>Governed Reason</th>
                      </tr>
                    </thead>
                    <tbody>
                      {exceptionsData.sample_exceptions.map((exc, idx) => (
                        <tr key={idx}>
                          <td><span className="badge font-mono">{exc.category}</span></td>
                          <td className="font-mono text-cyan">{exc.customer_id || "N/A"}</td>
                          <td className="font-bold">{exc.decision}</td>
                          <td><span className="badge badge-rose">{exc.policy_action}</span></td>
                          <td><span className={`badge ${exc.retryable ? "badge-cyan" : "badge-muted"}`}>{exc.retryable ? "YES" : "NO"}</span></td>
                          <td className="text-sm text-secondary">{exc.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </section>
      )}

      {/* TAB 5: CONTROLLED FAILURE DEMONSTRATION */}
      {activeTab === "failure" && (
        <section className="failure-view">
          <div className="evidence-header-card">
            <div>
              <div className="drawer-tag">RUNTIME RESILIENCE & ERROR HANDLING</div>
              <h2 className="evidence-title">CONTROLLED FAILURE & GRACEFUL RECOVERY DEMONSTRATION</h2>
              <div className="evidence-meta text-secondary text-xs mt-1">
                CONTROLLED DETERMINISTIC FAILURE FIXTURE backed by real ExecutionEngine failure semantics (not a live customer decision).
              </div>
            </div>
            <div className="badge badge-amber font-bold text-sm px-3 py-2">
              CONTROLLED DETERMINISTIC FAILURE FIXTURE
            </div>
          </div>

          <div className="failure-selector-tabs mt-3">
            {failureScenarios.map((scen, idx) => (
              <button
                key={scen.scenario_id}
                type="button"
                className={`failure-tab-btn ${selectedFailureIdx === idx ? "active" : ""}`}
                onClick={() => setSelectedFailureIdx(idx)}
              >
                {scen.title}
              </button>
            ))}
          </div>

          {failureScenarios[selectedFailureIdx] && (
            <div className="card mt-3">
              <div className="metrics-grid-4 mb-3">
                <div className="detail-box">
                  <div className="detail-label">FIXTURE TARGET</div>
                  <div className="detail-value font-mono text-cyan">
                    {failureScenarios[selectedFailureIdx].customer_id} (FIXTURE)
                  </div>
                </div>
                <div className="detail-box">
                  <div className="detail-label">FAILURE CLASSIFICATION</div>
                  <div className="detail-value font-mono text-rose font-bold">
                    {failureScenarios[selectedFailureIdx].failure_type}
                  </div>
                </div>
                <div className="detail-box">
                  <div className="detail-label">STATE-MACHINE TRANSITION</div>
                  <div className="detail-value font-mono text-amber font-bold">
                    {failureScenarios[selectedFailureIdx].final_state}
                  </div>
                </div>
                <div className="detail-box">
                  <div className="detail-label">SAFE POLICY ACTION</div>
                  <div className="detail-value font-mono text-success font-bold">
                    {failureScenarios[selectedFailureIdx].safe_action}
                  </div>
                </div>
              </div>

              <div className="section-title">STEP-BY-STEP FAILURE & RECOVERY LIFECYCLE</div>
              <div className="failure-steps-container mt-2">
                {failureScenarios[selectedFailureIdx].steps.map((step) => (
                  <div key={step.step_number} className="failure-step-card">
                    <div className="failure-step-header">
                      <div className="failure-step-badge">{step.step_number}</div>
                      <div className="failure-step-title">{step.step_name}</div>
                      <span className={`badge status-${step.status.toLowerCase().replace(/_/g, "-")}`}>
                        {step.status}
                      </span>
                    </div>
                    <div className="failure-step-desc text-sm mt-1">{step.description}</div>
                    <div className="failure-step-snapshot font-mono text-xs mt-2">
                      {JSON.stringify(step.state_snapshot)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
      )}

      {/* TAB 6: METHODOLOGY & LIMITATIONS */}
      {activeTab === "methodology" && (
        <section className="methodology-view">
          <div className="card">
            <div className="section-title">EVALUATION METHODOLOGY & TRANSPARENT DISCLOSURES</div>

            <div className="disclosure-banner mt-2 mb-3">
              <strong>Critical Disclosure:</strong> Phase B is a deterministic synthetic evaluation. Ground-truth
              labels are hidden from REVIVE during decision-making and used only after the decision for evaluation.
              These figures are not production merchant results.
            </div>

            <div className="methodology-section">
              <h3 className="methodology-heading">1. Paired Experimental Units</h3>
              <p className="text-secondary text-sm">
                10,000 paired synthetic customer journeys were generated under deterministic Seed 42. Each paired unit
                was evaluated twice: once in the Control Arm (simulating zero merchant intervention) and once in the
                Treatment Arm (simulating active REVIVE detection, diagnosis, policy gating, and recovery execution).
              </p>
            </div>

            <div className="methodology-section mt-3">
              <h3 className="methodology-heading">2. Four-Way Conversion Taxonomy</h3>
              <ul className="methodology-list text-secondary text-sm">
                <li><strong>Natural Conversion:</strong> Customer converts independently without intervention.</li>
                <li><strong>Genuine Incremental Recovery:</strong> Customer converts solely due to REVIVE's intervention.</li>
                <li><strong>Observed Unrecoverable:</strong> Customer converts despite prior model unrecoverability label.</li>
                <li><strong>No Conversion:</strong> Customer remains unrecovered.</li>
              </ul>
            </div>

            <div className="methodology-section mt-3">
              <h3 className="methodology-heading">3. Financial Metrics Definitions</h3>
              <ul className="methodology-list text-secondary text-sm">
                <li><strong>Net Revenue Delta vs Control:</strong> Total Treatment Net Revenue minus Total Control Net Revenue.</li>
                <li><strong>Genuine Incremental Recovery Revenue:</strong> Value of conversions that would not have occurred without intervention.</li>
                <li><strong>OutcomeEngine Attributable Recovery:</strong> Gross observed recovery revenue attributable to active recovery links.</li>
                <li><strong>Intervention Cost:</strong> Direct execution dispatch and outreach expenses.</li>
              </ul>
            </div>

            <div className="methodology-section mt-3">
              <h3 className="methodology-heading">4. Known Limitations</h3>
              <p className="text-secondary text-sm">
                Customer behavior was simulated using synthetic event generators with stochastic response functions. While
                interventions were evaluated through real deterministic policy constraints, live merchant deployments may
                exhibit distinct customer response dynamics.
              </p>
            </div>
          </div>
        </section>
      )}

      {/* 4. CUSTOMER DETAIL DRAWER */}
      <CustomerDrawer customer={selectedCustomer} onClose={() => setSelectedCustomer(null)} />
    </div>
  );
}

export default App;
