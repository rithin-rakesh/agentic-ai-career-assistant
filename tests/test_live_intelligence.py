import pytest
import time
from datetime import datetime, timezone, timedelta
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.api.app import app
from app.auth.authentication import create_access_token, DEFAULT_USERNAME
from app.database.models import Base
from app.collectors.base import BaseCollector
from app.collectors.collector_manager import CollectorManager
from app.collectors.remoteok import RemoteOKCollector
from app.collectors.arbeitnow import ArbeitnowCollector
from app.collectors.remotive import RemotiveCollector

from app.schemas.job import JobCreate
from app.database.repository import JobRepository, DuplicateJobError
from app.services.filtering import FilteringService
from app.agents.ranking_agent import RankingAgent
from app.config import settings

@pytest.fixture(autouse=True)
def patch_qdrant_memory(monkeypatch):
    """
    Forces Qdrant Vector DB to operate in :memory: mode during test execution to prevent file locks.
    """
    monkeypatch.setattr("app.config.settings.VECTOR_DB_URL", ":memory:")

@pytest.fixture
def mock_db_provider():
    """
    Sets up an in-memory SQLite database registering all tables.
    """
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
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

@pytest.fixture
def auth_client():
    """
    TestClient with access token cookie configured for authenticated endpoint testing.
    """
    with TestClient(app) as client:
        token = create_access_token(data={"sub": DEFAULT_USERNAME})
        client.cookies.set("access_token", token)
        yield client

class FailingCollector(BaseCollector):
    def collect(self) -> list:
        raise RuntimeError("Simulated external API timeout/down failure")

def test_collector_resilience_and_timeout():
    """
    Verifies that a failing collector does not crash CollectorManager and
    successful collectors' results are merged cleanly.
    """
    working_collector = RemoteOKCollector(mock_mode=True)
    failing_collector = FailingCollector()

    manager = CollectorManager(collectors=[working_collector, failing_collector])
    merged_jobs, failed_count = manager.collect_all()

    assert failed_count == 1
    assert len(merged_jobs) == 1
    assert merged_jobs[0].company == "Nexus AI"
    assert manager.collector_status["FailingCollector"]["status"] == "failed"
    assert manager.collector_status["RemoteOKCollector"]["status"] == "healthy"

def test_multi_stage_deduplication(mock_db_provider):
    """
    Verifies SHA-256 hash match, exact URL match, and normalized title+company match.
    """
    repo = JobRepository(session_provider=mock_db_provider)
    now_utc = datetime.now(timezone.utc)

    job1 = JobCreate(
        title="AI Engineer",
        company="TechCorp",
        location="Remote",
        job_url="https://example.com/job1",
        description="Python PyTorch ML",
        source="Test",
        date_posted=now_utc,
        content_hash=BaseCollector.generate_content_hash("TechCorp", "AI Engineer", "Python PyTorch ML")
    )

    repo.insert_job(job1)

    # 1. Exact URL duplicate check
    assert repo.job_exists(url="https://example.com/job1") is True

    # 2. SHA-256 content_hash duplicate check
    hash2 = BaseCollector.generate_content_hash("TechCorp", "AI Engineer", "Python PyTorch ML")
    assert repo.job_exists(url="https://example.com/job2", content_hash=hash2) is True

    # 3. Normalized Company + Title match
    assert repo.job_exists(url="https://example.com/job3", title="  ai engineer  ", company="techcorp") is True

    # 4. Non-duplicate job
    assert repo.job_exists(url="https://example.com/job4", title="Data Engineer", company="OtherCorp") is False

