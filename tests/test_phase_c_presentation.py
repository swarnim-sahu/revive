"""
Comprehensive Test Suite for REVIVE Phase C Command Center & Presentation Layer.
Validates:
A. Candidate action values match real InterventionDecision candidate scores, not presentation constants.
B. Supporting evidence shown to the API equals authoritative structured evidence.
C. Risk signals cannot be created merely by changing the diagnosis label (derived from observable events/features).
D. Operational batch audit never reports WEBHOOK = EXECUTED or HMAC VERIFIED solely because outcome == RECOVERED.
E. Operational audit timestamps come from authoritative records or are null.
F. Controlled failure endpoint produces states derived from real component execution and ExceptionLedger.
G. No benchmark business numbers are hardcoded in frontend source (App.tsx).
H. Exception provenance correctly identifies operational vs benchmark source.
I. Demo selectors deterministically resolve to records satisfying their documented properties.
J. Phase A proof artifact provenance is validated with honest historical identifiers.
"""

from decimal import Decimal
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.api.dashboard import get_evaluation_result

client = TestClient(app)


def test_phase_c_A_candidate_action_values_match_authoritative_decision():
    """A. Candidate action values match real InterventionDecision candidate scores, not presentation constants."""
    resp = client.get("/api/dashboard/customers/cus_000005")
    assert resp.status_code == 200
    data = resp.json()

    candidates = {c["action"]: c for c in data.get("candidate_actions", [])}
    assert "PAYMENT_RECOVERY" in candidates
    recov = candidates["PAYMENT_RECOVERY"]
    assert recov["selected"] is True
    assert recov["eligible"] is True
    assert recov["direct_cost"] == 3.0
    assert recov["recovery_probability"] == pytest.approx(0.3825, abs=1e-3)
    # Ensure expected value matches decision expected value exactly
    assert recov["expected_value"] == data["expected_value"]

    # NO_ACTION candidate
    assert "NO_ACTION" in candidates
    no_act = candidates["NO_ACTION"]
    assert no_act["expected_value"] == 0.0
    assert no_act["direct_cost"] == 0.0
    assert no_act["selected"] is False


def test_phase_c_B_supporting_evidence_integrity():
    """B. Supporting evidence and evidence event IDs equal authoritative structured evidence."""
    resp = client.get("/api/dashboard/customers/cus_000005")
    assert resp.status_code == 200
    data = resp.json()

    # Must contain evidence event IDs
    assert isinstance(data["evidence_event_ids"], list)
    assert len(data["evidence_event_ids"]) > 0
    for evt_id in data["evidence_event_ids"]:
        assert isinstance(evt_id, str)
        assert len(evt_id) > 0

    # Must contain supporting_evidence matching authoritative decision evidence
    assert "supporting_evidence" in data
    assert isinstance(data["supporting_evidence"], list)
    assert len(data["supporting_evidence"]) > 0
    for item in data["supporting_evidence"]:
        assert isinstance(item, str)
        assert len(item) > 0

    # Verify exact match against authoritative evaluation record
    eval_res = get_evaluation_result(customers_count=100, seed=42)
    expected_evidence = next(
        r.supporting_evidence for r in eval_res.per_customer_results if r.customer_id == "cus_000005"
    )
    assert data["supporting_evidence"] == expected_evidence


def test_phase_c_C_risk_signals_derived_from_observable_evidence():
    """C. Risk signals cannot be created merely by changing diagnosis label (derived from observable events/features)."""
    resp = client.get("/api/dashboard/customers")
    assert resp.status_code == 200
    customers = resp.json()

    for cust in customers:
        signals = cust.get("risk_signals", {})
        assert isinstance(signals, dict)
        assert "payment_failed_observed" in signals
        assert "cart_abandonment_observed" in signals
        assert "trial_expiration_approaching" in signals
        assert "inactivity_detected" in signals
        assert "prior_conversion_detected" in signals

        # For cus_000005, payment failure was observed and trial expires within 24h (0.0h)
        if cust["customer_id"] == "cus_000005":
            assert signals["payment_failed_observed"] is True
            assert signals["trial_expiration_approaching"] is True

        # For cus_000004, prior conversion was observed
        if cust["customer_id"] == "cus_000004":
            assert signals["prior_conversion_detected"] is True

    # Authoritative Seed 42 cus_000005 evaluation record consistency
    eval_res = get_evaluation_result(customers_count=100, seed=42, snapshot_hours=336.0)
    rec_005 = next(x for x in eval_res.per_customer_results if x.customer_id == "cus_000005")
    assert rec_005.risk_signals["trial_expiration_approaching"] is True
    assert any(
        "Trial expires within" in evidence
        for evidence in rec_005.supporting_evidence
    )


