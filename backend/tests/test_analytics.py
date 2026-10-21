from app.main import app, get_groq_service
from app.schemas import WorkflowDiagnosis


def ticket_payload(title, category="Network"):
    return {
        "title": title,
        "description": "The device cannot connect to the requested service.",
        "category": category,
        "priority": "Medium",
    }


def test_admin_analytics_uses_real_ticket_workflow_and_timestamp_data(admin_client):
    network = admin_client.post("/api/tickets", json=ticket_payload("Campus Wi-Fi is unavailable")).json()
    hardware = admin_client.post("/api/tickets", json=ticket_payload("Laptop camera is not detected", "Hardware")).json()
    resolved = admin_client.patch(
        f"/api/tickets/{network['id']}",
        json={"status": "Resolved", "resolution": "Reconnected the network profile and verified access."},
    )
    assert resolved.status_code == 200

    class FakeDiagnosisService:
        def diagnose(self, issue, sources):
            return WorkflowDiagnosis(
                summary="Network connection issue",
                category="Network",
                suggested_priority="Medium",
                likely_causes=["Connection profile may need attention"],
                troubleshooting_steps=["Check the connection status."],
            )

    app.dependency_overrides[get_groq_service] = FakeDiagnosisService
    workflow = admin_client.post(
        "/api/workflows",
        json={"issue": "The Wi-Fi connection is unavailable", "ticket_id": hardware["id"]},
    )
    assert workflow.status_code == 201

    response = admin_client.get("/api/analytics", params={"days": 30})
    assert response.status_code == 200
    data = response.json()
    assert data["days"] == 30
    assert data["total_tickets"] == 2
    assert data["resolved_tickets"] == 1
    assert data["resolution_rate_percent"] == 50.0
    assert data["average_first_response_minutes"] is None
    assert data["tickets_with_workflow"] == 1
    assert sum(day["created"] for day in data["daily_volume"]) == 2
    assert sum(day["resolved"] for day in data["daily_volume"]) == 1
    assert {item["category"]: item["count"] for item in data["category_distribution"]} == {
        "Network": 1,
        "Hardware": 1,
    }


def test_admin_analytics_empty_period_returns_no_invented_metrics(admin_client):
    response = admin_client.get("/api/analytics", params={"days": 30})
    assert response.status_code == 200
    data = response.json()
    assert data["total_tickets"] == 0
    assert data["resolved_tickets"] == 0
    assert data["resolution_rate_percent"] is None
    assert data["average_first_response_minutes"] is None
    assert data["tickets_with_workflow"] == 0
    assert all(day["created"] == day["resolved"] == 0 for day in data["daily_volume"])
    assert data["category_distribution"] == []


def test_analytics_is_admin_only_and_requires_authentication(user_client, client):
    assert user_client.get("/api/analytics").status_code == 403
    assert client.get("/api/analytics").status_code == 401


def test_analytics_rejects_unsupported_date_ranges(admin_client):
    assert admin_client.get("/api/analytics", params={"days": 1}).status_code == 422
    assert admin_client.get("/api/analytics", params={"days": 120}).status_code == 422
