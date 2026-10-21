from datetime import date

from app.main import app, get_groq_service
from app.schemas import WorkflowDiagnosis


def ticket_payload(**overrides):
    return {
        "title": "Campus Wi-Fi disconnects",
        "description": "My laptop disconnects from campus Wi-Fi several times each hour.",
        "category": "Network",
        "priority": "High",
        "owner": "Test Requester",
        **overrides,
    }


def test_dashboard_uses_persisted_ticket_status_priority_and_timestamps(admin_client):
    opened_high = admin_client.post("/api/tickets", json=ticket_payload()).json()
    opened_low = admin_client.post("/api/tickets", json=ticket_payload(title="Printer is offline", priority="Low")).json()
    resolved = admin_client.post("/api/tickets", json=ticket_payload(title="Cannot access shared drive", priority="Medium")).json()
    progress = admin_client.post("/api/tickets", json=ticket_payload(title="Laptop camera is not found", priority="Medium")).json()
    assert admin_client.patch(f"/api/tickets/{resolved['id']}", json={"status": "Resolved", "resolution": "Reconnected the network profile and confirmed access."}).json()["resolved_at"]
    admin_client.patch(f"/api/tickets/{progress['id']}", json={"status": "In Progress"})

    dashboard = admin_client.get("/api/dashboard", params={"days": 7})
    assert dashboard.status_code == 200
    data = dashboard.json()
    assert data["open_tickets"] == 2
    assert data["in_progress_tickets"] == 1
    assert data["resolved_tickets"] == 1
    assert data["priority_distribution"] == {"High": 1, "Medium": 0, "Low": 1}
    assert sum(day["created"] for day in data["daily_volume"]) == 4
    assert sum(day["resolved"] for day in data["daily_volume"]) == 1
    assert data["ai_verified_resolutions"] is None
    assert {ticket["id"] for ticket in data["recent_tickets"]} == {opened_high["id"], opened_low["id"], resolved["id"], progress["id"]}


def test_dashboard_empty_database_has_zeroes_and_no_fabricated_activity(admin_client):
    response = admin_client.get("/api/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert data["open_tickets"] == 0
    assert data["in_progress_tickets"] == 0
    assert data["resolved_tickets"] == 0
    assert data["priority_distribution"] == {"High": 0, "Medium": 0, "Low": 0}
    assert len(data["daily_volume"]) == 7
    assert all(day["created"] == day["resolved"] == 0 for day in data["daily_volume"])
    assert data["recent_tickets"] == []
    assert data["ai_activity"] == []
    assert data["ai_verified_resolutions"] is None


def test_ticket_resolution_timestamp_is_not_backfilled_or_counted_from_confirmation(admin_client):
    ticket = admin_client.post("/api/tickets", json=ticket_payload()).json()
    assert ticket["resolved_at"] is None
    unchanged = admin_client.patch(f"/api/tickets/{ticket['id']}", json={"title": "Updated campus Wi-Fi issue"})
    assert unchanged.json()["resolved_at"] is None
    first_resolution = admin_client.patch(f"/api/tickets/{ticket['id']}", json={"status": "Resolved", "resolution": "Restored access and verified the requester can sign in."}).json()
    assert first_resolution["resolved_at"]
    assert date.fromisoformat(first_resolution["resolved_at"][:10]) == date.today()


def test_dashboard_activity_comes_from_persisted_workflow_events_not_user_confirmation(admin_client):
    class FakeDiagnosisService:
        def diagnose(self, issue, sources):
            return WorkflowDiagnosis(
                summary="Intermittent Wi-Fi connectivity",
                category="Network",
                suggested_priority="Medium",
                likely_causes=["Weak signal"],
                troubleshooting_steps=["Check whether other devices also disconnect."],
            )

    app.dependency_overrides[get_groq_service] = FakeDiagnosisService
    created = admin_client.post("/api/workflows", json={"issue": "My Wi-Fi keeps disconnecting"})
    assert created.status_code == 201
    run = created.json()
    assert admin_client.post(f"/api/workflows/{run['id']}/confirm", json={"fixed": True}).status_code == 200

    data = admin_client.get("/api/dashboard").json()
    assert any(event["workflow_id"] == run["id"] and event["stage"] == "simulated_tool" and event["simulated"] for event in data["ai_activity"])
    assert any(event["workflow_id"] == run["id"] and event["stage"] == "user_confirmation" for event in data["ai_activity"])
    assert data["ai_verified_resolutions"] is None