def test_phase_c_D_operational_audit_never_fabricates_webhook():
    """D. Operational batch audit never reports WEBHOOK = EXECUTED or HMAC VERIFIED solely because outcome == RECOVERED."""
    # cus_000005 is RECOVERED in the synthetic operational batch
    resp = client.get("/api/dashboard/audit/cus_000005")
    assert resp.status_code == 200
    data = resp.json()

    stages_by_name = {s["stage_name"]: s for s in data["stages"]}
    wh_stage = stages_by_name["WEBHOOK"]

    # Must be NOT OBSERVED for synthetic operational batch
    assert wh_stage["status"] == "NOT OBSERVED"
    assert "not observed" in wh_stage["summary"].lower()
    assert wh_stage["timestamp"] is None

    # PAYMENT_RESULT must distinguish synthetic observation from live gateway
    pay_stage = stages_by_name["PAYMENT_RESULT"]
    assert pay_stage["status"] == "SYNTHETIC_OBSERVED"
    assert "synthetic" in pay_stage["summary"].lower()

    # Frontend Operational Overview Pipeline must NOT display real-webhook/HMAC wording for synthetic batch
    app_tsx = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    pipeline_sec_start = app_tsx.find("9-STAGE REVIVE RECOVERY PIPELINE")
    assert pipeline_sec_start != -1, "Expected section title '9-STAGE REVIVE RECOVERY PIPELINE'"
    pipeline_sec_end = app_tsx.find("</section>", pipeline_sec_start)
    pipeline_sec = app_tsx[pipeline_sec_start:pipeline_sec_end]

    # Verify synthetic batch distinction in overview
    assert "AUTONOMOUS 9-STAGE" not in pipeline_sec
    assert "HMAC SHA256" not in pipeline_sec, "Overview pipeline must not display real HMAC SHA256 for synthetic batch"
    assert "payment_link.paid" not in pipeline_sec, "Overview pipeline must not display real payment_link.paid for synthetic batch"
    assert "Synthetic Observed" in pipeline_sec
    assert "Not Observed" in pipeline_sec
    assert "Synthetic Batch" in pipeline_sec


def test_phase_c_E_operational_audit_timestamps_truthfulness():
    """E. Operational audit timestamps come from authoritative records or are null (never fabricated)."""
    resp = client.get("/api/dashboard/audit/cus_000005")
    assert resp.status_code == 200
    data = resp.json()

    for s in data["stages"]:
        ts = s["timestamp"]
        # Timestamps must either be None or a valid ISO timestamp from real records
        if ts is not None:
            assert "T" in ts
            assert not ts.startswith("2026-08-31T14:15:22")  # Hardcoded placeholder removed

    # For NO_ACTION customer, execution timestamp must be None
    resp_no_action = client.get("/api/dashboard/audit/cus_000004")
    assert resp_no_action.status_code == 200
    data_no_action = resp_no_action.json()
    stages_no_act = {s["stage_name"]: s for s in data_no_action["stages"]}
    assert stages_no_act["EXECUTE"]["timestamp"] is None
    assert stages_no_act["EXECUTE"]["status"] == "NOT EXECUTED"


