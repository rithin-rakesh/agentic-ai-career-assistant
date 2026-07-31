import os
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager

from app.database.models import Base
from app.database.repository import JobRepository
from app.schemas.job import JobCreate
from app.resume.chunk_generator import ResumeChunkGenerator
from app.rag.embedding_service import EmbeddingService
from app.rag.vector_store import VectorStore
from app.rag.indexing import ResumeIndexingPipeline
from app.rag.retriever import Retriever
from app.services.rag_matching_service import RAGMatchingService
from app.ai.llm_client import BaseLLM

# Mock LLM Client
class MockLLM(BaseLLM):
    def __init__(self, response_text: str):
        self.response_text = response_text
        self.calls = []

    def generate(self, system_prompt: str, user_prompt: str, response_format = None) -> str:
        self.calls.append((system_prompt, user_prompt))
        return self.response_text

@pytest.fixture
def test_db_session():
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

def test_resume_chunk_generator():
    """
    Checks that the ResumeChunkGenerator correctly splits raw markdown by headers.
    """
    raw_md = """# Candidate Profile
## Technical Skills
- Python, PyTorch, SQL

## Work Experience
- Software Developer at Corp A (1 year)
"""
    chunks = ResumeChunkGenerator.generate_chunks(raw_md)
    
    # Expected chunks: Summary (intro), Technical Skills, Work Experience
    assert len(chunks) == 3
    assert chunks[0].section == "Candidate Profile"
    assert chunks[1].section == "Technical Skills"
    assert "Python, PyTorch, SQL" in chunks[1].content
    assert chunks[2].section == "Work Experience"

def test_embedding_service_cache_and_keyword_bias():
    """
    Verifies that the EmbeddingService generates correct dimension vectors (384),
    caches repeated queries, and applies keyword shifts to model semantic similarity.
    """
    service = EmbeddingService(mock_mode=True)
    
    # 1. Test dimension and cache
    v1 = service.get_embedding("Python Developer")
    assert len(v1) == 384
    
    # Cache hit check
    v1_cached = service.get_embedding("Python Developer")
    assert v1 == v1_cached
    
    # 2. Test keyword semantic alignment (cosine similarity check)
    # Jobs matching 'Python' should have higher similarity than mismatched jobs
    doc_resume_section = "Technical Skills: Experienced in Python programming, SQL databases, and PyTorch frameworks."
    query_python = "Looking for a Python Developer who knows PyTorch."
    query_unrelated = "Hiring a Ruby on Rails designer."
    
    emb_doc = service.get_embedding(doc_resume_section)
    emb_py = service.get_embedding(query_python)
    emb_unrelated = service.get_embedding(query_unrelated)
    
    # Compute dot products (since they are normalized unit vectors, dot product = cosine similarity)
    sim_py = sum(x * y for x, y in zip(emb_doc, emb_py))
    sim_unrelated = sum(x * y for x, y in zip(emb_doc, emb_unrelated))
    
    # The dot product of Python query should be significantly higher due to keyword shift weight
    assert sim_py > sim_unrelated
    assert sim_py > 0.4

def test_vector_store_operations(monkeypatch):
    """
    Verifies that the VectorStore creates collection points, inserts vector payloads,
    searches correctly with score thresholds, and drops collections.
    Uses in-memory volatile settings for fast testing.
    """
    monkeypatch.setattr("app.config.settings.VECTOR_DB_URL", ":memory:")
    store = VectorStore(collection_name="test_collection")
    
    # 1. Setup Collection schema
    store.create_collection()
    
    # 2. Ingest points
    vector1 = [0.1] * 384
    vector2 = [0.8] * 384
    # Normalize vectors manually for mock check
    mag1 = sum(x*x for x in vector1)**0.5
    vector1 = [x/mag1 for x in vector1]
    mag2 = sum(x*x for x in vector2)**0.5
    vector2 = [x/mag2 for x in vector2]
    
    store.insert_chunk(
        chunk_id="chunk-1",
        embedding=vector1,
        metadata={"section": "Summary"},
        content="This is section content 1."
    )
    store.insert_chunk(
        chunk_id="chunk-2",
        embedding=vector2,
        metadata={"section": "Skills"},
        content="This is section content 2."
    )
    
    # 3. Query search (query vector matches vector2 exactly)
    results = store.search(query_embedding=vector2, top_k=2, threshold=0.1)
    
    assert len(results) >= 1
    assert results[0]["chunk_id"] == "chunk-2"
    assert results[0]["content"] == "This is section content 2."
    assert results[0]["score"] > 0.9
    
    # Cleanup
    store.delete_collection()

