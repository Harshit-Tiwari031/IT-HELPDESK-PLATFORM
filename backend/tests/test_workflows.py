from types import SimpleNamespace

import httpx
import pytest
from groq import APIStatusError

from app.ai_service import AIProviderError, AIProviderTimeout, GroqHelpdeskService
from app.config import Settings
from app.main import app, get_groq_service
from app.schemas import WorkflowDiagnosis
from app.workflow_tools import ToolResult, execute_simulated_tool
import app.workflow_service as workflow_service


class FakeDiagnosisService:
    def diagnose(self, issue, sources):
        return WorkflowDiagnosis(
            summary="Intermittent campus Wi-Fi connectivity",
            category="Network",
            suggested_priority="Medium",
            likely_causes=["Weak access point signal", "Saved network profile issue"],
            troubleshooting_steps=["Reconnect to Campus-Secure", "Test in another location"],
        )


def override_ai(service):
    app.dependency_overrides[get_groq_service] = lambda: service


def test_workflow_persists_simulated_success_and_user_confirmation(user_client):
    override_ai(FakeDiagnosisService())
    started = user_client.post("/api/workflows", json={"issue": "Campus Wi-Fi keeps disconnecting"})
    assert started.status_code == 201
    run = started.json()
    assert run["status"] == "awaiting_user"
    assert run["tool_output"]["label"] == "SIMULATED"
    assert run["verification"]["passed"] is True
    assert run["verification"]["real_environment_verified"] is False
    assert "suggestion only" in run["proposed_resolution"]
    assert len(run["events"]) == 5
    assert run["events"][0]["stage"] == "issue_received"
    assert run["events"][-1]["stage"] == "verification"

    fetched = user_client.get(f"/api/workflows/{run['id']}")
    assert fetched.status_code == 200
    confirmed = user_client.post(f"/api/workflows/{run['id']}/confirm", json={"fixed": True})
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "user_confirmed_resolved"
    assert confirmed.json()["events"][-1]["stage"] == "user_confirmation"
    assert user_client.get("/api/workflows").json()[0]["id"] == run["id"]


def test_workflow_uses_mocked_groq_json_diagnosis(user_client):
    class FakeCompletions:
        def create(self, **kwargs):
            assert kwargs["response_format"] == {"type": "json_object"}
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='''{
                "summary": "Campus Wi-Fi drops intermittently",
                "category": "Network",
                "suggested_priority": "Low",
                "likely_causes": ["Weak signal"],
                    "troubleshooting_steps": ["Reconnect to the verified college Wi-Fi network"]
            }'''), finish_reason="stop")])

    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

        def close(self):
            pass

    override_ai(GroqHelpdeskService(Settings(groq_api_key="test-secret"), client_factory=FakeClient))
    response = user_client.post("/api/workflows", json={"issue": "Campus Wi-Fi drops every few minutes"})
    assert response.status_code == 201
    assert response.json()["diagnosis"]["summary"] == "Campus Wi-Fi drops intermittently"


def test_invalid_groq_diagnosis_does_not_run_or_persist_simulated_tool(user_client, monkeypatch):
    class FakeCompletions:
        def create(self, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"category":"Unknown"}'), finish_reason="stop")])

    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

        def close(self):
            pass

    monkeypatch.setattr(workflow_service, "execute_simulated_tool", lambda *args: pytest.fail("tool ran after invalid diagnosis"))
    override_ai(GroqHelpdeskService(Settings(groq_api_key="test-secret"), client_factory=FakeClient))
    response = user_client.post("/api/workflows", json={"issue": "Campus Wi-Fi keeps disconnecting"})
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "GROQ_INVALID_DIAGNOSIS"
    assert "No simulated tool was run" in response.json()["detail"]["message"]
    assert user_client.get("/api/workflows").json() == []


def test_truncated_groq_diagnosis_does_not_run_or_persist_simulated_tool(user_client, monkeypatch):
    class FakeCompletions:
        def create(self, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"summary":"partial'), finish_reason="length")])

    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

        def close(self):
            pass

    monkeypatch.setattr(workflow_service, "execute_simulated_tool", lambda *args: pytest.fail("tool ran after truncated diagnosis"))
    override_ai(GroqHelpdeskService(Settings(groq_api_key="test-secret"), client_factory=FakeClient))
    response = user_client.post("/api/workflows", json={"issue": "Campus Wi-Fi keeps disconnecting"})
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "GROQ_INCOMPLETE_RESPONSE"
    assert '{"summary"' not in response.text
    assert user_client.get("/api/workflows").json() == []


def test_unsafe_groq_diagnosis_does_not_run_or_persist_simulated_tool(user_client, monkeypatch):
    class FakeCompletions:
        def create(self, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='''{
                "summary": "Campus Wi-Fi certificate warning",
                "category": "Network",
                "suggested_priority": "Medium",
                "likely_causes": ["Unknown certificate"],
                "troubleshooting_steps": ["Accept any certificate warning"]
            }'''), finish_reason="stop")])

    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

        def close(self):
            pass

    monkeypatch.setattr(workflow_service, "execute_simulated_tool", lambda *args: pytest.fail("tool ran after unsafe diagnosis"))
    override_ai(GroqHelpdeskService(Settings(groq_api_key="test-secret"), client_factory=FakeClient))
    response = user_client.post("/api/workflows", json={"issue": "Campus Wi-Fi shows a certificate warning"})
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "GROQ_UNSAFE_RESPONSE"
    assert user_client.get("/api/workflows").json() == []


