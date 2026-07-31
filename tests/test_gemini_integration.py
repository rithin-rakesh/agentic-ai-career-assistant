import os
import json
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.api.app import app
from app.auth.authentication import create_access_token, DEFAULT_USERNAME
from app.ai.llm_client import BaseLLM, GeminiClient, MockLLM, get_llm_client, _clean_json_response
from app.ai.usage_tracker import ai_usage_tracker

@pytest.fixture(autouse=True)
def patch_qdrant_memory(monkeypatch):
    monkeypatch.setattr("app.config.settings.VECTOR_DB_URL", ":memory:")
    GeminiClient._shared_client = None
    GeminiClient._shared_key = None
    try:
        from app.memory.application_memory import ApplicationMemoryManager
        mem_mgr = ApplicationMemoryManager()
        mem_mgr.memory["ai_settings"] = {}
        mem_mgr.save_memory()
    except Exception:
        pass

@pytest.fixture
def auth_client():
    with TestClient(app) as client:
        token = create_access_token(data={"sub": DEFAULT_USERNAME})
        client.cookies.set("access_token", token)
        yield client

def test_json_cleaner():
    raw_markdown = "```json\n{\"test\": 123}\n```"
    cleaned = _clean_json_response(raw_markdown)
    assert cleaned == "{\"test\": 123}"

    raw_simple = "  {\"status\": \"ok\"}  "
    assert _clean_json_response(raw_simple) == "{\"status\": \"ok\"}"

def test_mock_llm_fallback():
    mock_llm = MockLLM(model_name="gemini-2.5-flash")
    resp = mock_llm.generate("You are an evaluator.", "evaluate this job: Python Engineer")
    parsed = json.loads(resp)
    assert "match_score" in parsed
    assert parsed["match_score"] > 0

def test_get_llm_client_factory_fallback(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr("app.config.settings.GEMINI_API_KEY", "")
    from app.memory.application_memory import ApplicationMemoryManager
    mem_mgr = ApplicationMemoryManager()
    mem_mgr.memory["ai_settings"] = {}
    mem_mgr.save_memory()

    # Without key -> returns MockLLM
    client = get_llm_client(api_key="")
    assert isinstance(client, MockLLM)

    # With key -> returns GeminiClient
    client_real = get_llm_client(api_key="AIzaSyTestMockKey12345")
    assert isinstance(client_real, GeminiClient)

@patch("google.genai.Client")
def test_gemini_client_successful_generation(mock_genai_client_class):
    GeminiClient._shared_client = None
    GeminiClient._shared_key = None

    mock_response = MagicMock()
    mock_response.text = "```json\n{\"match_score\": 95, \"priority\": \"High\"}\n```"
    mock_response.usage_metadata.prompt_token_count = 120
    mock_response.usage_metadata.candidates_token_count = 45

    mock_client_instance = MagicMock()
    mock_client_instance.models.generate_content.return_value = mock_response
    mock_genai_client_class.return_value = mock_client_instance

    gemini_client = GeminiClient(api_key="AIzaSyTestMockKey12345", model_name="gemini-2.5-flash")
    result = gemini_client.generate("System prompt", "Evaluate Python role")

    assert "match_score" in result
    assert json.loads(result)["match_score"] == 95

def test_ai_usage_endpoint(auth_client):
    resp = auth_client.get("/api/settings/ai-usage")
    assert resp.status_code == 200
    data = resp.json()

    assert "active_model" in data
    assert "prompts_today" in data
    assert "prompt_tokens" in data
    assert "completion_tokens" in data
    assert "total_tokens" in data
    assert "average_latency_ms" in data
    assert "connection_status" in data

@patch("google.genai.Client")
def test_test_gemini_connection_success(mock_genai_client_class, auth_client):
    mock_client_instance = MagicMock()
    mock_client_instance.models.get.return_value = MagicMock(name="gemini-2.5-flash")
    mock_genai_client_class.return_value = mock_client_instance

    payload = {
        "gemini_api_key": "AIzaSyValidTestKey123456789",
        "primary_model": "gemini-2.5-flash"
    }
    resp = auth_client.post("/api/settings/test-gemini", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "success"
    assert data["connection_status"] == "Connected"

@patch("google.genai.Client")
def test_test_gemini_connection_invalid_key(mock_genai_client_class, auth_client):
    mock_client_instance = MagicMock()
    mock_client_instance.models.get.side_effect = Exception("400 API_KEY_INVALID: Invalid API key")
    mock_genai_client_class.return_value = mock_client_instance

    payload = {
        "gemini_api_key": "AIzaSyInvalidKey",
        "primary_model": "gemini-2.5-flash"
    }
    resp = auth_client.post("/api/settings/test-gemini", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "error"
    assert data["connection_status"] == "Invalid API Key"

@patch("google.genai.Client")
def test_test_gemini_connection_quota_exceeded(mock_genai_client_class, auth_client):
    mock_client_instance = MagicMock()
    mock_client_instance.models.get.side_effect = Exception("RESOURCE_EXHAUSTED: Quota exceeded")
    mock_genai_client_class.return_value = mock_client_instance

    payload = {
        "gemini_api_key": "AIzaSyQuotaExceededKey",
        "primary_model": "gemini-2.5-flash"
    }
    resp = auth_client.post("/api/settings/test-gemini", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "error"
    assert data["connection_status"] == "Quota Exceeded"
