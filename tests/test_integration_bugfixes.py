import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.api.app import app
from app.auth.authentication import create_access_token, DEFAULT_USERNAME
from app.rag.vector_store import VectorStore, get_vector_store
import app.rag.vector_store as vs_mod
from app.ai.llm_client import GeminiClient

@pytest.fixture(autouse=True)
def reset_vector_store_singletons(monkeypatch):
    monkeypatch.setattr("app.config.settings.VECTOR_DB_URL", ":memory:")
    VectorStore._shared_client = None
    VectorStore._shared_url = None
    vs_mod._global_vector_store = None
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

def test_qdrant_singleton_connection_reuse(monkeypatch):
    monkeypatch.setattr("app.config.settings.VECTOR_DB_URL", ":memory:")
    VectorStore._shared_client = None
    VectorStore._shared_url = None
    vs_mod._global_vector_store = None

    vs1 = get_vector_store()
    vs2 = get_vector_store()
    vs3 = VectorStore()

    # All instances share the single underlying QdrantClient connection
    assert vs1.client is vs2.client
    assert vs2.client is vs3.client

def test_qdrant_server_mode_url_connection(monkeypatch):
    monkeypatch.setattr("app.config.settings.VECTOR_DB_URL", "http://localhost:6333")
    VectorStore._shared_client = None
    VectorStore._shared_url = None
    vs_mod._global_vector_store = None

    with patch("app.rag.vector_store.QdrantClient") as mock_qdrant_class:
        vs = VectorStore()
        mock_qdrant_class.assert_called_once_with(url="http://localhost:6333")

@patch("google.genai.Client")
def test_gemini_connection_utf8_non_ascii_handling(mock_genai_class, auth_client):
    mock_instance = MagicMock()
    # Exception containing non-ASCII Unicode characters (bullets, smart quotes, accent marks)
    mock_instance.models.get.side_effect = Exception("API Key Check Failed: 400 Invalid •••• credential key 'café_résumé'")
    mock_genai_class.return_value = mock_instance

    payload = {"gemini_api_key": "AIzaSyUnicodeKey••••12345", "primary_model": "gemini-2.5-flash"}
    resp = auth_client.post("/api/settings/test-gemini", json=payload)
    
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["status"] == "error"
    assert "Invalid API Key" in res_data["connection_status"] or "Error" in res_data["connection_status"]
