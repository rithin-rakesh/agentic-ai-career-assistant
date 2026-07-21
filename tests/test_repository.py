import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from contextlib import contextmanager

from app.database.models import Base
from app.database.repository import JobRepository, DuplicateJobError
from app.schemas.job import JobCreate

@pytest.fixture
def db_session_provider():
    """
    Fixture setting up an in-memory database and yielding a session provider.
    Each test gets a fresh, isolated database environment.
    """
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    @contextmanager
    def _session_provider():
        session = SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
            
    return _session_provider

def test_insert_and_get_job(db_session_provider):
    """
    Tests that jobs are successfully inserted and retrieved.
    """
    repo = JobRepository(session_provider=db_session_provider)
    
    job_in = JobCreate(
        title="Software Engineer",
        company="Tech Corp",
        location="Remote",
        job_url="https://example.com/jobs/1",
        description="A great software engineering role.",
        source="Wellfound",
        date_posted=datetime.now(timezone.utc)
    )
    
    # Insert job
    inserted_job = repo.insert_job(job_in)
    
    assert inserted_job.id is not None
    assert inserted_job.title == "Software Engineer"
    assert inserted_job.company == "Tech Corp"
    assert inserted_job.job_url == "https://example.com/jobs/1"
    
    # Retrieve all jobs
    jobs = repo.get_all_jobs()
    assert len(jobs) == 1
    assert jobs[0].id == inserted_job.id

def test_job_exists_and_count(db_session_provider):
    """
    Tests the duplicate check (job_exists) and count functionalities.
    """
    repo = JobRepository(session_provider=db_session_provider)
    url = "https://example.com/jobs/special"
    
    # Verify non-existence initially
    assert not repo.job_exists(url)
    assert repo.count_jobs() == 0
    
    job_in = JobCreate(
        title="ML Architect",
        company="Cognitive Inc",
        location="New York",
        job_url=url,
        description="Build LLM orchestrators.",
        source="Wellfound",
        date_posted=datetime.now(timezone.utc)
    )
    
    repo.insert_job(job_in)
    
    # Verify existence and count
    assert repo.job_exists(url)
    assert repo.count_jobs() == 1
    assert not repo.job_exists("https://example.com/jobs/other-one")

def test_repository_duplicate_job_error_url(db_session_provider):
    """
    Tests that inserting a job with an existing URL raises DuplicateJobError.
    """
    repo = JobRepository(session_provider=db_session_provider)
    url = "https://example.com/jobs/duplicate-check"
    
    job1 = JobCreate(
        title="Role A", company="Corp X", location="Location A", job_url=url, 
        description="Desc A", source="Wellfound", date_posted=datetime.now(timezone.utc)
    )
    job2 = JobCreate(
        title="Role B", company="Corp Y", location="Location B", job_url=url, 
        description="Desc B", source="Wellfound", date_posted=datetime.now(timezone.utc)
    )
    
    repo.insert_job(job1)
    
    # Second insert with same URL raises DuplicateJobError
    with pytest.raises(DuplicateJobError):
        repo.insert_job(job2)

def test_repository_duplicate_job_error_compound(db_session_provider):
    """
    Tests that inserting a job with the same company, title, and location
    raises DuplicateJobError, even if the URL is different.
    """
    repo = JobRepository(session_provider=db_session_provider)
    
    job1 = JobCreate(
        title="ML Engineer", company="AI Corp", location="Bangalore", 
        job_url="https://example.com/jobs/comp-1", description="Description 1", 
        source="Wellfound", date_posted=datetime.now(timezone.utc)
    )
    
    # Same company, title, location but different URL
    job2 = JobCreate(
        title="ML Engineer", company="AI Corp", location="Bangalore", 
        job_url="https://example.com/jobs/comp-2", description="Description 2", 
        source="Indeed", date_posted=datetime.now(timezone.utc)
    )
    
    repo.insert_job(job1)
    
    # Second insert with compound duplicate signature raises DuplicateJobError
    with pytest.raises(DuplicateJobError):
        repo.insert_job(job2)