def test_failed_verification_recommends_escalation(user_client, monkeypatch):
    override_ai(FakeDiagnosisService())
    monkeypatch.setattr(workflow_service, "execute_simulated_tool", lambda name, issue: ToolResult(
        output={"label": "SIMULATED", "result": "Sample expected response was not observed."},
        passed=False,
        reason="The simulated response did not match the sample criterion.",
    ))
    response = user_client.post("/api/workflows", json={"issue": "Campus Wi-Fi keeps disconnecting"})
    assert response.status_code == 201
    run = response.json()
    assert run["status"] == "needs_escalation"
    assert run["verification"]["passed"] is False
    assert "Contact campus IT" in run["next_action"]
    assert run["events"][-1]["stage"] == "escalation"
    assert run["ticket_id"] is None


def test_inconclusive_account_check_escalates_without_claiming_resolution(user_client):
    class AccountDiagnosis(FakeDiagnosisService):
        def diagnose(self, issue, sources):
            diagnosis = super().diagnose(issue, sources)
            return WorkflowDiagnosis.model_validate({**diagnosis.model_dump(), "category": "Account"})

    override_ai(AccountDiagnosis())
    response = user_client.post("/api/workflows", json={"issue": "I cannot sign into my account"})
    run = response.json()
    assert response.status_code == 201
    assert run["verification"]["passed"] is None
    assert run["status"] == "needs_escalation"
    assert run["verification"]["real_environment_verified"] is False


def test_unknown_tool_is_rejected():
    with pytest.raises(ValueError, match="allowlist"):
        execute_simulated_tool("run_shell_command", "anything")


def test_groq_timeout_is_sanitized_before_any_tool_runs(user_client, caplog):
    class FailingCompletions:
        def create(self, **kwargs):
            raise TimeoutError("provider failure contains test-secret")

    class FailingClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FailingCompletions())

        def close(self):
            pass

    override_ai(GroqHelpdeskService(Settings(groq_api_key="test-secret"), client_factory=FailingClient))
    response = user_client.post("/api/workflows", json={"issue": "Campus Wi-Fi drops every few minutes"})
    assert response.status_code == 504
    assert "test-secret" not in response.text
    assert "test-secret" not in caplog.text
    assert user_client.get("/api/workflows").json() == []


@pytest.mark.parametrize("http_status", [500, 503])
def test_groq_server_error_stops_workflow_before_tool_execution(user_client, monkeypatch, caplog, http_status):
    attempts = []

    class FailingCompletions:
        def create(self, **kwargs):
            attempts.append(kwargs)
            request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
            response = httpx.Response(http_status, request=request)
            raise APIStatusError("backend failure test-secret", response=response, body={"error": {"message": "backend failure test-secret"}})

    class FailingClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FailingCompletions())

        def close(self):
            pass

    monkeypatch.setattr(workflow_service, "execute_simulated_tool", lambda *args: pytest.fail("tool ran after failed diagnosis"))
    override_ai(GroqHelpdeskService(Settings(groq_api_key="test-secret"), client_factory=FailingClient))
    response = user_client.post("/api/workflows", json={"issue": "Campus Wi-Fi keeps disconnecting"})
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "GROQ_PROVIDER_ERROR"
    assert "No workflow tool was run" in response.json()["detail"]["message"]
    assert len(attempts) == 1
    assert "test-secret" not in caplog.text
    assert user_client.get("/api/workflows").json() == []


@pytest.mark.parametrize(("provider_error", "expected_status"), [(AIProviderTimeout(), 504), (AIProviderError("GROQ_PROVIDER_ERROR", "Unavailable."), 502)])
def test_workflow_provider_failures_never_run_or_persist_tools(user_client, provider_error, expected_status):
    class FailedDiagnosis:
        def diagnose(self, issue, sources):
            raise provider_error

    override_ai(FailedDiagnosis())
    response = user_client.post("/api/workflows", json={"issue": "Campus Wi-Fi keeps disconnecting"})
    assert response.status_code == expected_status
    assert "SIMULATED" not in response.text
    assert user_client.get("/api/workflows").json() == []


def test_confirm_not_fixed_records_escalation_and_no_duplicate_ticket(user_client):
    override_ai(FakeDiagnosisService())
    run = user_client.post("/api/workflows", json={"issue": "Campus Wi-Fi keeps disconnecting"}).json()
    response = user_client.post(f"/api/workflows/{run['id']}/confirm", json={"fixed": False})
    assert response.json()["status"] == "needs_escalation"
    assert response.json()["events"][-1]["stage"] == "escalation"
    assert user_client.get("/api/tickets").json() == []
