import pytest
from fastapi.testclient import TestClient
from app.api.app import app
from app.auth.authentication import create_access_token, DEFAULT_USERNAME
from app.config import settings

@pytest.fixture(autouse=True)
def patch_qdrant_memory(monkeypatch):
    monkeypatch.setattr("app.config.settings.VECTOR_DB_URL", ":memory:")

@pytest.fixture
def auth_client():
    with TestClient(app) as client:
        token = create_access_token(data={"sub": DEFAULT_USERNAME})
        client.cookies.set("access_token", token)
        yield client

def test_scheduler_status_and_controls(auth_client):
    # GET status
    status_resp = auth_client.get("/api/scheduler/status")
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert "current_status" in data
    assert "last_run" in data
    assert "next_run" in data
    assert "duration" in data

    # POST pause
    pause_resp = auth_client.post("/api/scheduler/pause")
    assert pause_resp.status_code == 200
    assert pause_resp.json()["data"]["current_status"] == "Paused"

    # POST resume
    resume_resp = auth_client.post("/api/scheduler/resume")
    assert resume_resp.status_code == 200
    assert resume_resp.json()["data"]["current_status"] == "Running"

    # POST run-now
    run_resp = auth_client.post("/api/scheduler/run-now")
    assert run_resp.status_code == 200
    assert run_resp.json()["status"] == "success"

def test_job_preferences_and_ai_settings_update(auth_client):
    payload = {
        "preferred_roles": ["AI Engineer", "ML Architect"],
        "preferred_locations": ["Remote", "Bangalore", "San Francisco"],
        "enable_remote": True,
        "enable_hybrid": True,
        "enable_onsite": False,
        "minimum_salary": "$100,000 / yr",
        "maximum_salary": "$250,000 / yr",
        "experience_level": "Senior",
        "preferred_skills": ["Python", "PyTorch", "LangGraph", "Qdrant"],
        "ignored_companies": ["SpamCorp"],
        "ignored_keywords": ["Crypto", "Unpaid"],

        "gemini_api_key": "test_gemini_key",
        "openai_api_key": "test_openai_key",
        "primary_model": "gemini-2.5-flash",
        "temperature": 0.3,
        "max_tokens": 2048,
        "request_timeout": 45,

        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_username": "test.sender@gmail.com",
        "smtp_password": "app_password_123",
        "notification_email": "test.recipient@example.com"
    }

    patch_resp = auth_client.patch("/api/settings", json=payload)
    assert patch_resp.status_code == 200

    get_resp = auth_client.get("/api/settings")
    assert get_resp.status_code == 200
    res_data = get_resp.json()

    assert res_data["preferred_roles"] == ["AI Engineer", "ML Architect"]
    assert res_data["enable_remote"] is True
    assert res_data["enable_onsite"] is False
    assert res_data["experience_level"] == "Senior"
    assert res_data["primary_model"] == "gemini-2.5-flash"
    assert res_data["temperature"] == 0.3
    assert res_data["max_tokens"] == 2048
    assert res_data["smtp_username"] == "test.sender@gmail.com"

def test_email_test_endpoint_mock(auth_client):
    payload = {
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_username": "",
        "smtp_password": "",
        "notification_email": "candidate@example.com"
    }

    # Test email sending endpoint
    resp = auth_client.post("/api/settings/email/test", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
