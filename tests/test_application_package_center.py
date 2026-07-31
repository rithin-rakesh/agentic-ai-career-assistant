import os
import pytest
from datetime import datetime, timezone
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.api.app import app
from app.auth.authentication import create_access_token, DEFAULT_USERNAME
from app.database.models import Base, JobModel, ApplicationModel, CareerDecisionModel
from app.database.repository import JobRepository

@pytest.fixture(autouse=True)
def patch_qdrant_memory(monkeypatch):
    """
    Forces Qdrant Vector DB to operate in :memory: mode during test execution to prevent file locks.
    """
    monkeypatch.setattr("app.config.settings.VECTOR_DB_URL", ":memory:")

@pytest.fixture
def mock_db_provider(tmp_path):
    db_file = tmp_path / "test_app_pkg.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    @contextmanager
    def _provider():
        session = SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
            
    return _provider

@pytest.fixture(autouse=True)
def patch_db_session(mock_db_provider, monkeypatch):
    monkeypatch.setattr("app.database.database.get_db_session", mock_db_provider)
    monkeypatch.setattr("app.database.repository.get_db_session", mock_db_provider)

@pytest.fixture
def auth_client():
    with TestClient(app) as client:
        token = create_access_token(data={"sub": DEFAULT_USERNAME})
        client.cookies.set("access_token", token)
        yield client

@pytest.fixture
def sample_package_db(mock_db_provider, tmp_path):
    repo = JobRepository(session_provider=mock_db_provider)
    now_utc = datetime.now(timezone.utc)

    # 1. Create sample job
    with repo.session_provider() as session:
        job = JobModel(
            title="Principal AI Architect",
            company="Quantum AI Labs",
            location="San Francisco, CA",
            job_url="https://example.com/jobs/quantum-ai-principal-101",
            apply_url="https://example.com/apply/quantum-ai-principal-101",
            description="Leading multi-agent system design and RAG pipelines.",
            source="RemoteOK",
            date_posted=now_utc,
            match_score=94,
            priority="High",
            summary="Exceptional fit for AI systems leadership.",
            strengths='["Python", "LangGraph", "FastAPI"]',
            missing_skills='["Kubernetes"]',
            learning_effort="Low",
            employment_type="Full-time",
            salary_range="$220k - $260k"
        )
        session.add(job)
        session.flush()

        # 2. Create sample files
        res_file = tmp_path / "quantum_ai_resume.pdf"
        res_file.write_text("%PDF-1.4 sample resume content")
        
        res_md_file = tmp_path / "quantum_ai_resume.md"
        res_md_file.write_text("# Tailored Resume\n- Senior AI Engineer")

        cl_file = tmp_path / "quantum_ai_cover_letter.pdf"
        cl_file.write_text("%PDF-1.4 sample cover letter content")

        cl_md_file = tmp_path / "quantum_ai_cover_letter.md"
        cl_md_file.write_text("# Cover Letter\nDear Hiring Team")

        # 3. Create application
        app_rec = ApplicationModel(
            job_id=job.id,
            company=job.company,
            position=job.title,
            status="Ready",
            resume_path=str(res_file),
            cover_letter_path=str(cl_file)
        )
        session.add(app_rec)

        # 4. Create career decision
        cd = CareerDecisionModel(
            job_id=job.id,
            recommendation="Apply Immediately",
            confidence=0.95,
            priority="High",
            estimated_interview_probability="92%",
            career_growth="Very High",
            salary_competitiveness="Top 5%",
            learning_effort="Low",
            resume_changes_required=True,
            cover_letter_required=True
        )
        session.add(cd)
        session.flush()
        
        app_id = app_rec.id
        job_id = job.id

    from app.database.database import get_db_session
    app.dependency_overrides[JobRepository] = lambda: repo
    app.dependency_overrides[get_db_session] = mock_db_provider

    yield {
        "repo": repo,
        "app_id": app_id,
        "job_id": job_id,
        "res_file": str(res_file),
        "cl_file": str(cl_file)
    }
    
    app.dependency_overrides.clear()


def test_application_package_detail_endpoint(auth_client, sample_package_db):
    """
    Verifies GET /api/applications/{id} exposes combined Application, Job, and Decision metadata.
    """
    app_id = sample_package_db["app_id"]
    resp = auth_client.get(f"/api/applications/{app_id}")
        
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == app_id
    assert data["company"] == "Quantum AI Labs"
    assert data["position"] == "Principal AI Architect"
    assert data["match_score"] == 94
    assert data["estimated_interview_probability"] == "92%"
    assert data["recommendation"] == "Apply Immediately"
    assert "Python" in data["strengths"]
    assert "Kubernetes" in data["missing_skills"]
    assert data["job_url"] == "https://example.com/jobs/quantum-ai-principal-101"