def test_retriever_query_mapping():
    """
    Checks that Retriever embeds queries and retrieves section contexts from VectorStore.
    """
    embedding_service = MagicMock(spec=EmbeddingService)
    vector_store = MagicMock(spec=VectorStore)
    
    embedding_service.get_embedding.return_value = [0.1] * 384
    vector_store.search.return_value = [
        {"chunk_id": "chunk-9", "content": "Match context", "metadata": {"section": "Skills"}, "score": 0.85}
    ]
    
    retriever = Retriever(embedding_service=embedding_service, vector_store=vector_store)
    chunks, max_score, latency = retriever.retrieve_relevant_context("Search description details.")
    
    embedding_service.get_embedding.assert_called_once()
    vector_store.search.assert_called_once()
    assert len(chunks) == 1
    assert chunks[0]["chunk_id"] == "chunk-9"
    assert max_score == 0.85

def test_rag_matching_service_integration(test_db_session, monkeypatch):
    """
    Verifies the integration workflow of RAGMatchingService:
    - Automatically builds/indexes resume chunks in Qdrant (in-memory)
    - Fetches unevaluated database jobs
    - Runs semantic retriever context filtering
    - Submits prompts to LLM and saves RAG scoring metrics inside SQLite.
    """
    repo = JobRepository(session_provider=test_db_session)
    repo.create_database()
    
    # 1. Insert an unevaluated job description
    repo.insert_job(
        JobCreate(
            title="Python Developer", company="Corp X", location="Remote",
            job_url="https://example.com/rag-job", description="Required Python skills.",
            source="Indeed", date_posted=datetime.now(timezone.utc)
        )
    )
    
    # 2. Setup Mock components
    mock_llm_json = """
    {
      "match_score": 88,
      "should_apply": true,
      "priority": "High",
      "summary": "Retrieved context matches perfectly.",
      "strengths": ["Python"],
      "missing_skills": [],
      "learning_effort": "Low",
      "confidence": 0.95
    }
    """
    llm = MockLLM(mock_llm_json)
    
    # Force vector store and embedding service to run in memory
    monkeypatch.setattr("app.config.settings.VECTOR_DB_URL", ":memory:")
    monkeypatch.setattr("app.config.settings.COLLECTION_NAME", "test_rag_collection")
    
    embedding_service = EmbeddingService(mock_mode=True)
    vector_store = VectorStore()
    
    service = RAGMatchingService(
        repository=repo, 
        llm_client=llm,
        embedding_service=embedding_service,
        vector_store=vector_store
    )
    
    service.resume_path = "dummy_resume_path.md"
    service._ensure_default_resume = MagicMock()
    
    from app.resume.resume_loader import ResumeLoader
    monkeypatch.setattr(ResumeLoader, "load_resume", MagicMock(return_value="## Technical Skills\n- Python, Git, SQL"))
    
    # 3. Execute matching sync
    stats = service.evaluate_pending_jobs()
    
    assert stats["total_pending"] == 1
    assert stats["processed"] == 1
    assert stats["recommended"] == 1
    
    # 4. Check SQLite record details
    jobs = repo.get_all_jobs()
    assert len(jobs) == 1
    assert jobs[0].match_score == 88
    assert jobs[0].should_apply is True
    assert jobs[0].priority == "High"
    assert jobs[0].summary == "Retrieved context matches perfectly."
    
    # RAG specific columns assert checks
    assert len(jobs[0].retrieved_chunk_ids) == 1
    assert "chunk-1-technical-skills" in jobs[0].retrieved_chunk_ids[0]
    assert jobs[0].retrieval_score > 0.4
    assert jobs[0].retrieval_time is not None
    assert jobs[0].embedding_model == "all-MiniLM-L6-v2"