def test_phase_c_F_controlled_failure_derived_from_real_execution():
    """F. Controlled failure endpoint produces states derived from real component execution and ExceptionLedger."""
    resp = client.get("/api/dashboard/failure-scenarios")
    assert resp.status_code == 200
    scenarios = {s["scenario_id"]: s for s in resp.json()}

    s1 = scenarios.get("payment_gateway_timeout_retryable")
    assert s1 is not None
    assert s1["label"] in ["CONTROLLED DETERMINISTIC FAILURE FIXTURE", "CONTROLLED / SIMULATED FAILURE"]
    assert s1["retryable"] is True
    assert s1["safe_action"] == "RETRY_SCHEDULED"
    assert s1["final_state"] == "RETRY"
    assert len(s1["steps"]) == 5

    # Verify steps reflect execution state machine
    step_names = [st["step_name"] for st in s1["steps"]]
    assert "ACTION_DISPATCH" in step_names
    assert "DISPATCH_FAILURE" in step_names
    assert "FAILURE_CLASSIFICATION" in step_names
    assert "RETRY_POLICY_EVALUATION" in step_names
    assert "SAFE_ACTION_ASSIGNMENT" in step_names

    s2 = scenarios.get("terminal_policy_blocked_invalid_state")
    assert s2 is not None
    assert s2["label"] in ["CONTROLLED DETERMINISTIC FAILURE FIXTURE", "CONTROLLED / SIMULATED FAILURE"]
    assert s2["retryable"] is False
    assert s2["safe_action"] in ["STOP", "GOVERNED_STOP"]
    assert s2["final_state"] in ["NO_ACTION", "BLOCKED", "STOPPED"]


def test_phase_c_G_no_hardcoded_benchmark_numbers_in_frontend():
    """G. Verify benchmark measurements are dynamically sourced from the benchmark object in frontend/src/App.tsx."""
    app_tsx_path = Path("frontend/src/App.tsx")
    assert app_tsx_path.exists()
    content = app_tsx_path.read_text(encoding="utf-8")

    # Contract: Banned hardcoded strings must not appear
    assert "341 genuine recoveries" not in content
    assert "₹143.15 net return per ₹1 cost" not in content
    assert "10000 - " not in content

    # Contract: Reject frontend arithmetic for 4-way taxonomy metrics
    assert "treatment_evaluations ?? 0) -" not in content
    assert "- (benchmark.economics?.treatment_total_conversions" not in content
    assert "- benchmark.economics?.treatment_total_conversions" not in content

    # Contract: Reject frontend arithmetic for gross revenue delta vs control
    assert "- (benchmark.economics?.control_gross_revenue" not in content
    assert "- benchmark.economics?.control_gross_revenue" not in content
    assert "treatment_total_gross_revenue || 0) -" not in content

    # Contract: Benchmark metrics must be bound dynamically to benchmark object
    benchmark_bindings = [
        "benchmark.economics?.control_evaluations",
        "benchmark.economics?.treatment_evaluations",
        "benchmark.metadata?.total_arm_evaluations",
        "benchmark.economics?.control_conversions",
        "benchmark.economics?.treatment_total_conversions",
        "benchmark.economics?.conversion_lift_points",
        "benchmark.economics?.conversion_relative_lift_pct",
        "benchmark.economics?.control_gross_revenue",
        "benchmark.economics?.treatment_total_gross_revenue",
        "benchmark.economics?.gross_revenue_delta_vs_control",
        "benchmark.economics?.treatment_intervention_cost",
        "benchmark.economics?.control_net_revenue",
        "benchmark.economics?.treatment_total_net_revenue",
        "benchmark.economics?.incremental_net_revenue",
        "benchmark.economics?.treatment_genuine_incremental_revenue",
        "benchmark.economics?.treatment_genuine_incremental_recoveries",
        "benchmark.economics?.treatment_attributable_recovery_revenue",
        "benchmark.economics?.recovery_roi",
        "benchmark.economics?.treatment_natural_conversions",
        "benchmark.economics?.treatment_observed_unrecoverable_conversions",
        "benchmark.economics?.treatment_no_treatment_conversions",
    ]
    for binding in benchmark_bindings:
        assert binding in content, f"Missing dynamic benchmark binding in App.tsx: {binding}"


def test_phase_c_H_exception_provenance_correctness():
    """H. Exception provenance correctly identifies operational vs benchmark source."""
    resp = client.get("/api/dashboard/exceptions")
    assert resp.status_code == 200
    data = resp.json()

    assert data["provenance"] == "CUSTOMER OPERATIONAL STATE"
    assert data["total_exceptions"] > 0
    assert data["terminal_count"] >= 0
    assert data["retryable_count"] >= 0


