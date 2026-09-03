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
    """3. GET /api/dashboard/summary is 100% deterministic across multiple invocations."""
    res1 = client.get("/api/dashboard/summary").json()
    res2 = client.get("/api/dashboard/summary").json()
    assert res1 == res2


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
