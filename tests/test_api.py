import json

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from openai import OpenAI

from app import triage as triage_service
from app.main import app


RESULT = {
    "category": "withdrawal",
    "priority": "high",
    "summary": "Customer reports a delayed withdrawal.",
    "recommended_action": "Ask for the transaction reference and investigate its status.",
    "requires_human": True,
}
FAILURE = {"detail": "Triage service could not process the message."}


def provider_response(content=None, status="completed"):
    return {
        "id": "resp_test",
        "object": "response",
        "created_at": 0,
        "model": "test-model",
        "status": status,
        "output": [{
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": content if content is not None else [{
                "type": "output_text", "text": json.dumps(RESULT), "annotations": [],
            }],
        }],
    }


@pytest.fixture(autouse=True)
def isolate_provider(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-placeholder")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    def unexpected_client(**kwargs):
        pytest.fail("Unexpected provider call; tests must install a mock transport")

    monkeypatch.setattr(triage_service, "OpenAI", unexpected_client)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def mock_provider(monkeypatch):
    def install(handler):
        def create_client(**kwargs):
            return OpenAI(
                **kwargs,
                base_url="https://provider.test/v1",
                http_client=httpx.Client(transport=httpx.MockTransport(handler)),
            )

        monkeypatch.setattr(triage_service, "OpenAI", create_client)

    return install


def test_health_without_configuration(client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY")
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


@pytest.mark.parametrize("configured_model", [None, "custom-model"])
def test_triage_success(client, mock_provider, monkeypatch, configured_model):
    if configured_model:
        monkeypatch.setenv("OPENAI_MODEL", configured_model)
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=provider_response())

    mock_provider(respond)
    response = client.post("/triage", json={"message": "  My withdrawal is delayed.  "})
    assert response.status_code == 200
    assert response.json() == RESULT
    assert len(requests) == 1
    sent = requests[0]
    assert sent["model"] == (configured_model or triage_service.DEFAULT_MODEL)
    assert sent["input"] == [{"role": "user", "content": "My withdrawal is delayed."}]
    output_format = sent["text"]["format"]
    assert output_format["type"] == "json_schema"
    assert output_format["strict"] is True
    assert output_format["schema"]["additionalProperties"] is False
    assert set(output_format["schema"]["required"]) == set(RESULT)


@pytest.mark.parametrize("body", [
    {}, {"message": ""}, {"message": " \t\n "}, {"message": None},
    {"message": 123}, {"message": True}, {"message": []}, [],
])
def test_invalid_request_rejected_without_provider_call(client, body):
    assert client.post("/triage", json=body).status_code == 422


def test_missing_body_and_malformed_json(client):
    assert client.post("/triage").status_code == 422
    response = client.post(
        "/triage", content="{broken", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422


@pytest.mark.parametrize("api_key", [None, "", "  "])
def test_missing_configuration(client, monkeypatch, api_key):
    if api_key is None:
        monkeypatch.delenv("OPENAI_API_KEY")
    else:
        monkeypatch.setenv("OPENAI_API_KEY", api_key)
    response = client.post("/triage", json={"message": "Please help."})
    assert response.status_code == 503
    assert response.json() == {"detail": "Triage service is unavailable."}


@pytest.mark.parametrize("status", [401, 429, 500])
def test_provider_failure_is_sanitized(client, mock_provider, status):
    calls = []

    def fail(request):
        calls.append(request)
        return httpx.Response(status, json={"error": {
            "message": "Sensitive provider internals test-placeholder", "type": "api_error",
        }})

    mock_provider(fail)
    response = client.post("/triage", json={"message": "Please help."})
    assert response.status_code == 502
    assert response.json() == FAILURE
    assert "Sensitive" not in response.text
    assert "test-placeholder" not in response.text
    assert len(calls) == 1


def test_provider_timeout(client, mock_provider):
    def timeout(request):
        raise httpx.ReadTimeout("Sensitive network details", request=request)

    mock_provider(timeout)
    response = client.post("/triage", json={"message": "Please help."})
    assert response.status_code == 502
    assert response.json() == FAILURE


@pytest.mark.parametrize("changes", [
    {"category": "unknown"}, {"priority": "urgent"}, {"summary": "  "},
    {"recommended_action": ""}, {"requires_human": "yes"}, {"extra": "forbidden"},
])
def test_invalid_model_output_is_rejected(client, mock_provider, changes):
    content = [{
        "type": "output_text", "text": json.dumps(RESULT | changes), "annotations": [],
    }]
    mock_provider(lambda request: httpx.Response(200, json=provider_response(content)))
    response = client.post("/triage", json={"message": "Please help."})
    assert response.status_code == 502
    assert response.json() == FAILURE


@pytest.mark.parametrize("content,status", [
    ([{"type": "refusal", "refusal": "Cannot help."}], "completed"),
    ([], "completed"),
    (None, "incomplete"),
    ([{"type": "output_text", "text": "not JSON", "annotations": []}], "completed"),
])
def test_unusable_model_response(client, mock_provider, content, status):
    mock_provider(lambda request: httpx.Response(
        200, json=provider_response(content, status)
    ))
    response = client.post("/triage", json={"message": "Please help."})
    assert response.status_code == 502
    assert response.json() == FAILURE