def test_download_resume_pdf_and_md(auth_client, sample_package_db):
    """
    Verifies GET /api/applications/{id}/download/resume/pdf and /md secure file download routes.
    """
    repo = sample_package_db["repo"]
    app_id = sample_package_db["app_id"]

    with pytest.MonkeyPatch.context() as m:
        m.setattr("app.api.routes.applications.JobRepository", lambda: repo)
        
        # Download PDF
        resp_pdf = auth_client.get(f"/api/applications/{app_id}/download/resume/pdf")
        assert resp_pdf.status_code == 200
        assert resp_pdf.headers["content-type"] == "application/pdf"
        assert len(resp_pdf.content) > 0

        # Download MD
        resp_md = auth_client.get(f"/api/applications/{app_id}/download/resume/md")
        assert resp_md.status_code == 200
        assert "text/markdown" in resp_md.headers["content-type"] or "text/plain" in resp_md.headers["content-type"]


def test_download_cover_letter_pdf_and_md(auth_client, sample_package_db):
    """
    Verifies GET /api/applications/{id}/download/cover-letter/pdf and /md secure file download routes.
    """
    repo = sample_package_db["repo"]
    app_id = sample_package_db["app_id"]

    with pytest.MonkeyPatch.context() as m:
        m.setattr("app.api.routes.applications.JobRepository", lambda: repo)

        resp_pdf = auth_client.get(f"/api/applications/{app_id}/download/cover-letter/pdf")
        assert resp_pdf.status_code == 200
        assert resp_pdf.headers["content-type"] == "application/pdf"

        resp_md = auth_client.get(f"/api/applications/{app_id}/download/cover-letter/md")
        assert resp_md.status_code == 200


def test_missing_file_handling_returns_404_json(auth_client, mock_db_provider):
    """
    Verifies clean HTTP 404 JSON response when a document file is missing from disk.
    Never throws server 500 exceptions.
    """
    repo = JobRepository(session_provider=mock_db_provider)
    now_utc = datetime.now(timezone.utc)

    with repo.session_provider() as session:
        job = JobModel(
            title="Systems Dev",
            company="Ghost Corp",
            location="Remote",
            job_url="https://example.com/jobs/ghost-1",
            description="Python",
            source="RemoteOK",
            date_posted=now_utc
        )
        session.add(job)
        session.flush()

        app_rec = ApplicationModel(
            job_id=job.id,
            company=job.company,
            position=job.title,
            status="Ready",
            resume_path="data/resumes/non_existent_file.pdf",
            cover_letter_path="data/cover_letters/non_existent_file.pdf"
        )
        session.add(app_rec)
        session.flush()
        missing_app_id = app_rec.id

    from app.database.database import get_db_session
    app.dependency_overrides[JobRepository] = lambda: repo
    app.dependency_overrides[get_db_session] = mock_db_provider
    
    # Test download missing resume -> 404 JSON
    res_resp = auth_client.get(f"/api/applications/{missing_app_id}/download/resume/pdf")
    assert res_resp.status_code == 404
    assert "not found" in res_resp.json()["detail"].lower()

    # Test download missing non-existent application -> 404 JSON
    bad_resp = auth_client.get("/api/applications/99999/download/resume/pdf")
    assert bad_resp.status_code == 404

    app.dependency_overrides.clear()


def test_application_status_update_transitions(auth_client, sample_package_db):
    """
    Verifies PATCH /api/applications/{id} transitions statuses (Applied, Interview, Offer, Rejected).
    """
    repo = sample_package_db["repo"]
    app_id = sample_package_db["app_id"]

    with pytest.MonkeyPatch.context() as m:
        m.setattr("app.api.routes.applications.JobRepository", lambda: repo)

        for new_st in ["Applied", "Interview", "Offer", "Rejected"]:
            resp = auth_client.patch(f"/api/applications/{app_id}", json={"status": new_st})
            assert resp.status_code == 200
            assert resp.json()["status"] == new_st


def test_application_package_html_page(auth_client, sample_package_db):
    """
    Verifies HTML view GET /applications/{id} renders Application Package Center summary page.
    """
    app_id = sample_package_db["app_id"]
    resp = auth_client.get(f"/applications/{app_id}")

    assert resp.status_code == 200
    assert "Application Package Center" in resp.text
    assert "Quantum AI Labs" in resp.text
    assert "Apply Now" in resp.text
