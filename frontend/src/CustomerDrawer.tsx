import React, { useEffect, useState } from "react";
import type { CustomerEvidenceRecord, AuditTimelineData, CohortControls } from "./types";
import { fetchCustomerAudit } from "./api";
import { formatINR } from "./utils";

interface CustomerDrawerProps {
  customer: CustomerEvidenceRecord | null;
  controls?: CohortControls;
  onClose: () => void;
}

export const CustomerDrawer: React.FC<CustomerDrawerProps> = ({ customer, controls, onClose }) => {
  const [auditData, setAuditData] = useState<AuditTimelineData | null>(null);
  const [auditLoading, setAuditLoading] = useState<boolean>(false);
  const [auditError, setAuditError] = useState<string | null>(null);

  useEffect(() => {
    if (!customer) return;

    let active = true;

    fetchCustomerAudit(customer.customer_id, controls)
      .then((data) => {
        if (active) {
          setAuditData(data);
          setAuditLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (active) {
          setAuditError(err instanceof Error ? err.message : "Failed to load audit timeline");
          setAuditLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [customer, controls]);

  if (!customer) return null;

  return (
    <div className="drawer-overlay" onClick={onClose}>
      <div className="drawer-container" onClick={(e) => e.stopPropagation()}>
        {/* Drawer Header */}
        <div className="drawer-header">
          <div>
            <div className="drawer-tag">CUSTOMER AUDIT LINEAGE & EXPLAINABILITY</div>
            <h2 className="drawer-title">{customer.customer_id}</h2>
            <div className="drawer-meta text-secondary text-xs mt-1">
              Plan: <span className="text-primary font-bold">{customer.plan?.toUpperCase() || "PRO"}</span> • Provenance:{" "}
              <span className="text-blue font-bold">CUSTOMER OPERATIONAL STATE</span>
            </div>
          </div>
          <button type="button" className="drawer-close-btn" onClick={onClose} aria-label="Close drawer">
            ✕
          </button>
        </div>

        <div className="drawer-content">
          {/* STEP 1: RISK ENGINE (DETECT) */}
          <div className="drawer-step">
            <div className="step-badge">01</div>
            <div className="step-body">
              <div className="step-title">STAGE 1: RISK DETECTION & OBSERVABLE SIGNALS</div>
              <div className="metrics-grid-3">
                <div className="detail-box">
                  <div className="detail-label">RISK SCORE</div>
                  <div className="detail-value font-mono">{(customer.risk_score * 100).toFixed(1)}%</div>
                </div>
                <div className="detail-box">
                  <div className="detail-label">RISK TIER</div>
                  <div className="detail-value">
                    <span className={`badge tier-${customer.risk_tier.toLowerCase()}`}>
                      {customer.risk_tier}
                    </span>
                  </div>
                </div>
                <div className="detail-box">
                  <div className="detail-label">REVENUE AT RISK</div>
                  <div className="detail-value font-mono">{formatINR(customer.revenue_at_risk)}</div>
                </div>
              </div>

              {customer.risk_signals && (
                <div className="signals-box mt-2">
                  <div className="detail-label mb-1">OBSERVABLE BEHAVIOR SIGNALS</div>
                  <div className="signals-grid">
                    {Object.entries(customer.risk_signals).map(([sigKey, sigVal]) => (
                      <div key={sigKey} className={`signal-chip ${sigVal ? "signal-active" : "signal-inactive"}`}>
                        <span className="signal-dot">{sigVal ? "●" : "○"}</span>
                        <span>{sigKey.replace(/_/g, " ")}: <strong>{sigVal ? "YES" : "NO"}</strong></span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* STEP 2: DIAGNOSIS ENGINE (DIAGNOSE) */}
          <div className="drawer-step">
            <div className="step-badge">02</div>
            <div className="step-body">
              <div className="step-title">STAGE 2: ROOT-CAUSE DIAGNOSIS & AI GROUNDING</div>
              <div className="metrics-grid-3 mb-2">
                <div className="detail-box">
                  <div className="detail-label">DIAGNOSIS CATEGORY</div>
                  <div className="detail-value font-highlight">{customer.diagnosis}</div>
                </div>
                <div className="detail-box">
                  <div className="detail-label">CONFIDENCE</div>
                  <div className="detail-value font-mono">{(customer.diagnosis_confidence * 100).toFixed(0)}%</div>
                </div>
                <div className="detail-box">
                  <div className="detail-label">ACTIONABILITY</div>
                  <div className="detail-value">
                    <span className={`badge actionability-${(customer.actionability || "candidate").toLowerCase()}`}>
                      {customer.actionability || "CANDIDATE"}
                    </span>
                  </div>
                </div>
              </div>

              <div className="metrics-grid-2">
                <div className="detail-box">
                  <div className="detail-label">AI INTELLIGENCE STATUS</div>
                  <div className="detail-value">
                    <span className={`badge status-${customer.ai_status.toLowerCase()}`}>
                      {customer.ai_status} ({(customer.ai_confidence * 100).toFixed(0)}%)
                    </span>
                  </div>
                </div>
                <div className="detail-box">
                  <div className="detail-label">FALLBACK HEURISTIC USED</div>
                  <div className="detail-value font-mono">
                    <span className={`badge fallback-${customer.fallback_used ? "true" : "false"}`}>
                      {customer.fallback_used ? "YES (HEURISTIC)" : "NO (MODEL)"}
                    </span>
                  </div>
                </div>
              </div>

              {customer.evidence_event_ids && customer.evidence_event_ids.length > 0 && (
                <div className="reason-box mt-2">
                  <div className="reason-label">SUPPORTING EVIDENCE EVENT IDS</div>
                  <div className="evidence-tags">
                    {customer.evidence_event_ids.map((id) => (
                      <span key={id} className="evidence-tag font-mono">
                        {id}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* STEP 3: DECISION COMPARISON (DECIDE) */}
          <div className="drawer-step">
            <div className="step-badge">03</div>
            <div className="step-body">
              <div className="step-title">STAGE 3: CANDIDATE INTERVENTIONS & EXPECTED VALUE</div>
              <div className="decision-callout mb-2">
                <div className="detail-label">SELECTED ACTION</div>
                <div className="decision-hero font-bold text-success">
                  {customer.selected_action} <span className="text-secondary font-mono text-sm">(EV: {formatINR(customer.expected_value)})</span>
                </div>
                <div className="reason-text text-sm text-secondary mt-1">{customer.decision_reason}</div>
              </div>

              {customer.candidate_actions && customer.candidate_actions.length > 0 && (
                <div className="candidates-table-wrap">
                  <table className="candidates-table">
                    <thead>
                      <tr>
                        <th>Candidate Action</th>
                        <th>Expected Value</th>
                        <th>Recov Prob</th>
                        <th>Cost</th>
                        <th>Eligibility</th>
                        <th>Decision</th>
                      </tr>
                    </thead>
                    <tbody>
                      {customer.candidate_actions.map((act) => (
                        <tr key={act.action} className={act.selected ? "candidate-selected" : ""}>
                          <td className="font-bold">{act.action}</td>
                          <td className="font-mono">{formatINR(act.expected_value)}</td>
                          <td className="font-mono">{(act.recovery_probability * 100).toFixed(1)}%</td>
                          <td className="font-mono">{formatINR(act.direct_cost)}</td>
                          <td>
                            <span className={`badge status-${act.eligible ? "eligible" : "ineligible"}`}>
                              {act.eligible ? "ELIGIBLE" : "INELIGIBLE"}
                            </span>
                          </td>
                          <td>
                            {act.selected ? (
                              <span className="badge badge-success">SELECTED</span>
                            ) : (
                              <span className="rejection-text">{act.rejection_reason || "Not Selected"}</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>

          {/* STEP 4: POLICY GUARDRAILS (GUARD) */}
          <div className="drawer-step">
            <div className="step-badge">04</div>
            <div className="step-body">
              <div className="step-title">STAGE 4: DETERMINISTIC POLICY GATE & GOVERNANCE</div>
              <div className="policy-architecture-banner">
                <span>AI Recommends</span> → <strong className="text-purple">Deterministic Policy Authorizes</strong> → <span>Execution Acts</span>
              </div>
              <div className="metrics-grid-3 mt-2">
                <div className="detail-box">
                  <div className="detail-label">POLICY STATUS</div>
                  <div className="detail-value">
                    <span className={`badge status-${customer.eligibility_status.toLowerCase()}`}>
                      {customer.eligibility_status}
                    </span>
                  </div>
                </div>
                <div className="detail-box">
                  <div className="detail-label">POLICY VERSION</div>
                  <div className="detail-value font-mono text-xs">{customer.policy_version || "Phase 5 Bounded EV v1.0"}</div>
                </div>
                <div className="detail-box">
                  <div className="detail-label">RECOVERY ASSUMPTION</div>
                  <div className="detail-value font-mono text-xs">{customer.assumption_version || "v1.0"}</div>
                </div>
              </div>
            </div>
          </div>

          {/* STEP 5: EXECUTION (EXECUTE) */}
          <div className="drawer-step">
            <div className="step-badge">05</div>
            <div className="step-body">
              <div className="step-title">STAGE 5: EXECUTION ENGINE & DISPATCH</div>
              <div className="metrics-grid-2">
                <div className="detail-box">
                  <div className="detail-label">EXECUTION STATUS</div>
                  <div className="detail-value">
                    <span className={`badge exec-${customer.execution_status.toLowerCase()}`}>
                      {customer.execution_status}
                    </span>
                  </div>
                </div>
                <div className="detail-box">
                  <div className="detail-label">TARGET DISPATCHER</div>
                  <div className="detail-value font-mono text-sm">
                    {customer.selected_action === "PAYMENT_RECOVERY"
                      ? "Razorpay Sandbox Dispatcher"
                      : customer.selected_action === "NO_ACTION"
                      ? "None (Governed Stop)"
                      : "Operator Notification Queue"}
                  </div>
                </div>
              </div>

              {customer.failure_reason && (
                <div className="reason-box warning-box mt-2">
                  <div className="reason-label">EXECUTION DETAILS / REASON</div>
                  <div className="reason-text text-warning">{customer.failure_reason}</div>
                </div>
              )}
            </div>
          </div>

          {/* STEP 6 & 7: OUTCOME & ATTRIBUTION */}
          <div className="drawer-step">
            <div className="step-badge">06</div>
            <div className="step-body">
              <div className="step-title">STAGE 8 & 9: OUTCOME OBSERVATION & FINANCIAL ATTRIBUTION</div>
              <div className="metrics-grid-3 mb-2">
                <div className="detail-box">
                  <div className="detail-label">OBSERVED OUTCOME</div>
                  <div className="detail-value">
                    <span className={`badge outcome-${(customer.outcome || "unknown").toLowerCase()}`}>
                      {customer.outcome || "PENDING"}
                    </span>
                  </div>
                </div>
                <div className="detail-box">
                  <div className="detail-label">ATTRIBUTION STATUS</div>
                  <div className="detail-value">
                    <span className={`badge attr-${(customer.attribution_status || "unattributed").toLowerCase()}`}>
                      {customer.attribution_status || "UNATTRIBUTED"}
                    </span>
                  </div>
                </div>
                <div className="detail-box">
                  <div className="detail-label">NET RECOVERED REVENUE</div>
                  <div className="detail-value font-mono font-bold text-success">
                    {formatINR(customer.net_recovered_revenue)}
                  </div>
                </div>
              </div>

              {customer.payment_reference && (
                <div className="detail-box mb-2">
                  <div className="detail-label">PAYMENT REFERENCE</div>
                  <div className="detail-value font-mono text-sm text-cyan">{customer.payment_reference}</div>
                </div>
              )}
            </div>
          </div>

          {/* STEP 8: 9-STAGE CHRONOLOGICAL AUDIT TIMELINE */}
          <div className="drawer-step">
            <div className="step-badge">07</div>
            <div className="step-body">
              <div className="step-title">COMPLETE 9-STAGE CHRONOLOGICAL AUDIT TRAIL</div>

              {auditLoading && <div className="text-secondary text-sm font-mono">Loading 9-stage audit lineage...</div>}
              {auditError && <div className="text-rose text-sm font-mono">{auditError}</div>}

              {auditData && (
                <div className="timeline-container mt-2">
                  <div className="timeline-meta mb-2 text-xs text-secondary">
                    Total Stages: <span className="text-white font-bold">{auditData.total_stages}</span> • Completed:{" "}
                    <span className="text-success font-bold">{auditData.completed_stages}</span> • Final State:{" "}
                    <span className="text-cyan font-bold">{auditData.final_status}</span>
                  </div>

                  <div className="timeline-steps">
                    {auditData.stages.map((stg) => (
                      <div key={stg.stage_index} className={`timeline-node status-${stg.status.toLowerCase().replace(/_/g, "-").replace(/ /g, "-")}`}>
                        <div className="timeline-node-header">
                          <div className="timeline-node-index">{stg.stage_index}</div>
                          <div className="timeline-node-name">{stg.stage_name}</div>
                          <span className={`badge stage-badge-${stg.status.toLowerCase().replace(/_/g, "-").replace(/ /g, "-")}`}>
                            {stg.status}
                          </span>
                          {stg.timestamp && <div className="timeline-node-time">{stg.timestamp}</div>}
                        </div>
                        <div className="timeline-node-summary text-sm">{stg.summary}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
