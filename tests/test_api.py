"""
Pytest Suite for REVIVE FastAPI Presentation & Dashboard Layer.
Tests /health, /api/dashboard/summary, /api/dashboard/customers,
determinism, forbidden field isolation, and HTTP 404 error handling.
"""

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

    assert data["dataset"]["customers_evaluated"] == 100
    assert data["dataset"]["customers_with_payment_failures"] == 17
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


def test_7_dashboard_customer_by_id_not_found():
    """7. GET /api/dashboard/customers/{unknown_id} returns HTTP 404."""
    response = client.get("/api/dashboard/customers/cus_non_existent_999")
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
