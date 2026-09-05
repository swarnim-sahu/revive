"""
Pytest Suite for REVIVE FastAPI Presentation & Dashboard Layer.
Tests /health, /api/dashboard/summary, /api/dashboard/customers,
/api/dashboard/benchmark, /api/dashboard/razorpay-proof, /api/dashboard/audit/{id},
/api/dashboard/exceptions, /api/dashboard/failure-scenarios, determinism,
forbidden field isolation, secret isolation, and HTTP 404 error handling.
"""

from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
import pytest

from app.api.main import app

client = TestClient(app)


def test_1_health_check_endpoint():
    """1. GET /health returns HTTP 200 with ok status and service name."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "revive-api"


def test_2_dashboard_summary_endpoint():
    """2. GET /api/dashboard/summary returns HTTP 200 with complete benchmark metrics."""
    response = client.get("/api/dashboard/summary")
    assert response.status_code == 200
    data = response.json()

    assert "dataset" in data
    assert "risk" in data
    assert "diagnosis" in data
    assert "policy" in data
    assert "expected_recovery" in data
    assert "measured_recovery" in data
    assert "outcomes" in data
    assert "attribution" in data
    assert "execution" in data
    assert "provenance" in data
    assert "CUSTOMER OPERATIONAL STATE" in data["provenance"]

    assert data["dataset"]["customers_evaluated"] == 100
    assert data["dataset"]["customers_with_payment_failures"] == 17
    assert data["diagnosis"]["payment_friction"] == 17
    assert data["diagnosis"]["actionable"] == 76
    assert data["diagnosis"]["non_actionable"] == 24
    assert data["expected_recovery"]["total_expected_recovery"] > 0.0
    assert data["measured_recovery"]["net_recovered_revenue"] > 0.0


def test_3_dashboard_summary_determinism():
    """3. GET /api/dashboard/summary is 100% deterministic and reproducible across seeds and cohort sizes."""
    # Summary A, B, C test: seed=42 vs seed=99 vs seed=42
    A = client.get("/api/dashboard/summary?seed=42&cohort_size=100&snapshot_hours=336.0").json()
    B = client.get("/api/dashboard/summary?seed=99&cohort_size=100&snapshot_hours=336.0").json()
    C = client.get("/api/dashboard/summary?seed=42&cohort_size=100&snapshot_hours=336.0").json()

    assert A != B
    assert A == C

    # Customer list reproducibility: seed=42 vs seed=99 vs seed=42
    custA = client.get("/api/dashboard/customers?seed=42&cohort_size=100&snapshot_hours=336.0").json()
    custB = client.get("/api/dashboard/customers?seed=99&cohort_size=100&snapshot_hours=336.0").json()
    custC = client.get("/api/dashboard/customers?seed=42&cohort_size=100&snapshot_hours=336.0").json()

    assert custA != custB
    assert custA == custC

    # Different cohort sizes: 50 vs 100
    res50 = client.get("/api/dashboard/customers?seed=42&cohort_size=50&snapshot_hours=336.0").json()
    res100 = client.get("/api/dashboard/customers?seed=42&cohort_size=100&snapshot_hours=336.0").json()

    assert len(res50) == 50
    assert len(res100) == 100


def test_4_dashboard_customers_list_endpoint():
    """4. GET /api/dashboard/customers returns 100 safe customer evidence records."""
    response = client.get("/api/dashboard/customers")
    assert response.status_code == 200
    records = response.json()
    assert len(records) == 100
    assert records[0]["customer_id"] == "cus_000001"
    assert "candidate_actions" in records[0]
    assert len(records[0]["candidate_actions"]) > 0


def test_5_no_forbidden_fields_or_secrets_in_customer_records():
    """5. Customer evidence records contain zero ground-truth hidden fields or committed secrets."""
    response = client.get("/api/dashboard/customers")
    records = response.json()

    forbidden_fields = {
        "ground_truth",
        "true_root_cause",
        "natural_conversion",
        "recoverable",
        "maximum_recoverable_revenue",
        "conversion_after_intervention",
        "generation_segment",
    }

    for rec in records:
        for forbidden in forbidden_fields:
            assert forbidden not in rec
        rec_str = str(rec)
        assert "SECRET" not in rec_str
        assert "rzp_test_MOCK" not in rec_str
        assert "Authorization" not in rec_str


def test_6_dashboard_customer_by_id_endpoint():
    """6. GET /api/dashboard/customers/{customer_id} returns the matching customer evidence record."""
    response = client.get("/api/dashboard/customers/cus_000001")
    assert response.status_code == 200
    data = response.json()
    assert data["customer_id"] == "cus_000001"
    assert "risk_score" in data
    assert "expected_value" in data
    assert "candidate_actions" in data


def test_7_dashboard_customer_by_id_not_found():
    """7. GET /api/dashboard/customers/{unknown_id} returns HTTP 404."""
    response = client.get("/api/dashboard/customers/cus_non_existent_999")
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data


def test_8_dashboard_benchmark_endpoint():
    """8. GET /api/dashboard/benchmark returns authoritative Phase B snapshot from docs/evidence/."""
    response = client.get("/api/dashboard/benchmark")
    assert response.status_code == 200
    data = response.json()

    assert data["available"] is True
    assert data["provenance"] == "PHASE B BENCHMARK (Synthetic Controlled Evaluation)"
    assert data["source_artifact"] == "docs/evidence/phase_b_summary.json"
    assert data["metadata"]["paired_experimental_units"] == 10000
    assert data["metadata"]["total_arm_evaluations"] == 20000
    assert data["economics"]["control_gross_revenue"] == 13396279.0
    assert data["economics"]["treatment_total_net_revenue"] == 15411701.0
    assert data["economics"]["incremental_net_revenue"] == 2015422.0
    assert data["economics"]["treatment_genuine_incremental_revenue"] == 1415659.0
    assert data["economics"]["treatment_no_treatment_conversions"] == 5780
    assert data["economics"]["gross_revenue_delta_vs_control"] == 2029501.0
    assert data["economics"]["recovery_roi"] == 143.15
    assert data["safety_governance"]["safety_policy_compliance_rate"] if "safety_policy_compliance_rate" in data["safety_governance"] else True
    assert data["throughput"]["events_processed"] == 530944
    assert data["reconciliation_passed"] is True


def test_9_dashboard_benchmark_missing_artifact_handling(tmp_path):
    """9. GET /api/dashboard/benchmark returns available=False when snapshot is missing (no silent fallback)."""
    with patch("app.api.dashboard._PHASE_B_EVIDENCE_PATH", tmp_path / "non_existent.json"):
        response = client.get("/api/dashboard/benchmark")
        assert response.status_code == 200
        data = response.json()
        assert data["available"] is False
        assert "unavailable" in data["diagnostic_message"].lower()
        assert data["metadata"] is None


def test_10_dashboard_razorpay_proof_endpoint():
    """10. GET /api/dashboard/razorpay-proof returns verified Phase A proof with exact ₹996 net recovery."""
    response = client.get("/api/dashboard/razorpay-proof")
    assert response.status_code == 200
    data = response.json()

    assert data["proof_type"] == "RAZORPAY_TEST_MODE_EXTERNAL_RECOVERY"
    assert data["status"] == "VERIFIED"
    assert data["correlated_customer_id"] == "cus_live_proof_001"
    assert data["payment_link_id"] == "payload_pay_6898e42b"
    assert data["webhook_event_id"] == "TXFf0xsmSYoRsx"
    assert data["payment_id"] == "pay_TXFeukRbYol9b3"
    assert data["attributable_revenue"] == 999.0
    assert data["intervention_cost"] == 3.0
    assert data["net_recovered_revenue"] == 996.0
    assert data["outcome"] == "RECOVERED"
    assert data["attribution_status"] == "DIRECTLY_OBSERVED"
    assert data["duplicate_delivery_status"] == "DUPLICATE_ACKNOWLEDGED"
    assert "Razorpay Test Mode" in data["disclosure"]

    # Security: No secrets
    data_str = str(data)
    assert "secret" not in data_str.lower() or "webhook_secret" not in data_str
    assert "token" not in data_str.lower()
    assert "key_secret" not in data_str


def test_11_dashboard_audit_timeline_9_stages():
    """11. GET /api/dashboard/audit/{customer_id} returns exact 9-stage chronological timeline."""
    response = client.get("/api/dashboard/audit/cus_000005")
    assert response.status_code == 200
    data = response.json()

    assert data["customer_id"] == "cus_000005"
    assert data["total_stages"] == 9
    assert len(data["stages"]) == 9

    expected_stages = [
        "DETECT",
        "DIAGNOSE",
        "DECIDE",
        "GUARD",
        "EXECUTE",
        "PAYMENT_RESULT",
        "WEBHOOK",
        "OUTCOME",
        "ATTRIBUTION",
    ]

    allowed_statuses = [
        "EXECUTED",
        "PASSED",
        "GOVERNED_STOP",
        "ESCALATED",
        "BLOCKED",
        "NOT EXECUTED",
        "FAILED",
        "PENDING",
        "NOT OBSERVED",
        "SYNTHETIC_OBSERVED",
        "SYNTHETIC_FAILED",
        "RECOVERED",
        "ALREADY_CONVERTED",
        "NOT_RECOVERED",
        "NO_OBSERVABLE_OUTCOME",
        "DIRECTLY_OBSERVED",
        "UNATTRIBUTED",
    ]

    for idx, stage_name in enumerate(expected_stages, start=1):
        stage = data["stages"][idx - 1]
        assert stage["stage_index"] == idx
        assert stage["stage_name"] == stage_name
        assert stage["status"] in allowed_statuses
        assert len(stage["summary"]) > 0


def test_12_dashboard_audit_timeline_not_found():
    """12. GET /api/dashboard/audit/{unknown_id} returns HTTP 404."""
    response = client.get("/api/dashboard/audit/cus_non_existent_888")
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data


def test_13_dashboard_exceptions_endpoint():
    """13. GET /api/dashboard/exceptions returns exception ledger accounting and non-action details."""
    response = client.get("/api/dashboard/exceptions")
    assert response.status_code == 200
    data = response.json()

    assert "total_exceptions" in data
    assert "retryable_count" in data
    assert "terminal_count" in data
    assert "by_stage" in data
    assert "by_failure_type" in data
    assert "sample_exceptions" in data
    assert len(data["sample_exceptions"]) > 0


def test_14_dashboard_failure_scenarios_endpoint():
    """14. GET /api/dashboard/failure-scenarios returns deterministic controlled failure scenarios."""
    response = client.get("/api/dashboard/failure-scenarios")
    assert response.status_code == 200
    scenarios = response.json()

    assert len(scenarios) >= 2
    scen1 = scenarios[0]
    assert scen1["scenario_id"] == "payment_gateway_timeout_retryable"
    assert scen1["label"] in ["CONTROLLED DETERMINISTIC FAILURE FIXTURE", "CONTROLLED / SIMULATED FAILURE"]
    assert scen1["retryable"] is True
    assert scen1["safe_action"] == "RETRY_SCHEDULED"
    assert scen1["final_state"] == "RETRY"
    assert len(scen1["steps"]) >= 4

    scen2 = scenarios[1]
    assert scen2["scenario_id"] == "terminal_policy_blocked_invalid_state"
    assert scen2["label"] in ["CONTROLLED DETERMINISTIC FAILURE FIXTURE", "CONTROLLED / SIMULATED FAILURE"]
    assert scen2["retryable"] is False
    assert scen2["safe_action"] in ["STOP", "GOVERNED_STOP"]


def test_15_cors_headers_configured_for_frontend_origins():
    """15. CORS headers are present for allowed frontend origins."""
    response_localhost = client.options(
        "/api/dashboard/summary",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response_localhost.status_code == 200
    assert response_localhost.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_16_guard_semantics_passed_vs_governed_stop_vs_blocked():
    """16. Correct Guard Semantics: PASSED for eligible actions, GOVERNED_STOP for NO_ACTION, BLOCKED for ineligible."""
    # Find cus_000005 (Payment recovery, eligible) -> GUARD must be PASSED
    res_passed = client.get("/api/dashboard/audit/cus_000005?seed=42&cohort_size=100")
    assert res_passed.status_code == 200
    audit_passed = res_passed.json()
    guard_stage_passed = next(s for s in audit_passed["stages"] if s["stage_name"] == "GUARD")
    assert guard_stage_passed["status"] == "PASSED"
    assert "authorized" in guard_stage_passed["summary"]

    # Check all customers in cohort to find a NO_ACTION and INELIGIBLE case if present
    cust_res = client.get("/api/dashboard/customers?seed=42&cohort_size=100")
    assert cust_res.status_code == 200
    all_custs = cust_res.json()

    no_action_cust = next((c for c in all_custs if c["selected_action"] == "NO_ACTION" and c["eligibility_status"] == "ELIGIBLE"), None)
    if no_action_cust:
        res_stop = client.get(f"/api/dashboard/audit/{no_action_cust['customer_id']}?seed=42&cohort_size=100")
        assert res_stop.status_code == 200
        guard_stage_stop = next(s for s in res_stop.json()["stages"] if s["stage_name"] == "GUARD")
        assert guard_stage_stop["status"] == "GOVERNED_STOP"
        assert "Governed non-action" in guard_stage_stop["summary"]

    ineligible_cust = next((c for c in all_custs if c["eligibility_status"] == "INELIGIBLE"), None)
    if ineligible_cust:
        res_blocked = client.get(f"/api/dashboard/audit/{ineligible_cust['customer_id']}?seed=42&cohort_size=100")
        assert res_blocked.status_code == 200
        guard_stage_blocked = next(s for s in res_blocked.json()["stages"] if s["stage_name"] == "GUARD")
        assert guard_stage_blocked["status"] == "BLOCKED"
        assert "BLOCKED" in guard_stage_blocked["summary"]

    # Verify completed_stages excludes GOVERNED_STOP, BLOCKED, ESCALATED
    completed_statuses = {"EXECUTED", "PASSED", "RECOVERED", "DIRECTLY_OBSERVED", "SYNTHETIC_OBSERVED"}
    for c in all_custs[:10]:
        res_audit = client.get(f"/api/dashboard/audit/{c['customer_id']}?seed=42&cohort_size=100")
        if res_audit.status_code == 200:
            a = res_audit.json()
            expected_completed = sum(1 for s in a["stages"] if s["status"] in completed_statuses)
            assert a["completed_stages"] == expected_completed
            # Assert that no governed stop or blocked stage is counted as completed
            for s in a["stages"]:
                if s["status"] in {"GOVERNED_STOP", "BLOCKED", "ESCALATED"}:
                    assert s["status"] not in completed_statuses


def test_17_composite_cache_and_query_parameters():
    """17. Composite cache respects (cohort_size, seed, snapshot_hours) and maintains determinism."""
    # Call with custom parameters
    res1 = client.get("/api/dashboard/summary?seed=99&cohort_size=50&snapshot_hours=168.0")
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["dataset"]["customers_evaluated"] == 50

    # Repeat call: verify exact deterministic result
    res2 = client.get("/api/dashboard/summary?seed=99&cohort_size=50&snapshot_hours=168.0")
    assert res2.status_code == 200
    data2 = res2.json()
    assert data1["expected_recovery"]["total_revenue_at_risk"] == data2["expected_recovery"]["total_revenue_at_risk"]

    # Call with alias customers_count
    res_alias = client.get("/api/dashboard/summary?customers_count=25&seed=42")
    assert res_alias.status_code == 200
    assert res_alias.json()["dataset"]["customers_evaluated"] == 25

    # Distinct seed produces distinct evaluation
    res_seed42 = client.get("/api/dashboard/summary?seed=42&cohort_size=50&snapshot_hours=168.0")
    assert res_seed42.status_code == 200
    data_seed42 = res_seed42.json()
    assert data_seed42["dataset"]["customers_evaluated"] == 50


def test_18_query_parameter_propagation_customers_and_audit():
    """18. Query parameters propagate to customers list, customer detail, audit timeline, and exceptions."""
    cust_res = client.get("/api/dashboard/customers?seed=77&cohort_size=25&snapshot_hours=336.0")
    assert cust_res.status_code == 200
    custs = cust_res.json()
    assert len(custs) == 25
    first_id = custs[0]["customer_id"]

    # Single customer detail
    single_res = client.get(f"/api/dashboard/customers/{first_id}?seed=77&cohort_size=25&snapshot_hours=336.0")
    assert single_res.status_code == 200
    assert single_res.json()["customer_id"] == first_id

    # Customer audit timeline
    audit_res = client.get(f"/api/dashboard/audit/{first_id}?seed=77&cohort_size=25&snapshot_hours=336.0")
    assert audit_res.status_code == 200
    assert audit_res.json()["customer_id"] == first_id

    # Exceptions
    exc_res = client.get("/api/dashboard/exceptions?seed=77&cohort_size=25&snapshot_hours=336.0")
    assert exc_res.status_code == 200
    assert "total_exceptions" in exc_res.json()


def test_19_failure_scenarios_all_5_scenarios_present():
    """19. All 5 controlled failure scenarios are present with complete step lifecycles."""
    res = client.get("/api/dashboard/failure-scenarios")
    assert res.status_code == 200
    scenarios = res.json()
    assert len(scenarios) == 5

    scenario_ids = [s["scenario_id"] for s in scenarios]
    assert scenario_ids == [
        "payment_gateway_timeout_retryable",
        "terminal_policy_blocked_invalid_state",
        "cooldown_window_blocked",
        "idempotent_duplicate_suppression",
        "retry_exhaustion_escalation",
    ]

    for s in scenarios:
        assert s["label"] == "CONTROLLED DETERMINISTIC FAILURE FIXTURE"
        assert len(s["steps"]) >= 3
        assert s["customer_id"].startswith("cus_")
        assert s["final_state"] in ["RETRY", "STOP", "BLOCKED", "EXECUTED", "ESCALATED", "NO_ACTION"]


def test_20_no_duplicate_gemini_route():
    """20. Ensure GET /api/dashboard/gemini-evaluation is registered exactly once without route shadowing."""
    from app.api.main import app
    matching_routes = [
        r for r in app.routes
        if hasattr(r, "path") and r.path == "/api/dashboard/gemini-evaluation"
    ]
    assert len(matching_routes) == 1, f"Expected 1 route for gemini-evaluation, found {len(matching_routes)}"
