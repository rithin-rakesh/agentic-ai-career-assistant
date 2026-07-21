import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager

from app.database.models import Base
from app.database.repository import JobRepository
from app.collectors.base import BaseCollector
from app.services.job_service import JobService
from app.schemas.job import JobCreate

# Mock Collector returning a deterministic list of jobs for test purposes
class MockCollector(BaseCollector):
    def __init__(self, jobs: list[JobCreate]):
        self.jobs = jobs

    def collect(self) -> list[JobCreate]:
        return self.jobs

@pytest.fixture
def test_db_provider():
    """
    Sets up an in-memory SQL database for isolation.
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

def test_service_sync_success_and_deduplication(test_db_provider):
    """
    Tests that JobService successfully collects jobs, inserts new ones,
    skips duplicates, and returns accurate statistics.
    """
    repo = JobRepository(session_provider=test_db_provider)
    now = datetime.now(timezone.utc)
    
    # 1. Pre-insert a job to simulate an existing duplicate in the database
    duplicate_url = "https://wellfound.com/jobs/dup-1"
    repo.insert_job(
        JobCreate(
            title="Old Job", company="Corp A", location="Remote", 
            job_url=duplicate_url, description="Old", source="Wellfound", date_posted=now
        )
    )
    
    # 2. Define the jobs returned by the collector
    collected_jobs = [
        # New job 1
        JobCreate(
            title="Python Developer", company="Fast Solutions", location="NYC",
            job_url="https://wellfound.com/jobs/new-1", description="FastAPI, SqlAlchemy",
            source="Wellfound", date_posted=now - timedelta(hours=1)
        ),
        # Duplicate job (same url as pre-inserted job)
        JobCreate(
            title="Old Job", company="Corp A", location="Remote",
            job_url=duplicate_url, description="Old description updated",
            source="Wellfound", date_posted=now
        ),
        # New job 2
        JobCreate(
            title="Frontend Dev", company="Pixel Perfect", location="LA",
            job_url="https://wellfound.com/jobs/new-2", description="React, CSS",
            source="Wellfound", date_posted=now
        )
    ]
    
    collector = MockCollector(collected_jobs)
    service = JobService(repository=repo, collector=collector)
    
    # 3. Run sync
    stats = service.sync_jobs()
    
    # Assert statistics
    assert stats["Collected"] == 3
    assert stats["Inserted"] == 2
    assert stats["Duplicates"] == 1
    assert stats["Failed"] == 0
    
    # Verify overall count in database (1 pre-inserted + 2 newly inserted = 3 total)
    assert repo.count_jobs() == 3
    assert repo.job_exists("https://wellfound.com/jobs/new-1")
    assert repo.job_exists("https://wellfound.com/jobs/new-2")

def test_service_error_handling_resilience(test_db_provider):
    """
    Tests that a database failure on a single job insertion does not abort the
    collection process for other valid jobs.
    """
    repo = JobRepository(session_provider=test_db_provider)
    now = datetime.now(timezone.utc)
    
    # We will simulate a failure by injecting a job that violates a database constraint.
    # While Pydantic validates input schemas, database-level issues can still happen
    # (e.g. database lock, text encoding error, or here a duplicate URL inserted simultaneously).
    # To cause an DB IntegrityError on the 2nd job, we repeat its URL.
    
    collected_jobs = [
        # Job 1 (valid)
        JobCreate(
            title="Job 1", company="Corp A", location="Remote",
            job_url="https://wellfound.com/jobs/resilient-1", description="D1",
            source="Wellfound", date_posted=now
        ),
        # Job 2 (duplicate url, but since it's in the same collection batch, if we bypass the
        # repository's job_exists check or if the DB insert throws IntegrityError)
        # Let's mock repository's insert_job to throw an Exception specifically for Job 2
        JobCreate(
            title="Job 2 (Faulty)", company="Corp B", location="Remote",
            job_url="https://wellfound.com/jobs/resilient-2", description="D2",
            source="Wellfound", date_posted=now
        ),
        # Job 3 (valid)
        JobCreate(
            title="Job 3", company="Corp C", location="Remote",
            job_url="https://wellfound.com/jobs/resilient-3", description="D3",
            source="Wellfound", date_posted=now
        )
    ]
    
    # Customize the insert_job behavior for tests to throw error on job 2
    original_insert = repo.insert_job
    def faulty_insert(job_in: JobCreate):
        if "resilient-2" in job_in.job_url:
            raise Exception("Mocked database connection failure during write.")
        return original_insert(job_in)
        
    repo.insert_job = faulty_insert
    
    collector = MockCollector(collected_jobs)
    service = JobService(repository=repo, collector=collector)
    
    # Run sync
    stats = service.sync_jobs()
    
    # Statistics check: 3 collected, 2 inserted (Job 1 & 3), 0 duplicates, 1 failed (Job 2)
    assert stats["Collected"] == 3
    assert stats["Inserted"] == 2
    assert stats["Failed"] == 1
    
    # Assert database holds only Job 1 and Job 3
    assert repo.count_jobs() == 2
    assert repo.job_exists("https://wellfound.com/jobs/resilient-1")
    assert repo.job_exists("https://wellfound.com/jobs/resilient-3")
    assert not repo.job_exists("https://wellfound.com/jobs/resilient-2")