def test_smart_filtering_rules(monkeypatch):
    """
    Verifies blacklisted companies, ignored keywords, job age limits, and skill screening.
    """
    monkeypatch.setattr(settings, "JOB_KEYWORDS", ["AI Engineer", "Python Developer"])
    monkeypatch.setattr(settings, "REQUIRED_SKILLS", ["Python"])
    monkeypatch.setattr(settings, "PREFERRED_LOCATIONS", ["Remote"])
    monkeypatch.setattr(settings, "ENABLE_REMOTE", True)
    monkeypatch.setattr(settings, "BLACKLISTED_COMPANIES", ["ScamCorp"])
    monkeypatch.setattr(settings, "IGNORED_KEYWORDS", ["internship"])
    monkeypatch.setattr(settings, "MAX_JOB_AGE_DAYS", 30)

    service = FilteringService()
    now_utc = datetime.now(timezone.utc)

    # Valid Job
    job_valid = JobCreate(
        title="Senior AI Engineer",
        company="GoodTech",
        location="Remote",
        job_url="https://example.com/valid",
        description="Python ML position",
        source="Test",
        date_posted=now_utc
    )
    passed, reason = service.filter_job_with_reason(job_valid)
    assert passed is True
    assert reason == "passed"

    # Blacklisted Company Job
    job_blacklisted = JobCreate(
        title="AI Engineer",
        company="ScamCorp",
        location="Remote",
        job_url="https://example.com/blacklisted",
        description="Python position",
        source="Test",
        date_posted=now_utc
    )
    passed, reason = service.filter_job_with_reason(job_blacklisted)
    assert passed is False
    assert reason == "blacklisted_company"

    # Ignored Keyword Job (internship)
    job_internship = JobCreate(
        title="AI Engineer Internship",
        company="GoodTech",
        location="Remote",
        job_url="https://example.com/intern",
        description="Python position",
        source="Test",
        date_posted=now_utc
    )
    passed, reason = service.filter_job_with_reason(job_internship)
    assert passed is False
    assert reason == "ignored_keyword"

    # Stale Job (>30 days old)
    old_date = now_utc - timedelta(days=40)
    job_stale = JobCreate(
        title="Python Developer",
        company="GoodTech",
        location="Remote",
        job_url="https://example.com/stale",
        description="Python position",
        source="Test",
        date_posted=old_date
    )
    passed, reason = service.filter_job_with_reason(job_stale)
    assert passed is False
    assert reason == "stale_job"

def test_weighted_job_ranking():
    """
    Verifies multi-factor composite scoring and priority categorization (High, Medium, Low).
    """
    ranking_agent = RankingAgent()

    jobs = [
        {
            "title": "Lead AI Architect",
            "company": "TopAI",
            "location": "Remote",
            "remote_type": "Remote",
            "salary_range": "$150k",
            "job_url": "https://example.com/high"
        },
        {
            "title": "Junior Python Dev",
            "company": "LocalCo",
            "location": "Onsite",
            "salary_range": None,
            "job_url": "https://example.com/low"
        }
    ]

    match_results = {
        "https://example.com/high": {
            "match_score": 92,
            "career_growth_score": 90,
            "should_apply": True,
            "missing_skills": [],
            "confidence": 0.95
        },
        "https://example.com/low": {
            "match_score": 45,
            "career_growth_score": 40,
            "should_apply": False,
            "missing_skills": ["PyTorch", "Docker", "Kubernetes", "AWS"],
            "confidence": 0.60
        }
    }

    ranked = ranking_agent.rank_jobs(jobs, match_results)
    assert len(ranked) == 2
    assert ranked[0]["job_url"] == "https://example.com/high"
    assert ranked[0]["priority"] == "High"
    assert ranked[0]["composite_score"] >= 80.0
    assert ranked[1]["priority"] == "Low"

def test_dashboard_analytics_endpoint(auth_client):
    """
    Verifies GET /api/dashboard returns live collector status, missing skills, top companies, and priorities.
    """
    resp = auth_client.get("/api/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert "metrics" in data
    assert "collector_status" in data
    assert "top_companies" in data
    assert "top_missing_skills" in data
    assert "high_priority_jobs" in data

def test_prometheus_metrics_live_intelligence(auth_client):
    """
    Verifies /metrics endpoint exposes collector_requests_total, jobs_filtered_total, duplicate_jobs_total.
    """
    resp = auth_client.get("/metrics")
    assert resp.status_code == 200
    content = resp.text
    assert "collector_requests_total" in content
    assert "collector_latency_seconds" in content
    assert "jobs_filtered_total" in content
    assert "jobs_ranked_total" in content
    assert "duplicate_jobs_total" in content
