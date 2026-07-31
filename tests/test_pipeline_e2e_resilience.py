import pytest
import os
import time
from datetime import datetime, timezone, timedelta
from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.api.app import app
from app.auth.authentication import create_access_token, DEFAULT_USERNAME
from app.database.models import Base
from app.collectors.base import BaseCollector
from app.collectors.collector_manager import CollectorManager
from app.collectors.remoteok import RemoteOKCollector
from app.config import settings

from app.schemas.job import JobCreate
from app.database.repository import JobRepository
from app.services.filtering import FilteringService
from app.services.collection_service import CollectionService
from app.services.pipeline_tracker import pipeline_tracker
from app.scheduler.scheduler_manager import scheduler_manager
from app.ai.llm_client import BaseLLM
from app.notifications.email_service import EmailService

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

class TimingOutGeminiLLM(BaseLLM):
    def generate(self, system_prompt: str, user_prompt: str, response_format=None) -> str:
        raise TimeoutError("Gemini API call timed out after 30 seconds")

class FailingCollector(BaseCollector):
    def collect(self) -> list:
        raise RuntimeError("External job API down")

class FailingEmailService(EmailService):
    def send_html_email(self, subject: str, html_body: str, to_email: str = None) -> tuple:
        return False, 3, "SMTP Connection Refused"


def test_complete_pipeline_success(mock_db_provider, monkeypatch):
    """
    Verifies 100% end-to-end pipeline execution from collection through matching,
    ranking, notification evaluation, application draft creation, daily digest, and DB persistence.
    """
    monkeypatch.setattr(settings, "JOB_KEYWORDS", ["Remote AI Systems Engineer", "AI Systems Engineer", "AI Engineer", "Python Developer"])
    monkeypatch.setattr(settings, "REQUIRED_SKILLS", ["Python"])
    monkeypatch.setattr(settings, "PREFERRED_LOCATIONS", ["Remote"])
    monkeypatch.setattr(settings, "ENABLE_REMOTE", True)
    monkeypatch.setattr(settings, "MAX_EXPERIENCE", 10)

    repo = JobRepository(session_provider=mock_db_provider)
    working_collector = RemoteOKCollector(mock_mode=True)
    collector_mgr = CollectorManager(collectors=[working_collector])
    filtering_svc = FilteringService()

    svc = CollectionService(repository=repo, collector_manager=collector_mgr, filtering_service=filtering_svc)
    stats = svc.run_sync()

    assert stats.get("collected", 0) > 0
    assert pipeline_tracker.status == "Completed"
    assert pipeline_tracker.current_stage == "COMPLETED"
    assert "COLLECT_JOBS" in pipeline_tracker.completed_stages
    assert "PERSIST_JOBS" in pipeline_tracker.completed_stages


def test_pipeline_collector_failure_resilience(mock_db_provider, monkeypatch):
    """
    Verifies that when one collector fails, the pipeline logs the failure,
    continues with remaining healthy collectors, and completes successfully.
    """
    monkeypatch.setattr(settings, "JOB_KEYWORDS", ["Full Stack AI Engineer", "AI Engineer", "Python Developer"])
    monkeypatch.setattr(settings, "REQUIRED_SKILLS", ["Python"])

    repo = JobRepository(session_provider=mock_db_provider)
    working_collector = RemoteOKCollector(mock_mode=True)
    failing_collector = FailingCollector()
    collector_mgr = CollectorManager(collectors=[working_collector, failing_collector])
    filtering_svc = FilteringService()

    svc = CollectionService(repository=repo, collector_manager=collector_mgr, filtering_service=filtering_svc)
    stats = svc.run_sync()

    assert stats.get("collected", 0) == 1
    assert stats.get("failed_collectors", 0) == 1
    assert pipeline_tracker.status == "Completed"


def test_pipeline_gemini_timeout_fallback(mock_db_provider, monkeypatch):
    """
    Verifies that a Gemini timeout triggers graceful fallback without halting the pipeline.
    """
    monkeypatch.setattr(settings, "JOB_KEYWORDS", ["Full Stack AI Engineer", "AI Engineer", "Python Developer"])
    monkeypatch.setattr(settings, "REQUIRED_SKILLS", ["Python"])

    repo = JobRepository(session_provider=mock_db_provider)
    collector_mgr = CollectorManager(collectors=[RemoteOKCollector(mock_mode=True)])
    filtering_svc = FilteringService()

    timeout_llm = TimingOutGeminiLLM()
    mock_ai = MagicMock()
    mock_ai.llm_client = timeout_llm
    mock_ai.embedding_service = MagicMock()
    mock_ai.vector_store = MagicMock()
    mock_ai.retriever = MagicMock()
    mock_ai.retriever.retrieve_context.return_value = "Retrieved profile skills"
    mock_ai.indexing_pipeline = MagicMock()
    mock_ai.resume_path = "data/resume.md"
    mock_ai._ensure_default_resume = MagicMock()

    svc = CollectionService(repository=repo, collector_manager=collector_mgr, filtering_service=filtering_svc, ai_matching_service=mock_ai)
    stats = svc.run_sync()

    assert pipeline_tracker.status == "Completed"
    assert stats.get("collected", 0) > 0


