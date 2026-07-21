import os
import shutil
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager

from app.config import settings
from app.database.models import Base, JobModel
from app.database.repository import JobRepository
from app.notifications.notification_models import NotificationModel
from app.notifications.notification_repository import NotificationRepository
from app.notifications.email_service import EmailService
from app.notifications.template_engine import TemplateEngine
from app.agents.notification_agent import NotificationAgent
from app.agents.digest_agent import DigestAgent

@pytest.fixture
def mock_db_provider():
    """
    Sets up an in-memory SQLite database registering both jobs and notifications tables.
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

def test_template_engine_rendering():
    """
    Checks that template engine compiles and renders Jinja2 layouts successfully.
    """
    engine = TemplateEngine()
    dummy_job = {
        "title": "Principal Lead AI Architect",
        "company": "DeepMind Partner Corp",
        "location": "London, UK",
        "match_score": 98,
        "summary": "Outstanding deep learning expert profile match.",
        "missing_skills": "Rust, Kubernetes",
        "job_url": "https://example.com/lead-ai"
    }
    
    # 1. Test instant alert template
    instant_html = engine.render("instant_alert.html", {"job": dummy_job})
    assert "Principal Lead AI Architect" in instant_html
    assert "DeepMind Partner Corp" in instant_html
    assert "98% Match Score" in instant_html
    assert "Outstanding deep learning expert" in instant_html
    assert "Rust, Kubernetes" in instant_html
    assert "https://example.com/lead-ai" in instant_html
    
    # 2. Test daily digest template
    digest_html = engine.render("daily_digest.html", {
        "high_priority_jobs": [dummy_job],
        "medium_priority_jobs": [],
        "date": "July 19, 2026"
    })
    assert "Daily AI Career Report" in digest_html
    assert "July 19, 2026" in digest_html
    assert "Principal Lead AI Architect" in digest_html

def test_email_service_mock_fallback():
    """
    Checks that EmailService operates in mock mode successfully by saving files.
    """
    service = EmailService()
    service.is_mock = True
    
    subject = "Mock Test Alert Subject Line"
    html_content = "<h1>Test HTML Email Template Content</h1>"
    
    success, attempts, err_msg = service.send_html_email(subject, html_content)
    
    assert success is True
    assert attempts == 1
    assert err_msg is None
    
    # Verify file was written to data/sent_emails/
    sent_dir = os.path.join(settings.BASE_DIR, "data", "sent_emails")
    assert os.path.exists(sent_dir)
    
    files = os.listdir(sent_dir)
    assert len(files) > 0
    
    # Check that one of the files contains the subject keyword
    found = False
    for filename in files:
        if "Mock_Test_Alert_Subject_Line" in filename:
            found = True
            filepath = os.path.join(sent_dir, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                assert html_content in content
            break
    assert found is True

@patch("smtplib.SMTP")
def test_email_service_smtp_retries(mock_smtp):
    """
    Asserts that EmailService live SMTP connection errors trigger configured retry backoffs.
    """
    service = EmailService()
    service.is_mock = False  # Force SMTP mode
    service.retries = 3
    
    # Mock SMTP to raise connection exceptions
    mock_smtp.side_effect = Exception("SMTP Host connection timeout error")
    
    with patch("time.sleep") as mock_sleep:  # Prevent slowing down tests
        success, attempts, err_msg = service.send_html_email(
            "SMTP Target Subject", 
            "<p>HTML</p>"
        )
        
        assert success is False
        assert attempts == 3
        assert "SMTP Host connection timeout error" in err_msg
        assert mock_sleep.call_count == 2  # Sleeps for attempt 1 (2s) and attempt 2 (4s)

def test_notification_agent_routing_and_duplicates(mock_db_provider):
    """
    Checks that NotificationAgent prioritizes and routes High/Medium/Low priority jobs,
    skips duplicate alerts, and records log results correctly.
    """
    repo = NotificationRepository(session_provider=mock_db_provider)
    job_repo = JobRepository(session_provider=mock_db_provider)
    
    # Create and mock EmailService
    email_service = MagicMock(spec=EmailService)
    email_service.send_html_email.return_value = (True, 1, None)
    
    agent = NotificationAgent(
        email_service=email_service,
        template_engine=TemplateEngine(),
        repository=repo
    )
    
    ranked_jobs = [
        # Job A: High Priority -> INSTANT ALERT (sent)
        {
            "title": "Staff AI Engineer", "company": "HighTech", "location": "Remote",
            "job_url": "https://example.com/high-job", "priority": "High", "match_score": 92
        },
        # Job B: Medium Priority -> DAILY DIGEST QUEUE (queued)
        {
            "title": "Backend developer", "company": "MidTech", "location": "Remote",
            "job_url": "https://example.com/mid-job", "priority": "Medium", "match_score": 75
        },
        # Job C: Low Priority -> NO ACTION (skipped)
        {
            "title": "Intern", "company": "LowTech", "location": "Remote",
            "job_url": "https://example.com/low-job", "priority": "Low", "match_score": 40
        }
    ]
    
    # 1. Execute agent evaluation on empty history database
    records = agent.evaluate_and_notify(ranked_jobs)
    
    assert len(records) == 3
    
    # Job A routing check
    assert records[0]["job_url"] == "https://example.com/high-job"
    assert records[0]["status"] == "sent"
    
    # Job B routing check
    assert records[1]["job_url"] == "https://example.com/mid-job"
    assert records[1]["status"] == "queued"
    
    # Job C routing check
    assert records[2]["job_url"] == "https://example.com/low-job"
    assert records[2]["status"] == "skipped"
    
    # Assert EmailService was called exactly once (for the High Priority alert)
    email_service.send_html_email.assert_called_once()
    
    # 2. Simulate persistence to test duplicate prevention check on next runs
    # Pre-insert Job A and write a successful sent notification record
    from app.schemas.job import JobCreate
    db_job_a = job_repo.insert_job(
        JobCreate(
            title="Staff AI Engineer", company="HighTech", location="Remote",
            job_url="https://example.com/high-job", description="Python AI",
            source="Wellfound", date_posted=datetime.now(timezone.utc)
        )
    )
    repo.log_notification(job_id=db_job_a.id, channel="email", status="sent")
    
    # Verify that Job A is now flagged as notified
    assert repo.has_been_notified("https://example.com/high-job") is True
    assert repo.has_been_notified("https://example.com/mid-job") is False
    
    # Run agent again: Job A should now be SKIPPED as duplicate
    email_service.reset_mock()
    new_records = agent.evaluate_and_notify([ranked_jobs[0]])
    
    assert len(new_records) == 1
    assert new_records[0]["job_url"] == "https://example.com/high-job"
    assert new_records[0]["status"] == "skipped"
    assert "Duplicate prevention" in new_records[0]["error_message"]
    email_service.send_html_email.assert_not_called()

def test_digest_agent_compilation():
    """
    Asserts that DigestAgent compiles grouped priority lists and delivers the email.
    """
    email_service = MagicMock(spec=EmailService)
    email_service.send_html_email.return_value = (True, 1, None)
    
    agent = DigestAgent(
        email_service=email_service,
        template_engine=TemplateEngine()
    )
    
    high_priority = [
        {"title": "AI Director", "company": "FAANG", "location": "US", "match_score": 96, "summary": "Great", "missing_skills": "None", "job_url": "url1"}
    ]
    medium_priority = [
        {"title": "Lead Dev", "company": "Startup", "location": "Remote", "match_score": 79, "summary": "Good", "missing_skills": "Docker", "job_url": "url2"}
    ]
    
    success, attempts, err_msg = agent.send_daily_digest(high_priority, medium_priority)
    
    assert success is True
    assert attempts == 1
    assert err_msg is None
    email_service.send_html_email.assert_called_once()
    
    # Extract subject arg from mock call
    call_args = email_service.send_html_email.call_args[0]
    assert "Daily AI Career Report" in call_args[0]