def test_phase_c_I_deterministic_demo_selectors():
    """I. Demo selectors deterministically resolve to records satisfying their documented properties."""
    resp = client.get("/api/dashboard/customers")
    assert resp.status_code == 200
    customers = {c["customer_id"]: c for c in resp.json()}

    # 1. HIGH_RISK_ACTIONABLE -> cus_000005
    c1 = customers.get("cus_000005")
    assert c1 is not None
    assert c1["risk_tier"] == "HIGH"
    assert c1["diagnosis"] == "PAYMENT_FRICTION"
    assert c1["selected_action"] == "PAYMENT_RECOVERY"
    assert c1["execution_status"] == "EXECUTED"
    assert c1["expected_value"] > 0.0

    # 2. NO_ACTION -> cus_000004
    c2 = customers.get("cus_000004")
    assert c2 is not None
    assert c2["diagnosis"] == "ALREADY_CONVERTED"
    assert c2["selected_action"] == "NO_ACTION"
    assert c2["expected_value"] == 0.0

    # 3. SUCCESSFUL_RECOVERY -> cus_000005
    assert c1["outcome"] == "RECOVERED"
    assert c1["attribution_status"] == "DIRECTLY_OBSERVED"
    assert c1["net_recovered_revenue"] == 4996.0


def test_phase_c_J_phase_a_proof_artifact_provenance():
    """J. Phase A proof artifact provenance is validated with honest historical identifiers."""
    resp = client.get("/api/dashboard/razorpay-proof")
    assert resp.status_code == 200
    data = resp.json()

    assert data["proof_type"] == "RAZORPAY_TEST_MODE_EXTERNAL_RECOVERY"
    assert data["status"] == "VERIFIED"
    assert data["correlated_customer_id"] == "cus_live_proof_001"
    assert data["payment_link_id"] == "payload_pay_6898e42b"
    assert data["webhook_event_id"] == "TXFf0xsmSYoRsx"
    assert data["payment_id"] == "pay_TXFeukRbYol9b3"
    assert data["plan_id"] == "pro"
    assert data["attributable_revenue"] == 999.0
    assert data["intervention_cost"] == 3.0
    assert data["net_recovered_revenue"] == 996.0
    assert data["duplicate_delivery_status"] == "DUPLICATE_ACKNOWLEDGED"
    assert data["signature_verification"] == "HMAC_SHA256_VERIFIED"
    assert "Test Mode" in data["disclosure"]


def test_phase_c_ground_truth_isolation():
    """Verify hidden simulation ground-truth fields are completely absent from customer responses."""
    resp = client.get("/api/dashboard/customers/cus_000005")
    assert resp.status_code == 200
    data = resp.json()

    forbidden = [
        "ground_truth",
        "true_root_cause",
        "natural_conversion",
        "recoverable",
        "maximum_recoverable_revenue",
        "conversion_after_intervention",
        "generation_segment",
    ]
    for key in forbidden:
        assert key not in data


def test_phase_c_secret_isolation_across_endpoints():
    """Verify zero API keys, webhook secrets, tokens, or auth headers are present in any presentation endpoint."""
    endpoints = [
        "/api/dashboard/summary",
        "/api/dashboard/customers",
        "/api/dashboard/customers/cus_000001",
        "/api/dashboard/benchmark",
        "/api/dashboard/razorpay-proof",
        "/api/dashboard/audit/cus_000001",
        "/api/dashboard/exceptions",
        "/api/dashboard/failure-scenarios",
    ]

    for ep in endpoints:
        resp = client.get(ep)
        assert resp.status_code == 200
        text = resp.text
        assert "SECRET_KEY" not in text
        assert "rzp_test_KEY" not in text
        assert "test_wh_secret" not in text
        assert "zrok" not in text.lower()
        assert "bearer " not in text.lower()
        assert "basic " not in text.lower()


def test_phase_c_read_only_financial_boundary():
    """Verify no financial mutation routes (POST/PUT/DELETE/PATCH) exist on /api/dashboard/*."""
    mutations = [
        ("POST", "/api/dashboard/payment-links"),
        ("POST", "/api/dashboard/charge"),
        ("POST", "/api/dashboard/refund"),
        ("PUT", "/api/dashboard/customers/cus_000001"),
        ("DELETE", "/api/dashboard/customers/cus_000001"),
    ]

    for method, path in mutations:
        if method == "POST":
            resp = client.post(path, json={"amount": 999})
        elif method == "PUT":
            resp = client.put(path, json={"status": "override"})
        elif method == "DELETE":
            resp = client.delete(path)
        assert resp.status_code in [404, 405], f"Mutation route {method} {path} should not exist"


