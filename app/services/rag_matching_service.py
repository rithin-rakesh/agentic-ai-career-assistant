import os
from typing import Dict, Any, List, Optional
from app.config import settings
from app.database.repository import JobRepository
from app.resume.resume_loader import ResumeLoader
from app.rag.embedding_service import EmbeddingService
from app.rag.vector_store import VectorStore, get_vector_store
from app.rag.indexing import ResumeIndexingPipeline
from app.rag.retriever import Retriever
from app.ai.llm_client import BaseLLM, get_llm_client
from app.ai.prompts import RAG_JOB_MATCH_SYSTEM_PROMPT, RAG_JOB_MATCH_USER_PROMPT
from app.ai.parser import parse_and_validate_json
from app.ai.job_matching_agent import JobMatchResult
from app.logger import logger

class RAGMatchingService:
    """
    RAG-based suitability matching service.
    Indexes candidate resumes, retrieves semantically matching section chunks for job descriptions,
    queries the LLM Recruiter Agent with matching context, and stores scores + metrics in database.
    """
    def __init__(self, repository: JobRepository, llm_client: Optional[BaseLLM] = None, embedding_service: Optional[EmbeddingService] = None, vector_store: Optional[VectorStore] = None):
        self.repository = repository
        self.llm_client = llm_client or get_llm_client()
        self.embedding_service = embedding_service or EmbeddingService()
        self.vector_store = vector_store or get_vector_store()
        
        # In-memory pipeline triggers
        self.indexing_pipeline = ResumeIndexingPipeline(
            embedding_service=self.embedding_service, 
            vector_store=self.vector_store
        )
        self.retriever = Retriever(
            embedding_service=self.embedding_service, 
            vector_store=self.vector_store
        )
        self.resume_path = settings.RESUME_PATH

    def _ensure_default_resume(self) -> None:
        """
        DX (Developer Experience): Automatically creates a sample resume
        if the configured file does not exist, enabling out-of-the-box execution.
        """
        os.makedirs(os.path.dirname(self.resume_path), exist_ok=True)
        if not os.path.exists(self.resume_path):
            logger.info(f"Resume file not found. Creating default template at '{self.resume_path}'")
            default_content = """# John Doe
## Junior ML Engineer & Python Developer

### Skills
- Python, SQL, Bash
- Flask, FastAPI, SQLAlchemy, PyTorch, Git
- AWS Cloud Practitioner

### Experience
- Junior ML Engineer at AI Innovations Ltd (1.5 years)
  Built pipeline data extraction code in Python using SQLAlchemy and PyTorch. Implemented FastAPI route routers.

### Education
- B.S. in Computer Science, State Technical University (2024)

### Projects
- Job Aggregator Dashboard
  Developed web crawling pipelines and sqlite repository services in Python using SQLAlchemy.
"""
            with open(self.resume_path, "w", encoding="utf-8") as f:
                f.write(default_content)

    def evaluate_pending_jobs(self) -> Dict[str, Any]:
        """
        Main pipeline process:
        1. Indexes candidate resume in Qdrant (checking text hash first).
        2. Queries database for unevaluated listings.
        3. Runs retriever semantic queries per job description.
        4. Invokes Recruiter LLM completions.
        5. Persists matching logs and Qdrant metrics inside SQLite.
        """
        stats = {
            "total_pending": 0,
            "processed": 0,
            "failed": 0,
            "recommended": 0
        }
        
        logger.info("RAG Matching Service pipeline started.")
        
        # 1. Load resume and run dynamic Qdrant indexing
        self._ensure_default_resume()
        try:
            raw_resume = ResumeLoader.load_resume(self.resume_path)
            # Create collection and ingest vectors if resume changed
            self.indexing_pipeline.run(raw_resume)
        except Exception as e:
            logger.error(f"Failed to process and index candidate resume: {e}", exc_info=True)
            raise

        # 2. Get unevaluated jobs
        unevaluated_jobs = self.repository.get_unevaluated_jobs()
        stats["total_pending"] = len(unevaluated_jobs)
        
        if stats["total_pending"] == 0:
            logger.info("No unevaluated jobs found in SQLite database.")
            return stats
            
        logger.info(f"Found {stats['total_pending']} jobs requiring AI evaluation. Initiating matching agent...")

        # 3. Process matching evaluations
        for job in unevaluated_jobs:
            try:
                # Query Qdrant for semantic neighbors
                chunks, max_score, retrieval_time = self.retriever.retrieve_relevant_context(job.description)
                
                # Handle zero retrieved chunks gracefully
                if not chunks:
                    logger.warning(f"RAG search query returned 0 matches for Job ID {job.id}. Building fallback context.")
                    retrieved_context = "No relevant resume sections could be semantically retrieved matching this job description. The candidate has no matching experience or skills listed."
                    retrieved_ids = []
                else:
                    context_parts = []
                    for chunk in chunks:
                        section_name = chunk.get("metadata", {}).get("section", "General")
                        context_parts.append(f"Section: {section_name}\nContent:\n{chunk['content']}")
                    retrieved_context = "\n\n---\n\n".join(context_parts)
                    retrieved_ids = [chunk["chunk_id"] for chunk in chunks]
                    
                # Format prompts using ONLY the retrieved sections
                user_prompt = RAG_JOB_MATCH_USER_PROMPT.format(
                    retrieved_context=retrieved_context,
                    job_title=job.title,
                    job_company=job.company,
                    job_location=job.location,
                    job_source=job.source,
                    job_description=job.description
                )
                
                # Execute LLM completion (OpenAI client or simulated mock client)
                response_text = self.llm_client.generate(
                    system_prompt=RAG_JOB_MATCH_SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    response_format={"type": "json_object"}
                )
                
                # Clean and validate LLM dictionary output against schema rules
                evaluation = parse_and_validate_json(response_text, JobMatchResult).model_dump()
                
                # Inject RAG metrics into data dictionary before DB write
                evaluation["retrieved_chunk_ids"] = retrieved_ids
                evaluation["retrieval_time"] = retrieval_time
                evaluation["embedding_model"] = settings.EMBEDDING_MODEL
                evaluation["retrieval_score"] = max_score
                
                # Persist matching log and vector metrics inside SQLite database
                self.repository.update_job_ai_evaluation(job.id, evaluation)
                stats["processed"] += 1
                
                if evaluation.get("should_apply"):
                    stats["recommended"] += 1
                    
                logger.info(
                    f"RAG evaluation complete for Job ID {job.id} ('{job.title}' at '{job.company}'). "
                    f"Match Score: {evaluation.get('match_score')}, Score Threshold: {max_score:.4f}"
                )
                
            except Exception as e:
                stats["failed"] += 1
                logger.error(f"RAG matching pipeline failed for Job ID {job.id}: {e}", exc_info=True)
                continue
                
        logger.info(f"RAG matching finished. Metrics: {stats}")
        return stats
