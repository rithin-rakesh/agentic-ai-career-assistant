import os
import shutil
import json
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager

from app.config import settings
from app.database.models import Base
from app.database.repository import JobRepository
from app.memory.application_memory import ApplicationMemoryManager
from app.resume.resume_generator import ResumeDocumentGenerator
from app.cover_letters.generator import CoverLetterGenerator
from app.agents.resume_agent import ResumeAgent
from app.agents.cover_letter_agent import CoverLetterAgent
from app.agents.skills_agent import SkillsAgent
from app.agents.memory_agent import MemoryAgent
from app.agents.application_agent import ApplicationAgent

@pytest.fixture
def temp_output_dir():
    """
    Creates a temporary output directory for document generations and cleans it up.
    """
    path = os.path.join(settings.BASE_DIR, "data", "test_applications")
    os.makedirs(path, exist_ok=True)
    yield path
    if os.path.exists(path):
        shutil.rmtree(path)

@pytest.fixture
def temp_memory_file():
    """
    Creates a temporary memory JSON path.
    """
    path = os.path.join(settings.BASE_DIR, "data", "test_career_memory.json")
    if os.path.exists(path):
        os.remove(path)
    yield path
    if os.path.exists(path):
        os.remove(path)

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

def test_resume_document_generator(temp_output_dir):
    """
    Checks that ResumeDocumentGenerator successfully compiles MD, DOCX, and PDF resume formats.
    """
    generator = ResumeDocumentGenerator()
    
    md_content = """# Jane Developer
Email: jane@dev.com | Phone: +1-555-0299

## Professional Summary
Python engineer specializing in building AI systems.

## Experience
### Junior Python Developer
**AI Solutions Inc** &bull; 2024 - Present
- Tailored RAG models.
- Refactored SQLAlchemy endpoints.
"""
    base_path = os.path.join(temp_output_dir, "test_resume")
    paths = generator.generate(md_content, base_path)
    
    # Assert correct keys are returned
    assert "markdown" in paths
    assert "docx" in paths
    assert "pdf" in paths
    
    # Assert files exist in filesystem
    assert os.path.exists(paths["markdown"])
    assert os.path.exists(paths["docx"])
    assert os.path.exists(paths["pdf"])
    
    # Assert MD content was written
    with open(paths["markdown"], "r", encoding="utf-8") as f:
        read_text = f.read()
        assert "Jane Developer" in read_text
        assert "AI Solutions Inc" in read_text

def test_cover_letter_generator(temp_output_dir):
    """
    Checks that CoverLetterGenerator compiles MD, DOCX, and PDF Cover Letter formats.
    """
    generator = CoverLetterGenerator()
    
    md_content = """# Alex Candidate
Email: alex@dev.com

## July 19, 2026

Dear Hiring Manager,
I am excited to apply for the Python Role.
"""
    base_path = os.path.join(temp_output_dir, "test_cl")
    paths = generator.generate(md_content, base_path)
    
    assert "markdown" in paths
    assert "docx" in paths
    assert "pdf" in paths
    assert os.path.exists(paths["markdown"])
    assert os.path.exists(paths["docx"])
    assert os.path.exists(paths["pdf"])

def test_career_memory_manager(temp_memory_file):
    """
    Asserts that ApplicationMemoryManager loads, saves, updates statuses,
    applies list transitions, and checks package duplicates correctly.
    """
    manager = ApplicationMemoryManager(file_path=temp_memory_file)
    
    # 1. Default load checks
    assert len(manager.memory["applied_jobs"]) == 0
    assert "Python" in manager.memory["preferred_technologies"]
    
    # 2. Add application check
    job_url = "https://example.com/ml-architect"
    manager.add_applied_job(job_url, "OpenAI", "ML Architect", "Draft", "/res.pdf", "/cl.pdf")
    
    assert len(manager.memory["applied_jobs"]) == 1
    assert manager.memory["applied_jobs"][0]["company"] == "OpenAI"
    assert manager.memory["applied_jobs"][0]["status"] == "Draft"
    assert manager.has_generated_package(job_url) is True
    
    # 3. Status transition checks
    manager.update_status(job_url, "Interview")
    assert manager.memory["applied_jobs"][0]["status"] == "Interview"
    assert job_url in manager.memory["interview_invitations"]
    
    manager.update_status(job_url, "Rejected")
    assert manager.memory["applied_jobs"][0]["status"] == "Rejected"
    assert job_url in manager.memory["rejected_jobs"]