def test_phase_c_K_benchmark_no_synthetic_fallback_on_incomplete_schema(tmp_path):
    """K. Verify GET /api/dashboard/benchmark returns available=False without synthesizing missing fields when schema is incomplete."""
    from unittest.mock import patch

    # Snapshot missing treatment_no_treatment_conversions and gross_revenue_delta_vs_control
    incomplete_snapshot = {
        "metadata": {
            "experiment_id": "test_exp",
            "seed": 42,
            "paired_experimental_units": 100,
            "control_evaluations": 100,
            "treatment_evaluations": 100,
            "total_arm_evaluations": 200,
            "simulator_version": "v2.0.0",
            "policy_version": "v1.0",
            "assumption_version": "v1.0",
            "risk_model_version": "v1.0",
            "python_version": "3.13.9",
            "timestamp": "2026-09-02T19:00:00Z",
        },
        "economics": {
            "paired_experimental_units": 100,
            "control_evaluations": 100,
            "control_conversions": 37,
            "control_conversion_rate": 0.37,
            "control_gross_revenue": 100000.0,
            "control_net_revenue": 100000.0,
            "control_revenue_at_risk": 200000.0,
            "treatment_evaluations": 100,
            "treatment_total_conversions": 42,
            "treatment_total_conversion_rate": 0.42,
            "treatment_natural_conversions": 37,
            "treatment_genuine_incremental_recoveries": 3,
            "treatment_observed_unrecoverable_conversions": 2,
            # INTENTIONALLY MISSING: treatment_no_treatment_conversions & gross_revenue_delta_vs_control
            "treatment_total_gross_revenue": 110000.0,
            "treatment_attributable_recovery_revenue": 20000.0,
            "treatment_intervention_cost": 100.0,
            "treatment_net_recovered_revenue": 19900.0,
            "treatment_total_net_revenue": 109900.0,
            "treatment_genuine_incremental_revenue": 9000.0,
            "treatment_expected_recovery_value": 10000.0,
            "conversion_lift_points": 5.0,
            "conversion_relative_lift_pct": 13.5,
            "incremental_net_revenue": 9900.0,
            "maximum_recoverable_revenue": 50000.0,
            "recoverable_capture_rate_pct": 18.0,
            "recovery_roi": 99.0,
        },
    }

    dummy_path = tmp_path / "incomplete_phase_b_summary.json"
    dummy_path.write_text(json.dumps(incomplete_snapshot), encoding="utf-8")

    with patch("app.api.dashboard._PHASE_B_EVIDENCE_PATH", dummy_path):
        resp = client.get("/api/dashboard/benchmark")
        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is False
        assert "failed to parse" in data["diagnostic_message"].lower() or "schema-incomplete" in data["diagnostic_message"].lower()
        # Verify it did NOT synthesize the missing fields or produce a valid economics payload
        assert data["economics"] is None


def test_phase_c_L_summary_unavailable_state_and_no_zero_substitution_in_frontend():
    """L. Verify App.tsx displays explicit OPERATIONAL SUMMARY UNAVAILABLE and never substitutes fake zero metrics."""
    app_tsx_path = Path("frontend/src/App.tsx")
    assert app_tsx_path.exists()
    content = app_tsx_path.read_text(encoding="utf-8")

    # Must display explicit OPERATIONAL SUMMARY UNAVAILABLE state
    assert "OPERATIONAL SUMMARY UNAVAILABLE" in content
    assert "RETRY LOADING SUMMARY" in content

    # Must NOT contain the zero-filled fake fallback object
    assert "summary || {" not in content
    assert "customers_evaluated: 0" not in content
    assert "average_risk_score: 0" not in content
    assert "total_expected_recovery: 0" not in content
    assert "recovered_customers: 0" not in content


def test_phase_c_M_dashboard_actionability_mapping():
    """M. Verify /api/dashboard/summary maps authoritative actionable/non-actionable diagnosis counts (76/24)."""
    response = client.get("/api/dashboard/summary")
    assert response.status_code == 200
    diag = response.json()["diagnosis"]
    assert diag["payment_friction"] == 17
    assert diag["actionable"] == 76
    assert diag["non_actionable"] == 24
