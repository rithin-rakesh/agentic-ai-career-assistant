import os
import io
import pytest
from fastapi.testclient import TestClient
from app.api.app import app
from app.auth.authentication import create_access_token, DEFAULT_USERNAME
from app.config import settings

@pytest.fixture(autouse=True)
def patch_qdrant_memory(monkeypatch):
    monkeypatch.setattr("app.config.settings.VECTOR_DB_URL", ":memory:")

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def auth_headers():
    token = create_access_token(data={"sub": DEFAULT_USERNAME})
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def auth_client(client):
    token = create_access_token(data={"sub": DEFAULT_USERNAME})
    client.cookies.set("access_token", token)
    return client

def test_resume_status_endpoint(auth_client):
    response = auth_client.get("/api/resume/status")
    assert response.status_code == 200
    data = response.json()
    assert "current_resume" in data
    assert "version" in data
    assert "embedding_status" in data
    assert "chunk_count" in data

def test_upload_resume_text(auth_client):
    sample_md = "# Candidate Resume\n\n## Experience\nSenior AI Engineer with Python, PyTorch, FastAPI, Qdrant, Docker."
    response = auth_client.post("/api/resume", data={"resume_text": sample_md})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("success", "cached")
    assert data["chunk_count"] > 0

def test_upload_empty_file_returns_json_error(auth_client):
    files = {"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")}
    response = auth_client.post("/api/resume/upload", files=files)
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data or "message" in data
    assert "empty" in str(data).lower()

def test_upload_corrupted_pdf_returns_json_error(auth_client):
    corrupted_bytes = b"\x00\x11\x22\x33\x44\x55\x66\x77\x88\x99\xaa\xbb\xcc\xdd\xee\xff"
    files = {"file": ("corrupted.pdf", io.BytesIO(corrupted_bytes), "application/pdf")}
    response = auth_client.post("/api/resume/upload", files=files)
    assert response.status_code in (400, 500)
    # Must be valid JSON payload
    data = response.json()
    assert isinstance(data, dict)
    assert "detail" in data or "message" in data

def test_upload_unsupported_file_type_returns_json_error(auth_client):
    files = {"file": ("script.exe", io.BytesIO(b"binary data"), "application/x-msdownload")}
    response = auth_client.post("/api/resume/upload", files=files)
    assert response.status_code == 400
    data = response.json()
    assert "Unsupported" in str(data) or "detail" in data

def test_upload_valid_markdown_file_returns_json(auth_client):
    md_content = b"# John Doe\n\nPython Developer with 5 years experience in FastAPI and LLMs."
    files = {"file": ("resume.md", io.BytesIO(md_content), "text/markdown")}
    response = auth_client.post("/api/resume/upload", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("success", "cached")
    assert data["chunk_count"] > 0

def test_candidate_profile_update_and_get(auth_client):
    payload = {
        "candidate_name": "Jane Doe",
        "email_address": "jane.doe@example.com",
        "phone": "+1 (555) 123-4567",
        "linkedin": "https://linkedin.com/in/janedoe",
        "github": "https://github.com/janedoe",
        "portfolio": "https://janedoe.dev",
        "years_of_experience": 5.5,
        "preferred_salary": "$140,000 / yr",
        "notice_period": "30 Days",
        "minimum_match_score": 75,
        "scheduler_frequency_hours": 4,
        "preferred_locations": ["Remote", "San Francisco"],
        "preferred_technologies": ["Python", "FastAPI", "LangGraph"],
        "resume_content": "# Jane Doe Resume\n\nAI Engineer."
    }

    patch_resp = auth_client.patch("/api/settings", json=payload)
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "success"

    get_resp = auth_client.get("/api/settings")
    assert get_resp.status_code == 200
    settings_data = get_resp.json()

    assert settings_data["candidate_name"] == "Jane Doe"
    assert settings_data["email_address"] == "jane.doe@example.com"
    assert settings_data["phone"] == "+1 (555) 123-4567"
    assert settings_data["linkedin"] == "https://linkedin.com/in/janedoe"
    assert settings_data["github"] == "https://github.com/janedoe"
    assert settings_data["portfolio"] == "https://janedoe.dev"
    assert settings_data["years_of_experience"] == 5.5
    assert settings_data["preferred_salary"] == "$140,000 / yr"
    assert settings_data["notice_period"] == "30 Days"
