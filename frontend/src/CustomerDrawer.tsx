import React from "react";
import type { CustomerEvidenceRecord } from "./types";
import { formatINR } from "./utils";

interface CustomerDrawerProps {
  customer: CustomerEvidenceRecord | null;
  onClose: () => void;
}

export const CustomerDrawer: React.FC<CustomerDrawerProps> = ({ customer, onClose }) => {
  if (!customer) return null;

  return (
    <div className="drawer-overlay" onClick={onClose}>
      <div className="drawer-container" onClick={(e) => e.stopPropagation()}>
        {/* Drawer Header */}
        <div className="drawer-header">
          <div>
            <div className="drawer-tag">CUSTOMER AUDIT LINEAGE</div>
            <h2 className="drawer-title">{customer.customer_id}</h2>
          </div>
          <button type="button" className="drawer-close-btn" onClick={onClose} aria-label="Close drawer">
            ✕
          </button>
        </div>

        <div className="drawer-content">
          {/* STEP 1: RISK ENGINE */}
          <div className="drawer-step">
            <div className="step-badge">01</div>
            <div className="step-body">
              <div className="step-title">RISK ENGINE (PHASE 3)</div>
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
            </div>
          </div>

          {/* STEP 2: DIAGNOSIS ENGINE */}
          <div className="drawer-step">
            <div className="step-badge">02</div>
            <div className="step-body">
              <div className="step-title">DIAGNOSIS ENGINE (PHASE 4)</div>
              <div className="metrics-grid-2">
                <div className="detail-box">
                  <div className="detail-label">DETERMINISTIC DIAGNOSIS</div>
                  <div className="detail-value font-highlight">{customer.diagnosis}</div>
                </div>
                <div className="detail-box">
                  <div className="detail-label">DIAGNOSIS CONFIDENCE</div>
                  <div className="detail-value font-mono">{(customer.diagnosis_confidence * 100).toFixed(0)}%</div>
                </div>
              </div>
            </div>
          </div>

          {/* STEP 3: AI SERVICE & GROUNDING */}
          <div className="drawer-step">
            <div className="step-badge">03</div>
            <div className="step-body">
              <div className="step-title">AI INTELLIGENCE & GROUNDING (PHASE 8)</div>
              <div className="metrics-grid-3">
                <div className="detail-box">
                  <div className="detail-label">AI STATUS</div>
                  <div className="detail-value">
                    <span className={`badge status-${customer.ai_status.toLowerCase()}`}>
                      {customer.ai_status}
                    </span>
                  </div>
                </div>
                <div className="detail-box">
                  <div className="detail-label">AI CONFIDENCE</div>
                  <div className="detail-value font-mono">{(customer.ai_confidence * 100).toFixed(0)}%</div>
                </div>
                <div className="detail-box">
                  <div className="detail-label">FALLBACK USED</div>
                  <div className="detail-value">
                    <span className={`badge fallback-${customer.fallback_used ? "true" : "false"}`}>
                      {customer.fallback_used ? "YES" : "NO"}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* STEP 4: INTERVENTION POLICY */}
          <div className="drawer-step">
            <div className="step-badge">04</div>
            <div className="step-body">
              <div className="step-title">INTERVENTION POLICY (PHASE 5)</div>
              <div className="metrics-grid-3 mb-2">
                <div className="detail-box">
                  <div className="detail-label">ELIGIBILITY STATUS</div>
                  <div className="detail-value">
                    <span className={`badge status-${customer.eligibility_status.toLowerCase()}`}>
                      {customer.eligibility_status}
                    </span>
                  </div>
                </div>
                <div className="detail-box">
                  <div className="detail-label">SELECTED ACTION</div>
                  <div className="detail-value font-highlight">{customer.selected_action}</div>
                </div>
                <div className="detail-box">
                  <div className="detail-label">EXPECTED VALUE</div>
                  <div className="detail-value font-mono">{formatINR(customer.expected_value)}</div>
                </div>
              </div>
              <div className="reason-box">
                <div className="reason-label">POLICY DECISION REASON</div>
                <div className="reason-text">{customer.decision_reason}</div>
              </div>
            </div>
          </div>

          {/* STEP 5: EXECUTION ENGINE */}
          <div className="drawer-step">
            <div className="step-badge">05</div>
            <div className="step-body">
              <div className="step-title">EXECUTION ENGINE & DISPATCH (PHASE 6 & 9)</div>
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
                  <div className="detail-label">DISPATCH TARGET</div>
                  <div className="detail-value font-mono text-sm">
                    {customer.selected_action === "PAYMENT_RECOVERY" ? "Razorpay Sandbox Dispatcher" : "No Dispatch Needed"}
                  </div>
                </div>
              </div>
              {customer.failure_reason && (
                <div className="reason-box warning-box mt-2">
                  <div className="reason-label">DISPATCH RESULT DETAILS</div>
                  <div className="reason-text text-warning">{customer.failure_reason}</div>
                </div>
              )}
            </div>
          </div>

          {/* STEP 6: OUTCOME RESOLUTION */}
          <div className="drawer-step">
            <div className="step-badge">06</div>
            <div className="step-body">
              <div className="step-title">OUTCOME RESOLUTION (PHASE 7)</div>
              <div className="metrics-grid-2">
                <div className="detail-box">
                  <div className="detail-label">RESOLVED OUTCOME</div>
                  <div className="detail-value">
                    <span className={`badge outcome-${(customer.outcome || "unknown").toLowerCase()}`}>
                      {customer.outcome || "PENDING"}
                    </span>
                  </div>
                </div>
                <div className="detail-box">
                  <div className="detail-label">OUTCOME CONFIDENCE</div>
                  <div className="detail-value font-mono">
                    {customer.outcome_confidence !== null && customer.outcome_confidence !== undefined
                      ? `${(customer.outcome_confidence * 100).toFixed(0)}%`
                      : "N/A"}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* STEP 7: REVENUE ATTRIBUTION */}
          <div className="drawer-step">
            <div className="step-badge">07</div>
            <div className="step-body">
              <div className="step-title">REVENUE ATTRIBUTION & ACCOUNTING (PHASE 7)</div>
              <div className="metrics-grid-3 mb-2">
                <div className="detail-box">
                  <div className="detail-label">ATTRIBUTION STATUS</div>
                  <div className="detail-value">
                    <span className={`badge attr-${(customer.attribution_status || "unattributed").toLowerCase()}`}>
                      {customer.attribution_status || "UNATTRIBUTED"}
                    </span>
                  </div>
                </div>
                <div className="detail-box">
                  <div className="detail-label">ATTRIBUTABLE REVENUE</div>
                  <div className="detail-value font-mono">{formatINR(customer.attributable_revenue)}</div>
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

              {customer.evidence_event_ids && customer.evidence_event_ids.length > 0 && (
                <div className="reason-box">
                  <div className="reason-label">EVIDENCE EVENT IDS</div>
                  <div className="evidence-tags">
                    {customer.evidence_event_ids.map((id) => (
                      <span key={id} className="evidence-tag">
                        {id}
                      </span>
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
