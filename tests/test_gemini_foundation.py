import os
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.api.app import app
from app.auth.authentication import create_access_token, DEFAULT_USERNAME
from app.ai.llm_client import (
    BaseLLM,
    GeminiClient,
    MockLLM,
    get_llm_client,
    resolve_gemini_api_key
)

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

def test_base_llm_architecture():
    assert issubclass(GeminiClient, BaseLLM)
    assert issubclass(MockLLM, BaseLLM)

def test_key_resolution_hierarchy(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr("app.config.settings.GEMINI_API_KEY", "")
    from app.memory.application_memory import ApplicationMemoryManager
    mem_mgr = ApplicationMemoryManager()
    mem_mgr.memory["ai_settings"] = {}
    mem_mgr.save_memory()

    # 1. No key anywhere -> returns empty string
    assert resolve_gemini_api_key() == ""

    # 2. Env variable set -> resolves env key
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyEnvKey123456789")
    assert resolve_gemini_api_key() == "AIzaSyEnvKey123456789"

    # 3. Explicit unmasked key -> takes precedence
    assert resolve_gemini_api_key("AIzaSyExplicitKey987654321") == "AIzaSyExplicitKey987654321"

    # 4. Masked key -> falls back to env key
    assert resolve_gemini_api_key("••••••••") == "AIzaSyEnvKey123456789"

def test_factory_selection(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr("app.config.settings.GEMINI_API_KEY", "")
    from app.memory.application_memory import ApplicationMemoryManager
    mem_mgr = ApplicationMemoryManager()
    mem_mgr.memory["ai_settings"] = {}
    mem_mgr.save_memory()

    # No key -> returns MockLLM
    client_mock = get_llm_client()
    assert isinstance(client_mock, MockLLM)

    # Valid key -> returns GeminiClient
    client_real = get_llm_client(api_key="AIzaSyValidTestKey12345")
    assert isinstance(client_real, GeminiClient)

@patch("google.genai.Client")
def test_gemini_client_connection_reuse(mock_genai_class):
    mock_instance = MagicMock()
    mock_genai_class.return_value = mock_instance

    c1 = GeminiClient(api_key="AIzaSySharedKey12345", model_name="gemini-2.5-flash")
    c2 = GeminiClient(api_key="AIzaSySharedKey12345", model_name="gemini-2.5-flash")

    assert c1.client is c2.client
    assert mock_genai_class.call_count == 1

@patch("google.genai.Client")
def test_gemini_client_retry_logic(mock_genai_class):
    mock_instance = MagicMock()
    # First attempt fails with 429 RateLimit, second attempt succeeds
    mock_response = MagicMock()
    mock_response.text = '{"status": "ok"}'
    mock_instance.models.generate_content.side_effect = [
        Exception("429 RESOURCE_EXHAUSTED: Rate limit exceeded"),
        mock_response
    ]
    mock_genai_class.return_value = mock_instance

    client = GeminiClient(api_key="AIzaSyRetryKey12345", model_name="gemini-2.5-flash")
    result = client.generate("System", "User")
    assert result == '{"status": "ok"}'

@patch("google.genai.Client")
def test_gemini_client_invalid_api_key_fallback(mock_genai_class):
    mock_instance = MagicMock()
    mock_instance.models.generate_content.side_effect = Exception("400 API_KEY_INVALID: Invalid API key")
    mock_genai_class.return_value = mock_instance

    client = GeminiClient(api_key="AIzaSyInvalidKey12345", model_name="gemini-2.5-flash")
    client.max_retries = 2
    res = client.generate("System", "evaluate this job: Python")

    # Should gracefully fall back to MockLLM generation without crashing
    assert "match_score" in res or "status" in res

@patch("google.genai.Client")
def test_test_gemini_endpoint_success(mock_genai_class, auth_client):
    mock_instance = MagicMock()
    mock_instance.models.get.return_value = MagicMock(name="gemini-2.5-flash")
    mock_genai_class.return_value = mock_instance

    payload = {"gemini_api_key": "AIzaSyValidKey12345", "primary_model": "gemini-2.5-flash"}
    resp = auth_client.post("/api/settings/test-gemini", json=payload)
    assert resp.status_code == 200
    assert resp.json()["connection_status"] == "Connected"
