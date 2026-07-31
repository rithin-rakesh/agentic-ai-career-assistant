import os
import pytest
from fastapi.testclient import TestClient
from app.api.app import app
from app.config import settings
from app.auth.authentication import create_access_token, DEFAULT_USERNAME

@pytest.fixture(autouse=True)
def patch_qdrant_memory(monkeypatch):
    monkeypatch.setattr("app.config.settings.VECTOR_DB_URL", ":memory:")

@pytest.fixture
def auth_client():
    with TestClient(app) as client:
        token = create_access_token(data={"sub": DEFAULT_USERNAME})
        client.cookies.set("access_token", token)
        yield client

def test_control_center_get_settings_masked_secrets(auth_client):
    resp = auth_client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()

    assert "candidate_name" in data
    assert "current_location" in data
    assert "preferred_roles" in data
    assert "gemini_api_key" in data
    assert "smtp_password" in data
    assert "ai_connection_status" in data

    # Check secret masking format (never plain text if present)
    if data["gemini_api_key"]:
        assert "••••" in data["gemini_api_key"] or len(data["gemini_api_key"]) <= 12

def test_control_center_patch_settings(auth_client):
    orig_locs = settings.PREFERRED_LOCATIONS
    try:
        payload = {
            "candidate_name": "Test Engineer",
            "email_address": "test.engineer@example.com",
            "current_location": "San Francisco, CA",
            "years_of_experience": 6.5,
            "preferred_roles": ["AI Architect", "DevOps Lead"],
            "preferred_locations": ["Remote", "San Francisco", "Bangalore"],
            "enable_remote": True,
            "enable_hybrid": True,
            "enable_onsite": False,
            "minimum_salary": "$120,000 / yr",
            "gemini_api_key": "test_gemini_key_12345",
            "provider": "Google Gemini",
            "primary_model": "gemini-2.5-flash",
            "temperature": 0.2,
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 587,
            "smtp_username": "user@gmail.com",
            "smtp_password": "app_password_1234",
            "notification_email": "user@gmail.com"
        }

        patch_resp = auth_client.patch("/api/settings", json=payload)
        assert patch_resp.status_code == 200
        assert patch_resp.json()["status"] == "success"

        # Verify updated values via GET
        get_resp = auth_client.get("/api/settings")
        assert get_resp.status_code == 200
        res_data = get_resp.json()

        assert res_data["candidate_name"] == "Test Engineer"
        assert res_data["current_location"] == "San Francisco, CA"
        assert res_data["years_of_experience"] == 6.5
        assert res_data["preferred_roles"] == ["AI Architect", "DevOps Lead"]
        assert res_data["primary_model"] == "gemini-2.5-flash"
        assert res_data["gemini_api_key"].startswith("test") or "••••" in res_data["gemini_api_key"]
    finally:
        settings.PREFERRED_LOCATIONS = orig_locs

from unittest.mock import patch, MagicMock

@patch("google.genai.Client")
def test_test_gemini_endpoint(mock_genai_client, auth_client):
    mock_client_instance = MagicMock()
    mock_client_instance.models.get.return_value = MagicMock(name="gemini-2.5-flash")
    mock_genai_client.return_value = mock_client_instance

    payload = {
        "gemini_api_key": "test_gemini_api_key_string",
        "provider": "Google Gemini",
        "primary_model": "gemini-2.5-flash"
    }
    resp = auth_client.post("/api/settings/test-gemini", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["connection_status"] == "Connected"

def test_test_email_endpoint(auth_client):
    payload = {
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_username": "",
        "smtp_password": "",
        "notification_email": "candidate@example.com"
    }
    resp = auth_client.post("/api/settings/test-email", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["recipient"] == "candidate@example.com"
    assert data["delivery_mode"] == "MOCK"
    assert data["acceptance_status"] == "Mocked"
    assert "timestamp" in data

def test_resume_status_and_delete(auth_client):
    # GET status
    status_resp = auth_client.get("/api/resume/status")
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert "current_resume" in data
    assert "embedding_status" in data

    # DELETE active resume
    del_resp = auth_client.delete("/api/resume")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "success"

def test_system_status_endpoint(auth_client):
    resp = auth_client.get("/api/system/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ["healthy", "degraded"]
    assert "fastapi" in data["details"]
    assert "database" in data["details"]
    assert "qdrant" in data["details"]
