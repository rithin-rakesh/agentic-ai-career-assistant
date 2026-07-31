import pytest
from unittest.mock import MagicMock, patch

from app.ai.llm_client import BaseLLM, GeminiClient, MockLLM, get_llm_client
from app.agents.retrieval_agent import RetrievalAgent
from app.agents.matching_agent import MatchingAgent
from app.agents.ranking_agent import RankingAgent
from app.agents.career_strategy_agent import CareerStrategyAgent
from app.agents.resume_agent import ResumeAgent
from app.agents.cover_letter_agent import CoverLetterAgent
from app.agents.digest_agent import DigestAgent
from app.agents.notification_agent import NotificationAgent

@pytest.fixture(autouse=True)
def patch_environment(monkeypatch):
    monkeypatch.setattr("app.config.settings.VECTOR_DB_URL", ":memory:")
    GeminiClient._shared_client = None
    GeminiClient._shared_key = None
    GeminiClient._llm_cache = {}
    try:
        from app.memory.application_memory import ApplicationMemoryManager
        mem_mgr = ApplicationMemoryManager()
        mem_mgr.memory["ai_settings"] = {}
        mem_mgr.save_memory()
    except Exception:
        pass

def test_retrieval_agent_gemini_integration():
    mock_retriever = MagicMock()
    mock_retriever.retrieve_relevant_context.return_value = (
        [{"chunk_id": "c1", "metadata": {"section": "Skills"}, "content": "Python, Gemini"}],
        0.95,
        0.05
    )
    agent = RetrievalAgent(retriever=mock_retriever, llm_client=MockLLM())
    jobs = [{"job_url": "http://example.com/j1", "title": "AI Engineer", "description": "Python, Gemini"}]
    contexts, metrics = agent.retrieve(jobs)

    assert "http://example.com/j1" in contexts
    assert "Section: Skills" in contexts["http://example.com/j1"]

def test_matching_agent_gemini_integration():
    agent = MatchingAgent(llm_client=MockLLM())
    jobs = [{"job_url": "http://example.com/j2", "title": "GenAI Dev", "company": "Tech Corp", "description": "FastAPI, Gemini"}]
    contexts = {"http://example.com/j2": "Candidate experience: Python, FastAPI"}
    results = agent.match_jobs(jobs, contexts, {}, {})

    assert "http://example.com/j2" in results
    assert results["http://example.com/j2"]["match_score"] > 0
    assert results["http://example.com/j2"]["should_apply"] is True

def test_ranking_agent_gemini_integration():
    agent = RankingAgent(llm_client=MockLLM())
    jobs = [
        {"job_url": "u1", "title": "Dev1", "company": "C1"},
        {"job_url": "u2", "title": "Dev2", "company": "C2"}
    ]
    match_results = {
        "u1": {"match_score": 95, "should_apply": True, "confidence": 0.9},
        "u2": {"match_score": 70, "should_apply": False, "confidence": 0.7}
    }
    ranked = agent.rank_jobs(jobs, match_results)
    assert ranked[0]["job_url"] == "u1"
    assert ranked[0]["priority"] == "High"

def test_career_strategy_agent_gemini_integration():
    agent = CareerStrategyAgent(llm_client=MockLLM())
    job = {"id": 1001, "title": "Senior AI Architect", "company": "AI Inc", "match_score": 90, "description": "Python, Gemini"}
    decision = agent.evaluate_strategy(job, "Python AI Resume Context")

    assert decision["recommendation"] == "Apply Immediately"
    assert "reasoning" in decision

def test_resume_agent_gemini_integration():
    agent = ResumeAgent(llm_client=MockLLM())
    job = {"title": "Python Specialist", "company": "Innovations", "description": "Python, FastAPI"}
    resume_md = agent.tailor_resume("# John Doe\nDeveloper", job)

    assert "# John Doe" in resume_md
    assert "Python Specialist" in resume_md

def test_cover_letter_agent_gemini_integration():
    agent = CoverLetterAgent(llm_client=MockLLM())
    job = {"title": "Backend Lead", "company": "Future Systems", "description": "FastAPI"}
    cover_letter = agent.generate_cover_letter("Python Developer Resume", job)

    assert "Future Systems" in cover_letter
    assert "Backend Lead" in cover_letter

def test_digest_agent_gemini_integration():
    agent = DigestAgent(llm_client=MockLLM())
    high = [{"title": "Senior LLM Engineer", "company": "Gemini AI"}]
    medium = [{"title": "Backend Dev", "company": "Cloud Inc"}]
    summary = agent.generate_digest_summary(high, medium)

    assert "executive_summary" in summary
    assert "daily_recommendation" in summary

def test_notification_agent_gemini_integration():
    agent = NotificationAgent(llm_client=MockLLM())
    job = {"title": "Staff AI Engineer", "company": "Robotics", "match_score": 96}
    alert_summary = agent.enhance_alert_summary(job)

    assert "Staff AI Engineer" in alert_summary or "High match" in alert_summary

@patch("google.genai.Client")
def test_gemini_client_sha256_caching(mock_genai_class):
    mock_instance = MagicMock()
    mock_response = MagicMock()
    mock_response.text = '{"cached_key": "success"}'
    mock_instance.models.generate_content.return_value = mock_response
    mock_genai_class.return_value = mock_instance

    client = GeminiClient(api_key="AIzaSyCacheTestKey12345", model_name="gemini-2.5-flash")

    # First call - hits API
    res1 = client.generate("System Prompt", "Same User Input")
    # Second call - hits internal SHA-256 cache
    res2 = client.generate("System Prompt", "Same User Input")

    assert res1 == res2
    assert mock_instance.models.generate_content.call_count == 1
