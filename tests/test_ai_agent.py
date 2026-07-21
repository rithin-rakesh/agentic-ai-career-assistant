import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager

from app.database.models import Base
from app.database.repository import JobRepository
from app.schemas.job import JobCreate, Job
from app.ai.parser import clean_json_string, parse_and_validate_json
from app.ai.llm_client import BaseLLM
from app.ai.job_matching_agent import JobMatchResult, JobMatchingAgent
from app.resume.resume_parser import Resume, ResumeParser
from app.services.ai_matching_service import AIMatchingService

# Test Mock LLM Client
class MockLLMClient(BaseLLM):
    def __init__(self, response_text: str):
        self.response_text = response_text
        self.calls = []

    def generate(self, system_prompt: str, user_prompt: str, response_format = None) -> str:
        self.calls.append((system_prompt, user_prompt))
        return self.response_text

@pytest.fixture
def mock_db():
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

def test_clean_json_string():
    """
    Checks that the JSON cleaner strips markdown wrappers and extracts raw object blocks.
    """
    raw_markdown = "Here is the response: \n```json\n{\n  \"match_score\": 90\n}\n```\nThanks!"
    cleaned = clean_json_string(raw_markdown)
    assert cleaned == "{\n  \"match_score\": 90\n}"

def test_parse_and_validate_json():
    """
    Verifies that parsed JSON correctly builds and validates a Pydantic model.
    """
    raw_json = "```json {\"match_score\": 85, \"should_apply\": true, \"priority\": \"High\", \"summary\": \"Ok\", \"strengths\": [], \"missing_skills\": [], \"learning_effort\": \"Low\", \"confidence\": 0.9} ```"
    result = parse_and_validate_json(raw_json, JobMatchResult)
    assert result.match_score == 85
    assert result.should_apply is True
    assert result.priority == "High"

def test_resume_parser():
    """
    Verifies that ResumeParser formats input prompts and returns a validated Resume.
    """
    mock_response = """
    {
      "skills": ["Python", "SQL"],
      "programming_languages": ["Python"],
      "frameworks": ["FastAPI"],
      "experience": [],
      "education": [],
      "projects": [],
      "certifications": []
    }
    """
    llm = MockLLMClient(mock_response)
    parser = ResumeParser(llm_client=llm)
    
    resume = parser.parse_resume_text("Raw resume content text.")
    
    assert len(llm.calls) == 1
    assert "Raw resume content text" in llm.calls[0][1]
    assert resume.skills == ["Python", "SQL"]
    assert resume.frameworks == ["FastAPI"]

def test_job_matching_agent_evaluation():
    """
    Verifies that JobMatchingAgent generates appropriate prompts and extracts matching details.
    """
    mock_match_json = """
    {
      "match_score": 95,
      "should_apply": true,
      "priority": "High",
      "summary": "Excellent engineering fit.",
      "strengths": ["Python", "SQLAlchemy"],
      "missing_skills": ["Docker"],
      "learning_effort": "Low",
      "confidence": 0.98
    }
    """
    llm = MockLLMClient(mock_match_json)
    agent = JobMatchingAgent(llm_client=llm)
    
    resume = Resume(
        skills=["Python"], programming_languages=["Python"], frameworks=["SQLAlchemy"],
        experience=[], education=[], projects=[], certifications=[]
    )
    
    evaluation = agent.evaluate_job(
        resume=resume,
        job_title="AI Engineer",
        job_company="AI Labs",
        job_location="Remote",
        job_source="Wellfound",
        job_description="Hiring Python engineer with SQLAlchemy experience."
    )
    
    assert evaluation["match_score"] == 95
    assert evaluation["should_apply"] is True
    assert evaluation["priority"] == "High"
    assert evaluation["strengths"] == ["Python", "SQLAlchemy"]
    assert evaluation["missing_skills"] == ["Docker"]

def test_ai_matching_service_integration(mock_db):
    """
    Checks the orchestration of AIMatchingService: pulling unevaluated database jobs,
    scoring them using the matching agent, and writing evaluation columns back to SQLite.
    """
    repo = JobRepository(session_provider=mock_db)
    
    # 1. Initialize SQLite schema
    repo.create_database()
    
    # 2. Pre-insert a job listing (no evaluation metrics initially)
    job_in = JobCreate(
        title="ML Engineer", company="Tech Solutions", location="Remote",
        job_url="https://example.com/ml-role", description="Python and PyTorch required.",
        source="Wellfound", date_posted=datetime.now(timezone.utc)
    )
    repo.insert_job(job_in)
    
    # Assert job is currently unevaluated
    unevaluated = repo.get_unevaluated_jobs()
    assert len(unevaluated) == 1
    assert unevaluated[0].match_score is None
    
    # 3. Setup Mock LLM that returns a structured matching evaluation
    mock_matching_payload = """
    {
      "match_score": 90,
      "should_apply": true,
      "priority": "High",
      "summary": "Fits resume nicely.",
      "strengths": ["Python", "PyTorch"],
      "missing_skills": [],
      "learning_effort": "Low",
      "confidence": 0.95
    }
    """
    llm = MockLLMClient(mock_matching_payload)
    
    # 4. Instantiate service and run evaluation
    service = AIMatchingService(repository=repo, llm_client=llm)
    # Patch resume loader to avoid loading from a missing local file path during test
    service.resume_path = "dummy_path"
    service._ensure_default_resume = MagicMock()
    
    # Mock loader read to return fake raw text
    from app.resume.resume_loader import ResumeLoader
    ResumeLoader.load_resume = MagicMock(return_value="Fake raw resume text")
    
    stats = service.evaluate_pending_jobs()
    
    # Assert metrics
    assert stats["total_pending"] == 1
    assert stats["processed"] == 1
    assert stats["failed"] == 0
    assert stats["recommended"] == 1
    
    # Verify SQLite database has updated columns
    jobs = repo.get_all_jobs()
    assert len(jobs) == 1
    assert jobs[0].match_score == 90
    assert jobs[0].should_apply is True
    assert jobs[0].priority == "High"
    assert jobs[0].summary == "Fits resume nicely."
    assert jobs[0].strengths == ["Python", "PyTorch"]
    assert jobs[0].missing_skills == []
    assert jobs[0].learning_effort == "Low"
    assert jobs[0].confidence == 0.95
    assert jobs[0].analysis_timestamp is not None
