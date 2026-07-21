import os
from typing import Dict, Any, List, Optional
from app.config import settings
from app.database.repository import JobRepository
from app.resume.resume_loader import ResumeLoader
from app.resume.resume_parser import ResumeParser, Resume
from app.ai.llm_client import BaseLLM, OpenAIClient
from app.ai.job_matching_agent import JobMatchingAgent
from app.logger import logger

class AIMatchingService:
    """
    Orchestration service that loads/parses candidate resumes,
    finds unevaluated jobs, and invokes the AI Job Matching Agent to assess suitability.
    """
    def __init__(self, repository: JobRepository, llm_client: Optional[BaseLLM] = None):
        self.repository = repository
        self.llm_client = llm_client or OpenAIClient()
        self.resume_parser = ResumeParser(llm_client=self.llm_client)
        self.matching_agent = JobMatchingAgent(llm_client=self.llm_client)
        self.resume_path = settings.RESUME_PATH

    def _ensure_default_resume(self) -> None:
        """
        DX (Developer Experience): Automatically creates a sample resume
        if the configured file does not exist, enabling out-of-the-box execution.
        """
        # Ensure data folder exists
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
        Loads candidate resume, fetches all jobs missing AI match data,
        runs evaluation, and updates SQLite.
        """
        stats = {
            "total_pending": 0,
            "processed": 0,
            "failed": 0,
            "recommended": 0
        }
        
        logger.info("AI Matching Service started.")
        
        # 1. Ensure resume exists and load it
        self._ensure_default_resume()
        try:
            raw_resume = ResumeLoader.load_resume(self.resume_path)
            # Parse once, cache structured Resume model in memory
            resume = self.resume_parser.parse_resume_text(raw_resume)
        except Exception as e:
            logger.error(f"Failed to load or parse resume: {e}", exc_info=True)
            raise

        # 2. Query repository for all unevaluated jobs
        unevaluated_jobs = self.repository.get_unevaluated_jobs()
        stats["total_pending"] = len(unevaluated_jobs)
        
        if stats["total_pending"] == 0:
            logger.info("No unevaluated jobs found in the database. AI matching sync completed.")
            return stats
            
        logger.info(f"Found {stats['total_pending']} jobs requiring AI evaluation. Initiating matching agent...")

        # 3. Evaluate each job
        for job in unevaluated_jobs:
            try:
                # Execute semantic evaluation
                evaluation = self.matching_agent.evaluate_job(
                    resume=resume,
                    job_title=job.title,
                    job_company=job.company,
                    job_location=job.location,
                    job_source=job.source,
                    job_description=job.description
                )
                
                # Persist evaluation back to database
                self.repository.update_job_ai_evaluation(job.id, evaluation)
                stats["processed"] += 1
                
                if evaluation.get("should_apply"):
                    stats["recommended"] += 1
                    
                logger.info(
                    f"Job ID {job.id} ('{job.title}' at '{job.company}') evaluated successfully. "
                    f"Match Score: {evaluation.get('match_score')}, Recommendation: {evaluation.get('should_apply')}"
                )
                
            except Exception as e:
                stats["failed"] += 1
                logger.error(f"AI matching pipeline failed for Job ID {job.id}: {e}", exc_info=True)
                continue
                
        logger.info(f"AI matching finished. Metrics: {stats}")
        return stats
