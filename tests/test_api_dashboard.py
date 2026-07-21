import os
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from app.config import settings
from app.api.app import app
from app.database.repository import JobRepository
from app.database.models import Base
from app.schemas.job import JobCreate
from app.auth.authentication import create_access_token, DEFAULT_USERNAME

@pytest.fixture(autouse=True)
def patch_qdrant_memory(monkeypatch):
    monkeypatch.setattr("app.config.settings.VECTOR_DB_URL", ":memory:")

@pytest.fixture
def api_client():
    """
    Returns a TestClient instance bound to the FastAPI application.
    """
    client = TestClient(app)
    return client

@pytest.fixture
def auth_headers():
    """
    Generates mock auth headers containing a valid JWT token.
    """
    token = create_access_token(data={"sub": DEFAULT_USERNAME})
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def auth_cookie(api_client):
    """
    Sets the access_token cookie in the client session.
    """
    token = create_access_token(data={"sub": DEFAULT_USERNAME})
    api_client.cookies.set("access_token", token)
    return api_client

def test_health_check_endpoint(api_client):
    """
    Asserts that the health check endpoint returns 200 and system details.
    """
    response = api_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["healthy", "degraded"]
    assert "database" in data["details"]
    assert "vector_database" in data["details"]

def test_unauthenticated_endpoint_blocks(api_client):
    """
    Verifies that requesting secure endpoints without credentials returns 401.
    """
    # 1. API endpoint block check
    response = api_client.get("/api/jobs")
    assert response.status_code == 401
    
    # 2. HTML page endpoint redirect check
    response = api_client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"

def test_login_flow(api_client):
    """
    Verifies that the login page validates credentials and sets cookies.
    """
    # Fail credentials
    response = api_client.post("/login", data={"username": "wrong", "password": "wrong"})
    assert response.status_code == 200
    assert "Invalid username or password" in response.text
    
    # Success credentials
    response = api_client.post("/login", data={"username": DEFAULT_USERNAME, "password": "admin"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"
    assert "access_token" in response.cookies

def test_get_settings(api_client, auth_headers):
    """
    Checks settings retrieve endpoint.
    """
    response = api_client.get("/api/settings", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "minimum_match_score" in data
    assert "email_address" in data

def test_patch_settings(api_client, auth_headers):
    """
    Checks settings modification endpoint.
    """
    payload = {
        "minimum_match_score": 75,
        "email_address": "new_email@example.com"
    }
    response = api_client.patch("/api/settings", json=payload, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "success"

@patch("app.rag.retriever.Retriever")
@patch("app.agents.retrieval_agent.RetrievalAgent")
@patch("app.agents.application_agent.ApplicationAgent")
def test_human_approval_workflows(mock_agent_class, mock_retrieval_agent_class, mock_retriever_class, api_client, auth_headers):
    """
    Verifies that PATCH /api/applications/{id} with Approved status
    executes tailoring and updates SQLite statuses.
    """
    # Mock Retriever
    mock_retriever = MagicMock()
    mock_retriever_class.return_value = mock_retriever

    # Mock retrieval agent
    mock_retrieval_agent = MagicMock()
    mock_retrieval_agent.retrieve.return_value = ({"https://example.com/mock-url": "Context snippets"}, 0.1)
    mock_retrieval_agent_class.return_value = mock_retrieval_agent

    # Mock ApplicationAgent
    mock_agent = MagicMock()
    mock_agent.prepare_applications.return_value = [{
        "job_url": "https://example.com/mock-url",
        "company": "Mock Co",
        "position": "AI Architect",
        "status": "Draft",
        "resume_path": "data/test_applications/Mock_Co/resume.pdf",
        "cover_letter_path": "data/test_applications/Mock_Co/cover.pdf"
    }]
    mock_agent_class.return_value = mock_agent

    # Setup database records
    repo = JobRepository()
    repo.create_database()
    
    # Clean tables to ensure fresh test state
    with repo.session_provider() as session:
        from app.database.models import ApplicationModel, JobModel
        session.query(ApplicationModel).delete()
        session.query(JobModel).delete()
        session.commit()
    
    # 1. Insert mock Job
    job = repo.insert_job(
        JobCreate(
            title="AI Architect", company="Mock Co", location="Remote",
            job_url="https://example.com/mock-url", description="Description details",
            source="Wellfound", date_posted=datetime.now(timezone.utc)
        )
    )
    
    # 2. Insert Application log in "Pending Approval" status
    app_record = repo.create_application(
        job_id=job.id,
        company="Mock Co",
        position="AI Architect",
        status="Pending Approval"
    )
    
    # 3. Request human approval PATCH action
    payload = {"status": "Approved"}
    response = api_client.patch(f"/api/applications/{app_record.id}", json=payload, headers=auth_headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Draft"
    assert "resume.pdf" in data["resume_path"]
    
    # Double check database state got updated to "Draft"
    updated_db_app = repo.get_application_by_job_id(job.id)
    assert updated_db_app.status == "Draft"