def test_memory_agent_preferences_matching(temp_memory_file):
    """
    Checks that MemoryAgent flags blocked companies and identifies favorite companies.
    """
    manager = ApplicationMemoryManager(file_path=temp_memory_file)
    manager.memory["ignored_companies"] = ["BlockedCorp"]
    manager.memory["favorite_companies"] = ["FavoriteCorp"]
    manager.save_memory()
    
    agent = MemoryAgent(memory_manager=manager)
    
    # Check ignored company block
    blocked, fav, reason = agent.process_preferences({"company": "BlockedCorp", "location": "Remote", "description": "Python"})
    assert blocked is True
    assert fav is False
    assert "ignored" in reason
    
    # Check favorite company highlight
    blocked, fav, reason = agent.process_preferences({"company": "FavoriteCorp", "location": "Remote", "description": "Python"})
    assert blocked is False
    assert fav is True
    assert "favorite" in reason

def test_application_agent_pipeline(temp_output_dir, temp_memory_file, mock_db_provider):
    """
    Checks the full autonomous application pipeline flow:
    - High priority job matching generates documents.
    - Career Memory logs check prevents regeneration.
    - Application records successfully persist to database.
    """
    # 1. Setup mock agents
    res_agent = ResumeAgent()
    res_agent.llm_client = MagicMock()
    res_agent.llm_client.mock_mode = True
    
    cl_agent = CoverLetterAgent()
    cl_agent.llm_client = MagicMock()
    cl_agent.llm_client.mock_mode = True
    
    skills_agent = SkillsAgent()
    skills_agent.llm_client = MagicMock()
    skills_agent.llm_client.mock_mode = True
    
    memory_manager = ApplicationMemoryManager(file_path=temp_memory_file)
    
    agent = ApplicationAgent(
        resume_agent=res_agent,
        cl_agent=cl_agent,
        skills_agent=skills_agent,
        memory_manager=memory_manager
    )
    
    # Override settings output directory
    settings.OUTPUT_DIRECTORY = temp_output_dir
    
    ranked_jobs = [
        # Job A: High Priority -> Process (generates files)
        {
            "job_url": "https://example.com/job-a", "title": "AI Engineer",
            "company": "DeepMind", "location": "London", "priority": "High", "match_score": 90
        },
        # Job B: Low Priority -> Skipped
        {
            "job_url": "https://example.com/job-b", "title": "Intern",
            "company": "IgnoreCorp", "location": "Remote", "priority": "Low", "match_score": 40
        }
    ]
    
    retrieved_context = {"https://example.com/job-a": "Candidate is expert in ML."}
    
    # 2. Run Preparation Agent
    packages = agent.prepare_applications(ranked_jobs, retrieved_context)
    
    assert len(packages) == 1
    assert packages[0]["company"] == "DeepMind"
    assert packages[0]["status"] == "Draft"
    assert "resume_tailored" in packages[0]["resume_path"]
    assert "cover_letter" in packages[0]["cover_letter_path"]
    assert os.path.exists(packages[0]["learning_plan_path"])
    
    # Verify memory got updated
    assert memory_manager.has_generated_package("https://example.com/job-a") is True
    
    # 3. Duplicate prevention: run again, documents should NOT be regenerated (returned from cache)
    res_agent.llm_client.generate.reset_mock()
    new_packages = agent.prepare_applications(ranked_jobs, retrieved_context)
    
    assert len(new_packages) == 1
    assert new_packages[0]["company"] == "DeepMind"
    # LLM should not be called because it was resolved from cache
    res_agent.llm_client.generate.assert_not_called()
    
    # 4. Persistence verification: save records to SQLite DB
    job_repo = JobRepository(session_provider=mock_db_provider)
    
    # Pre-insert Job A
    from app.schemas.job import JobCreate
    db_job = job_repo.insert_job(
        JobCreate(
            title="AI Engineer", company="DeepMind", location="London",
            job_url="https://example.com/job-a", description="Python AI",
            source="Wellfound", date_posted=datetime.now(timezone.utc)
        )
    )
    
    # Simulate DB persistence from PersistenceAgent using create_application repo calls
    db_app = job_repo.create_application(
        job_id=db_job.id,
        company=packages[0]["company"],
        position=packages[0]["position"],
        status=packages[0]["status"],
        resume_path=packages[0]["resume_path"],
        cover_letter_path=packages[0]["cover_letter_path"]
    )
    
    assert db_app.id is not None
    assert db_app.job_id == db_job.id
    assert db_app.status == "Draft"
    
    # Verify we can fetch it back
    fetched = job_repo.get_application_by_job_id(db_job.id)
    assert fetched is not None
    assert fetched.company == "DeepMind"
    
    # Verify we can update status
    job_repo.update_application_status(fetched.id, "Applied", datetime.now(timezone.utc))
    fetched_updated = job_repo.get_application_by_job_id(db_job.id)
    assert fetched_updated.status == "Applied"
    assert fetched_updated.applied_at is not None
