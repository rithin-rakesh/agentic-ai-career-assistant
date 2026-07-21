import pytest
from datetime import datetime, timezone
from app.services.filtering import FilteringService
from app.schemas.job import JobCreate

@pytest.fixture
def filter_service():
    return FilteringService()

def test_filter_by_title_allowed(filter_service):
    """
    Job passes filter if title contains allowed keywords (case-insensitive).
    """
    # Matching title
    job1 = JobCreate(
        title="Senior Python Developer", company="A", location="Remote",
        job_url="https://example.com/test-title-1",
        description="Must know Python and PyTorch.", source="Wellfound",
        date_posted=datetime.now(timezone.utc)
    )
    # Non-matching title
    job2 = JobCreate(
        title="React Frontend Developer", company="A", location="Remote",
        job_url="https://example.com/test-title-2",
        description="Must know Python and PyTorch.", source="Wellfound",
        date_posted=datetime.now(timezone.utc)
    )
    
    assert filter_service.filter_job(job1) is True
    assert filter_service.filter_job(job2) is False

def test_filter_by_location(filter_service):
    """
    Job passes if remote matches (when enable_remote=True) or contains preferred cities.
    """
    # Remote location -> Keep
    job_remote = JobCreate(
        title="AI Engineer", company="A", location="Fully Remote (Global)",
        job_url="https://example.com/test-loc-1",
        description="Python, Machine Learning experience.", source="Wellfound",
        date_posted=datetime.now(timezone.utc)
    )
    # Preferred city -> Keep
    job_preferred = JobCreate(
        title="AI Engineer", company="A", location="Bangalore, Karnataka",
        job_url="https://example.com/test-loc-2",
        description="Python, Machine Learning experience.", source="Wellfound",
        date_posted=datetime.now(timezone.utc)
    )
    # Non-preferred city -> Filter Out
    job_blocked = JobCreate(
        title="AI Engineer", company="A", location="New Delhi, India",
        job_url="https://example.com/test-loc-3",
        description="Python, Machine Learning experience.", source="Wellfound",
        date_posted=datetime.now(timezone.utc)
    )
    
    assert filter_service.filter_job(job_remote) is True
    assert filter_service.filter_job(job_preferred) is True
    assert filter_service.filter_job(job_blocked) is False

def test_filter_by_experience(filter_service):
    """
    Job gets excluded if experience specified in description exceeds MAX_EXPERIENCE.
    """
    # 1 year requirement -> Keep
    job_low_exp = JobCreate(
        title="ML Engineer", company="A", location="Remote",
        job_url="https://example.com/test-exp-1",
        description="Requires 1 year of experience in Python and PyTorch.", source="Wellfound",
        date_posted=datetime.now(timezone.utc)
    )
    # 5 years requirement -> Filter Out
    job_high_exp = JobCreate(
        title="ML Engineer", company="A", location="Remote",
        job_url="https://example.com/test-exp-2",
        description="Seeking candidates with 5+ years of experience in Deep Learning and PyTorch.", source="Wellfound",
        date_posted=datetime.now(timezone.utc)
    )
    # Range 1-3 years -> Keep (since lower range limit is 1 year)
    job_range_exp = JobCreate(
        title="ML Engineer", company="A", location="Remote",
        job_url="https://example.com/test-exp-3",
        description="Required 1-3 years of experience in SQL and Python.", source="Wellfound",
        date_posted=datetime.now(timezone.utc)
    )
    # Range 4-6 years -> Filter Out (lowest limit is 4 years)
    job_high_range_exp = JobCreate(
        title="ML Engineer", company="A", location="Remote",
        job_url="https://example.com/test-exp-4",
        description="Looking for 4-6 years experience in Machine Learning.", source="Wellfound",
        date_posted=datetime.now(timezone.utc)
    )
    # Entry level / fresher / no mention -> Keep
    job_entry_exp = JobCreate(
        title="ML Engineer", company="A", location="Remote",
        job_url="https://example.com/test-exp-5",
        description="Entry level role for Python developer. No experience required.", source="Wellfound",
        date_posted=datetime.now(timezone.utc)
    )
    
    assert filter_service.filter_job(job_low_exp) is True
    assert filter_service.filter_job(job_high_exp) is False
    assert filter_service.filter_job(job_range_exp) is True
    assert filter_service.filter_job(job_high_range_exp) is False
    assert filter_service.filter_job(job_entry_exp) is True

def test_filter_by_skills(filter_service):
    """
    Job passes only if it mentions at least one required skill keyword.
    """
    # Match skill 'TensorFlow' -> Keep
    job_skills_ok = JobCreate(
        title="ML Engineer", company="A", location="Remote",
        job_url="https://example.com/test-skill-1",
        description="Work with TensorFlow libraries.", source="Wellfound",
        date_posted=datetime.now(timezone.utc)
    )
    # No matching skills -> Filter Out
    job_skills_bad = JobCreate(
        title="ML Engineer", company="A", location="Remote",
        job_url="https://example.com/test-skill-2",
        description="Familiarity with HTML, CSS, React, and Django.", source="Wellfound",
        date_posted=datetime.now(timezone.utc)
    )
    
    assert filter_service.filter_job(job_skills_ok) is True
    assert filter_service.filter_job(job_skills_bad) is False
