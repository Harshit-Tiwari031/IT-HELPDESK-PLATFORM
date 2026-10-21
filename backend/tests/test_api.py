def ticket_payload(**overrides):
    return {
        "title": "Campus Wi-Fi disconnects",
        "description": "My laptop disconnects from campus Wi-Fi several times each hour.",
        "category": "Network",
        "priority": "High",
        "owner": "Alex Morgan",
        **overrides,
    }


def test_health_reports_database_connection(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}


def test_ticket_create_list_detail_and_patch(admin_client):
    created = admin_client.post("/api/tickets", json=ticket_payload())
    assert created.status_code == 201
    ticket = created.json()
    assert ticket["id"].startswith("HD-")
    assert ticket["status"] == "Open"
    assert ticket["created_at"]
    assert ticket["updated_at"]

    listed = admin_client.get("/api/tickets", params={"search": "campus Wi-Fi", "status": "Open", "priority": "High"})
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [ticket["id"]]

    detail = admin_client.get(f"/api/tickets/{ticket['id'].lower()}")
    assert detail.status_code == 200
    assert detail.json()["description"] == ticket_payload()["description"]

    patched = admin_client.patch(f"/api/tickets/{ticket['id']}", json={"status": "In Progress", "priority": "Medium"})
    assert patched.status_code == 200
    assert patched.json()["status"] == "In Progress"
    assert patched.json()["priority"] == "Medium"

    missing_resolution = admin_client.patch(f"/api/tickets/{ticket['id']}", json={"status": "Resolved"})
    assert missing_resolution.status_code == 422
    resolved = admin_client.patch(f"/api/tickets/{ticket['id']}", json={"status": "Resolved", "resolution": "Updated the wireless adapter driver and verified the connection stays stable."})
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "Resolved"
    assert resolved.json()["resolved_at"] is not None


def test_ticket_validation_and_missing_ticket_errors(user_client):
    invalid = user_client.post("/api/tickets", json=ticket_payload(title="tiny"))
    assert invalid.status_code == 422

    unknown_field = user_client.post("/api/tickets", json=ticket_payload(unexpected="not accepted"))
    assert unknown_field.status_code == 422

    missing = user_client.get("/api/tickets/HD-MISSING")
    assert missing.status_code == 404

    empty_patch = user_client.patch("/api/tickets/HD-MISSING", json={})
    assert empty_patch.status_code == 422

    forbidden_patch = user_client.patch("/api/tickets/HD-MISSING", json={"owner": "Changed owner"})
    assert forbidden_patch.status_code == 422


def test_create_defaults_status_and_rejects_invalid_filters(user_client):
    created = user_client.post("/api/tickets", json=ticket_payload(priority="Low"))
    assert created.status_code == 201
    assert created.json()["status"] == "Open"
    assert user_client.get("/api/tickets", params={"status": "Waiting"}).status_code == 422
