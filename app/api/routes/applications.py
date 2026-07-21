import os
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Body, status
from pydantic import BaseModel
from sqlalchemy import select
from app.auth.authentication import get_current_user
from app.database.repository import JobRepository
from app.schemas.job import Application
from app.logger import logger

router = APIRouter(prefix="/api/applications", tags=["Applications"])

class ApprovalRequest(BaseModel):
    status: str # Approved, Rejected, Ignored, Regenerate

@router.get("", response_model=List[Application])
def get_applications(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by application status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    repo: JobRepository = Depends(JobRepository),
    username: str = Depends(get_current_user)
):
    """
    Retrieves all job application tracking logs from the SQLite database.
    """
    # Sanitize parameters if function is invoked directly as a Python helper
    clean_status = status_filter if isinstance(status_filter, str) else None
    clean_limit = limit if isinstance(limit, int) else 50
    clean_offset = offset if isinstance(offset, int) else 0

    try:
        with repo.session_provider() as session:
            from app.database.models import ApplicationModel
            query = select(ApplicationModel).order_by(ApplicationModel.created_at.desc())
            if clean_status and clean_status.strip():
                query = query.where(ApplicationModel.status == clean_status.strip())
            
            db_apps = session.execute(query).scalars().all()
            
            # Paginate
            paginated = db_apps[clean_offset:clean_offset + clean_limit]
            return [Application.model_validate(app) for app in paginated]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query applications database: {e}"
        )

@router.patch("/{app_id}", response_model=Application)
def update_application_status(
    app_id: int,
    payload: ApprovalRequest = Body(...),
    repo: JobRepository = Depends(JobRepository),
    username: str = Depends(get_current_user)
):
    """
    Updates the human approval status of a job application.
    If 'Approved' or 'Regenerate' is submitted, triggers document customization and compilation.
    """
    target_status = payload.status.strip()
    valid_statuses = ["Approved", "Rejected", "Ignored", "Regenerate", "Applied", "Interview"]
    if target_status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status choice. Must be one of: {valid_statuses}"
        )

    try:
        # 1. Fetch application record
        with repo.session_provider() as session:
            from app.database.models import ApplicationModel
            db_app = session.get(ApplicationModel, app_id)
            if not db_app:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Application ID {app_id} not found."
                )
            
            # Retrieve associated job record
            db_job = db_app.job
            if not db_job:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Associated job for Application ID {app_id} is missing."
                )
            
            job_dict = {
                "job_url": db_job.job_url,
                "title": db_job.title,
                "company": db_job.company,
                "location": db_job.location,
                "description": db_job.description,
                "match_score": db_job.match_score,
                "priority": db_job.priority
            }
            job_url = db_job.job_url
            company = db_job.company
            title = db_job.title
            job_id = db_job.id
            
        # 2. Process actions
        if target_status in ["Approved", "Regenerate"]:
            logger.info(f"API: Human triggered compilation of package '{title}' at '{company}'...")
            
            # Retrieve RAG semantic context
            from app.rag.retriever import Retriever
            from app.rag.embedding_service import EmbeddingService
            from app.rag.vector_store import VectorStore
            from app.agents.retrieval_agent import RetrievalAgent
            
            retriever = Retriever(embedding_service=EmbeddingService(), vector_store=VectorStore())
            retrieval_agent = RetrievalAgent(retriever=retriever)
            contexts, _ = retrieval_agent.retrieve([job_dict])
            context = contexts.get(job_url, "Skills: Python, FastAPI")
            
            # Trigger document generator
            from app.agents.application_agent import ApplicationAgent
            from app.ai.llm_client import OpenAIClient
            from app.agents.resume_agent import ResumeAgent
            from app.agents.cover_letter_agent import CoverLetterAgent
            from app.agents.skills_agent import SkillsAgent
            from app.memory.application_memory import ApplicationMemoryManager
            
            llm_client = OpenAIClient()
            res_agent = ResumeAgent(llm_client=llm_client)
            cov_agent = CoverLetterAgent(llm_client=llm_client)
            skl_agent = SkillsAgent(llm_client=llm_client)
            
            # Clear memory generated caches to allow regenerating packages
            memory_manager = ApplicationMemoryManager()
            if target_status == "Regenerate" and job_url in memory_manager.memory.get("previously_generated_resumes", {}):
                del memory_manager.memory["previously_generated_resumes"][job_url]
                memory_manager.save_memory()

            app_agent = ApplicationAgent(
                resume_agent=res_agent,
                cl_agent=cov_agent,
                skills_agent=skl_agent,
                memory_manager=memory_manager
            )
            
            # Compile tailored packages
            packages = app_agent.prepare_applications([job_dict], {job_url: context})
            if packages:
                pkg = packages[0]
                # Update SQLite database columns
                with repo.session_provider() as session:
                    active_app = session.get(ApplicationModel, app_id)
                    active_app.status = "Draft"
                    active_app.resume_path = pkg["resume_path"]
                    active_app.cover_letter_path = pkg["cover_letter_path"]
            else:
                # If generation skipped or failed, fallback to manual database status write
                repo.update_application_status(app_id, "Draft")
        else:
            # For Rejected, Ignored, Applied, Interview, directly write status
            repo.update_application_status(app_id, target_status)
            
            # If rejected or ignored, update the memory manager cache status
            from app.memory.application_memory import ApplicationMemoryManager
            memory_manager = ApplicationMemoryManager()
            memory_manager.update_status(job_url, target_status)

        # 3. Re-fetch and validate updated record
        updated_app = repo.get_application_by_job_id(job_id)
        return updated_app
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update application status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database update transaction failed: {e}"
        )
