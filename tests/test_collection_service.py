import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager

from app.database.models import Base
from app.database.repository import JobRepository
from app.collectors.base import BaseCollector
from app.collectors.collector_manager import CollectorManager
from app.services.filtering import FilteringService
from app.services.collection_service import CollectionService
from app.schemas.job import JobCreate

# Define target Mock Collectors
class SuccessCollector(BaseCollector):
    def __init__(self, jobs: list[JobCreate]):
        self.jobs = jobs
    def collect(self) -> list[JobCreate]:
        return self.jobs

class FailureCollector(BaseCollector):
    def collect(self) -> list[JobCreate]:
        raise Exception("Connection timeout during HTTP request scraping.")

@pytest.fixture
def mock_db_provider():
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

def test_collector_manager_error_isolation():
    """
    Checks that the CollectorManager catches crashes on a single collector
    and proceeds to return jobs collected from other working collectors.
    """
    jobs = [
        JobCreate(
            title="AI Engineer", company="A", location="Remote",
            job_url="https://example.com/source1",
            description="Python and PyTorch.", source="Source1",
            date_posted=datetime.now(timezone.utc)
        )
    ]
    
    c1 = SuccessCollector(jobs)
    c2 = FailureCollector()
    
    manager = CollectorManager()
    manager.register_collector(c1)
    manager.register_collector(c2)
    
    collected_jobs, failed_count = manager.collect_all()
    
    # Verify we got jobs from SuccessCollector, failed count is 1, and no crash occurred
    assert len(collected_jobs) == 1
    assert failed_count == 1

def test_collection_service_pipeline_and_stats(mock_db_provider, monkeypatch):
    """
    Verifies that CollectionService runs collection, filters listings,
    filters duplicates (both URL and compound duplicates), and reports accurate stats.
    """
    monkeypatch.setattr("app.config.settings.VECTOR_DB_URL", ":memory:")
    repo = JobRepository(session_provider=mock_db_provider)
    filtering_service = FilteringService()
    
    # 1. Pre-insert a job to test compound duplicate detection later
    repo.insert_job(
        JobCreate(
            title="Python Developer", company="Original Corp", location="Remote",
            job_url="https://example.com/original-url", description="SQL, Python.",
            source="Indeed", date_posted=datetime.now(timezone.utc)
        )
    )
    
    raw_jobs = [
        # Job A: Valid, unique -> KEEP & INSERT
        JobCreate(
            title="AI Engineer", company="Unique Corp", location="Bangalore",
            job_url="https://example.com/unique-url", description="Need PyTorch, Python experience.",
            source="Wellfound", date_posted=datetime.now(timezone.utc)
        ),
        # Job B: Invalid title (React Dev) -> FILTER OUT
        JobCreate(
            title="React Frontend Developer", company="Unique Corp", location="Bangalore",
            job_url="https://example.com/react-dev", description="Need React, Javascript experience.",
            source="Wellfound", date_posted=datetime.now(timezone.utc)
        ),
        # Job C: Duplicate by URL (matches pre-inserted job) -> SKIP DUPLICATE
        JobCreate(
            title="Python Developer", company="Original Corp", location="Remote",
            job_url="https://example.com/original-url", description="SQL, Python.",
            source="Indeed", date_posted=datetime.now(timezone.utc)
        ),
        # Job D: Duplicate by Compound signature (Title, Company, Location matches pre-inserted, but different URL) -> SKIP DUPLICATE
        JobCreate(
            title="Python Developer", company="Original Corp", location="Remote",
            job_url="https://example.com/different-url-but-dup", description="SQL, Python.",
            source="Naukri", date_posted=datetime.now(timezone.utc)
        )
    ]
    
    success_collector = SuccessCollector(raw_jobs)
    failure_collector = FailureCollector()
    
    manager = CollectorManager()
    manager.register_collector(success_collector)
    manager.register_collector(failure_collector)
    
    service = CollectionService(
        repository=repo, 
        collector_manager=manager, 
        filtering_service=filtering_service
    )
    
    # Run sync
    stats = service.run_sync()
    
    # Total raw jobs collected = 4 from success collector + 0 from failure collector = 4
    assert stats["collected"] == 4
    assert stats["failed_collectors"] == 1
    
    # Job B (React Developer) should be filtered out. Total filtered out = 1
    assert stats["filtered"] == 1
    
    # Duplicate calculations:
    # Remaining jobs: Job A (valid), Job C (URL dup), Job D (Compound dup)
    # Job A -> inserted (1)
    # Job C -> duplicate (1)
    # Job D -> duplicate (2)
    assert stats["duplicates"] == 2
    assert stats["inserted"] == 1
    
    # Double check final repository count (1 pre-inserted + 1 newly inserted = 2 total)
    assert repo.count_jobs() == 2