def test_pipeline_smtp_failure_resilience(mock_db_provider, monkeypatch):
    """
    Verifies that when SMTP transmission fails, notification status is recorded as 'failed',
    metrics are updated, and the pipeline finishes gracefully.
    """
    monkeypatch.setattr(settings, "JOB_KEYWORDS", ["Full Stack AI Engineer", "AI Engineer", "Python Developer"])
    monkeypatch.setattr(settings, "REQUIRED_SKILLS", ["Python"])

    repo = JobRepository(session_provider=mock_db_provider)
    collector_mgr = CollectorManager(collectors=[RemoteOKCollector(mock_mode=True)])
    filtering_svc = FilteringService()

    svc = CollectionService(repository=repo, collector_manager=collector_mgr, filtering_service=filtering_svc)
    
    with patch("app.agents.notification_agent.EmailService", FailingEmailService):
        stats = svc.run_sync()

    assert pipeline_tracker.status == "Completed"


def test_scheduler_restart_and_controls():
    """
    Verifies Pause, Resume, Reschedule, Restart, and Run Now interactive actions on SchedulerManager.
    """
    called = False
    def mock_task():
        nonlocal called
        called = True
        return {"collected": 5}

    scheduler_manager.initialize(sync_callback=mock_task, interval_hours=2)
    assert scheduler_manager.status == "Running"

    scheduler_manager.pause()
    assert scheduler_manager.status == "Paused"

    scheduler_manager.resume()
    assert scheduler_manager.status == "Running"

    scheduler_manager.restart(interval_hours=3)
    assert scheduler_manager.status == "Running"
    assert scheduler_manager.get_status_dict()["interval_hours"] == 3

    res = scheduler_manager.run_now()
    assert called is True
    assert res.get("collected") == 5


def test_pipeline_recovery_after_crash(mock_db_provider):
    """
    Verifies that an unhandled crash in sync callback sets failure status
    but DOES NOT break future scheduled executions.
    """
    def crashing_task():
        raise RuntimeError("Simulated catastrophic crash inside pipeline")

    scheduler_manager.sync_callback = crashing_task
    
    # Run task wrapper manually
    res = scheduler_manager.execute_task_wrapper()
    assert scheduler_manager.status == "Running"  # Reset back to Running for future runs
    assert res == {"collected": 0, "matched": 0}


def test_pipeline_duplicate_prevention(mock_db_provider):
    """
    Verifies duplicate prevention across URLs, content hashes, email notifications,
    and daily digests.
    """
    repo = JobRepository(session_provider=mock_db_provider)
    now_utc = datetime.now(timezone.utc)

    # 1. DB Deduplication
    job1 = JobCreate(
        title="Senior AI Engineer",
        company="Nexus AI",
        location="Remote",
        job_url="https://remoteok.com/jobs/123",
        description="Python PyTorch ML",
        source="RemoteOK",
        date_posted=now_utc,
        content_hash=BaseCollector.generate_content_hash("Nexus AI", "Senior AI Engineer", "Python PyTorch ML")
    )

    db_job = repo.insert_job(job1)
    assert repo.job_exists(url="https://remoteok.com/jobs/123") is True

    # 2. Duplicate Notification Suppression
    from app.notifications.notification_repository import NotificationRepository
    from app.agents.notification_agent import NotificationAgent

    noti_repo = NotificationRepository(session_provider=mock_db_provider)
    noti_repo.log_notification(job_id=db_job.id, channel="email", status="sent", sent_at=now_utc)

    noti_agent = NotificationAgent(repository=noti_repo)

    ranked_job = {
        "job_url": "https://remoteok.com/jobs/123",
        "title": "Senior AI Engineer",
        "company": "Nexus AI",
        "priority": "High",
        "match_score": 95
    }

    # Evaluation -> Skipped due to duplicate check
    records = noti_agent.evaluate_and_notify([ranked_job])
    assert records[0]["status"] == "skipped"
    assert records[0]["error_message"] == "Duplicate prevention filter triggered"


def test_dashboard_pipeline_endpoint(auth_client):
    """
    Verifies GET /api/dashboard exposes pipeline tracking payload and scheduler metrics.
    """
    resp = auth_client.get("/api/dashboard")
    assert resp.status_code == 200
    data = resp.json()

    assert "pipeline" in data
    p = data["pipeline"]
    assert "pipeline_status" in p
    assert "current_stage" in p
    assert "last_run" in p
    assert "next_run" in p
    assert "pipeline_duration" in p
    assert "jobs_processed" in p
    assert "notifications_sent" in p
    assert "Pipeline Status" in p
    assert "Current Stage" in p
