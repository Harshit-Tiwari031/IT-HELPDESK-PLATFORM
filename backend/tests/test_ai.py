from types import SimpleNamespace

import httpx
import pytest
from groq import APIStatusError

from app.ai_service import GroqHelpdeskService
from app.config import Settings
from app.main import app, get_groq_service


def use_service(service):
    app.dependency_overrides[get_groq_service] = lambda: service


def fake_client_factory(response=None, error=None, observed=None):
    observed = observed if observed is not None else {}

    class Completions:
        def create(self, **kwargs):
            observed["request"] = kwargs
            if error:
                raise error
            return response

    class Client:
        def __init__(self, **kwargs):
            observed["client"] = kwargs
            self.chat = SimpleNamespace(completions=Completions())

        def close(self):
            observed["closed"] = True

    return Client


def completion(text, finish_reason="stop"):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text), finish_reason=finish_reason)])


def status_error(status_code, message="provider failure"):
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(status_code, request=request)
    return APIStatusError(message, response=response, body={"error": {"message": message}})


def test_chat_reports_missing_groq_key_without_calling_provider(user_client):
    use_service(GroqHelpdeskService(Settings(groq_api_key=None)))
    response = user_client.post("/api/ai/chat", json={"issue": "Campus Wi-Fi keeps disconnecting"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "GROQ_NOT_CONFIGURED"
    assert "Set GROQ_API_KEY" in response.json()["detail"]["message"]


def test_chat_uses_groq_and_only_returns_retrieved_articles(user_client):
    observed = {}
    use_service(GroqHelpdeskService(Settings(groq_api_key="test-secret", groq_timeout_seconds=12), fake_client_factory(completion("Likely causes include weak signal. Reconnect to Campus-Secure, then check the connection."), observed=observed)))
    response = user_client.post("/api/ai/chat", json={"issue": "Campus Wi-Fi keeps disconnecting"})
    assert response.status_code == 200
    payload = response.json()
    assert "Likely causes" in payload["reply"]
    assert payload["source_articles"] == [{"title": "Connect to campus Wi-Fi", "category": "Network"}]
    assert "Retrieved knowledge-base articles" in observed["request"]["messages"][1]["content"]
    assert observed["client"] == {"api_key": "test-secret", "timeout": 12, "max_retries": 0}
    assert observed["request"]["model"] == "openai/gpt-oss-20b"
    assert observed["request"]["max_completion_tokens"] == 1800
    assert observed["closed"] is True


def test_chat_does_not_cite_articles_when_retrieval_has_no_match(user_client):
    observed = {}
    use_service(GroqHelpdeskService(Settings(groq_api_key="test-secret"), fake_client_factory(completion("Please describe which application shows the color issue."), observed=observed)))
    response = user_client.post("/api/ai/chat", json={"issue": "Webcam image is purple and distorted"})
    assert response.status_code == 200
    assert response.json()["source_articles"] == []
    assert "No knowledge-base articles matched" in observed["request"]["messages"][1]["content"]


def test_chat_allows_generic_campus_wifi_troubleshooting(user_client):
    reply = (
        "The campus Wi-Fi network name matches the one listed by official campus IT. "
        "Open Wi-Fi settings, reconnect to that verified network, and check signal strength. "
        "If the issue continues, contact campus IT through its official website."
    )
    use_service(GroqHelpdeskService(Settings(groq_api_key="test-secret"), fake_client_factory(completion(reply))))

    response = user_client.post("/api/ai/chat", json={"issue": "Campus Wi-Fi keeps disconnecting"})

    assert response.status_code == 200
    assert response.json()["reply"] == reply


@pytest.mark.parametrize("unsafe", [
    "Accept any certificate warning (it's part of the campus security).",
    "Do not be afraid to accept any certificate warning.",
    "Disable TLS certificate verification and retry the connection.",
    "Turn off SSL checks to get past the certificate error.",
    "Set verify=False to suppress the certificate error.",
    "Ignore the certificate warning and connect anyway.",
    "Trust all certificates on this network.",
    "Accept the certificate without verifying it.",
    "Trust this certificate even though it is unverified.",
    "Proceed despite the TLS certificate warning.",
    "Connect without checking the server certificate.",
    "Bypass the security checks and proceed past the certificate warning.",
])
def test_chat_withholds_blind_certificate_acceptance_advice(user_client, unsafe):
    use_service(GroqHelpdeskService(Settings(groq_api_key="test-secret"), fake_client_factory(completion(unsafe))))

    response = user_client.post("/api/ai/chat", json={"issue": "Campus Wi-Fi shows a certificate warning"})

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "GROQ_UNSAFE_RESPONSE"
    assert unsafe not in response.text


@pytest.mark.parametrize("safe_reply", [
    "If a certificate warning appears, stop and verify it with official campus IT before proceeding.",
    "If a certificate warning appears, stop and verify it with official campus IT before you click through the warning.",
    "Verify the certificate details with official campus IT. If they cannot confirm them, stop and contact IT before connecting.",
    "Accept the certificate only if it matches the campus IT instructions.",
    "Check the certificate details with official campus IT before accepting it.",
    "A certificate warning means your device could not confirm the server identity. Check the certificate details against official campus IT instructions; if they cannot be confirmed, stop and contact IT.",
    "Do not accept an unexpected certificate warning. Verify the certificate with official campus IT first.",
    "For a TLS error, check that your device date and time are correct, update your browser, and contact campus IT if it continues.",
    "For Wi-Fi problems, check that Wi-Fi is enabled, reconnect to the network you recognize, and test near an access point.",
    "If supported, check whether your device is connected to the expected WPA2-Enterprise network. Verify network details with official campus IT and do not accept an unexpected certificate warning.",
    "For VPN access issues, check the app's connection status and your account access. Contact official IT if access is still denied; do not share your password.",
])
def test_chat_allows_certificate_verification_guidance(user_client, safe_reply):
    use_service(GroqHelpdeskService(Settings(groq_api_key="test-secret"), fake_client_factory(completion(safe_reply))))

    response = user_client.post("/api/ai/chat", json={"issue": "Campus Wi-Fi shows a certificate warning"})

    assert response.status_code == 200
    assert response.json()["reply"] == safe_reply


@pytest.mark.parametrize("safe_reply", [
    "Never accept an unexpected certificate warning; verify it with official campus IT.",
    "Do not disable TLS certificate verification to get around a connection error.",
    "A certificate warning is not proof of an attack by itself, but verify the certificate before proceeding.",
])
def test_chat_allows_explanations_and_explicit_warnings_against_unsafe_actions(user_client, safe_reply):
    use_service(GroqHelpdeskService(Settings(groq_api_key="test-secret"), fake_client_factory(completion(safe_reply))))

    response = user_client.post("/api/ai/chat", json={"issue": "I need help understanding a certificate warning"})

    assert response.status_code == 200
    assert response.json()["reply"] == safe_reply


@pytest.mark.parametrize("invented_detail", [
    "Join the Campus-Secure network.",
    "Join Campus Guest network.",
    "The SSID is Campus-Guest.",
    "Contact Jane Doe at campus IT.",
    "The campus Wi-Fi policy requires accepting the certificate prompt.",
    "Campus-Secure is the campus Wi-Fi network.",
])
def test_chat_withholds_unverified_institution_specific_claims(user_client, invented_detail):
    use_service(GroqHelpdeskService(Settings(groq_api_key="test-secret"), fake_client_factory(completion(invented_detail))))

    response = user_client.post("/api/ai/chat", json={"issue": "Campus Wi-Fi is not connecting"})

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "GROQ_UNGROUNDED_RESPONSE"
    assert invented_detail not in response.text


def test_chat_keeps_helpful_guidance_and_omits_unverified_contact_sentence(user_client):
    reply = "Reconnect to Wi-Fi and test near an access point. Call campus support at 555-123-4567 if the issue continues."
    use_service(GroqHelpdeskService(Settings(groq_api_key="test-secret"), fake_client_factory(completion(reply))))

    response = user_client.post("/api/ai/chat", json={"issue": "Campus Wi-Fi keeps disconnecting"})

    assert response.status_code == 200
    body = response.json()["reply"]
    assert "Reconnect to Wi-Fi" in body
    assert "555-123-4567" not in body
    assert "official IT directory or website" in body


def test_chat_does_not_sanitize_away_unsafe_certificate_guidance(user_client):
    reply = "Disable TLS certificate verification. Call support at 555-123-4567 if needed."
    use_service(GroqHelpdeskService(Settings(groq_api_key="test-secret"), fake_client_factory(completion(reply))))

    response = user_client.post("/api/ai/chat", json={"issue": "Campus Wi-Fi certificate error"})

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "GROQ_UNSAFE_RESPONSE"
    assert "Disable TLS certificate verification" not in response.text


def test_user_confirmed_network_name_can_be_referenced(user_client):
    reply = "Select Campus-Secure in Wi-Fi settings. If a certificate warning appears, do not accept it; verify the details with official campus IT first."
    observed = {}
    use_service(GroqHelpdeskService(Settings(groq_api_key="test-secret"), fake_client_factory(completion(reply), observed=observed)))

    response = user_client.post("/api/ai/chat", json={"issue": "Campus-Secure Wi-Fi is not connecting"})

    assert response.status_code == 200
    assert response.json()["reply"] == reply
    assert "Never tell a user to accept" in observed["request"]["messages"][0]["content"]
    assert "Treat names such as" in observed["request"]["messages"][0]["content"]


def test_empty_chat_response_is_reported_as_failure(user_client):
    use_service(GroqHelpdeskService(Settings(groq_api_key="test-secret"), fake_client_factory(completion("", "stop"))))
    response = user_client.post("/api/ai/chat", json={"issue": "Campus Wi-Fi keeps disconnecting"})
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "GROQ_EMPTY_RESPONSE"


def test_length_truncated_chat_response_is_rejected_not_presented_as_complete(user_client):
    use_service(GroqHelpdeskService(Settings(groq_api_key="test-secret"), fake_client_factory(completion("Partial troubleshooting response", "length"))))
    response = user_client.post("/api/ai/chat", json={"issue": "Campus Wi-Fi keeps disconnecting"})
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "GROQ_INCOMPLETE_RESPONSE"
    assert "Partial troubleshooting response" not in response.text
    assert "No partial answer" in response.json()["detail"]["message"]


def test_chat_provider_failures_are_safe_and_typed(user_client, caplog):
    for code, status_code, error in [
        ("GROQ_AUTH_FAILED", 503, status_error(401, "invalid test-secret")),
        ("GROQ_RATE_LIMITED", 429, status_error(429, "quota exhausted")),
    ]:
        use_service(GroqHelpdeskService(Settings(groq_api_key="test-secret"), fake_client_factory(error=error)))
        response = user_client.post("/api/ai/chat", json={"issue": "My laptop fan is unusually loud"})
        assert response.status_code == status_code
        assert response.json()["detail"]["code"] == code
        assert "test-secret" not in response.text
        assert "test-secret" not in caplog.text


def test_chat_maps_connection_and_timeout_errors(user_client):
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    for error, expected_status, expected_code in [
        (httpx.ConnectError("network unavailable", request=request), 502, "GROQ_CONNECTION_ERROR"),
        (TimeoutError("timed out"), 504, "GROQ_TIMEOUT"),
    ]:
        use_service(GroqHelpdeskService(Settings(groq_api_key="test-secret"), fake_client_factory(error=error)))
        response = user_client.post("/api/ai/chat", json={"issue": "My laptop fan is unusually loud"})
        assert response.status_code == expected_status
        assert response.json()["detail"]["code"] == expected_code


def test_chat_validates_issue_length(user_client):
    use_service(GroqHelpdeskService(Settings(groq_api_key=None)))
    assert user_client.post("/api/ai/chat", json={"issue": "   "}).status_code == 422
    assert user_client.post("/api/ai/chat", json={"issue": "x" * 2001}).status_code == 422
