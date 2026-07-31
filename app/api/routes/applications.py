import os
import json
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Body, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from app.auth.authentication import get_current_user
from app.database.repository import JobRepository
from app.schemas.job import Application
from app.logger import logger

router = APIRouter(prefix="/api/applications", tags=["Applications"])

class ApprovalRequest(BaseModel):
    status: str # Approved, Rejected, Ignored, Regenerate, Applied, Interview, Offer, Accepted

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
            paginated = db_apps[clean_offset:clean_offset + clean_limit]
            return [Application.model_validate(app) for app in paginated]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query applications database: {e}"
        )

@router.get("/{app_id}")
def get_application_detail(
    app_id: int,
    repo: JobRepository = Depends(JobRepository),
    username: str = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Retrieves comprehensive Application Package Summary details, joining Application, Job, and Career Decision data.
    """
    try:
        with repo.session_provider() as session:
            from app.database.models import ApplicationModel, JobModel, CareerDecisionModel
            db_app = session.get(ApplicationModel, app_id)
            if not db_app:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Application ID {app_id} not found."
                )
            
            db_job = db_app.job
            if not db_job:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Associated job for Application ID {app_id} is missing."
                )

            # Retrieve career decision metadata if present
            cd_query = select(CareerDecisionModel).where(CareerDecisionModel.job_id == db_job.id)
            db_cd = session.execute(cd_query).scalars().first()

            strengths = json.loads(db_job.strengths) if db_job.strengths else []
            missing_skills = json.loads(db_job.missing_skills) if db_job.missing_skills else []
            
            return {
                "id": db_app.id,
                "job_id": db_job.id,
                "company": db_app.company,
                "position": db_app.position,
                "status": db_app.status,
                "resume_path": db_app.resume_path,
                "cover_letter_path": db_app.cover_letter_path,
                "created_at": db_app.created_at.isoformat() if db_app.created_at else None,
                "applied_at": db_app.applied_at.isoformat() if db_app.applied_at else None,
                "last_updated": db_app.last_updated.isoformat() if db_app.last_updated else None,
                
                # Job details
                "location": db_job.location,
                "job_url": db_job.job_url,
                "apply_url": db_job.apply_url or db_job.job_url,
                "source": db_job.source,
                "employment_type": db_job.employment_type or "Full-time",
                "salary_range": db_job.salary_range or "Not specified",
                "match_score": db_job.match_score or 0,
                "priority": db_job.priority or "Medium",
                "strengths": strengths,
                "missing_skills": missing_skills,
                "summary": db_job.summary,
                
                # Decision details
                "recommendation": db_cd.recommendation if db_cd else ("Apply" if (db_job.match_score or 0) >= 70 else "Review"),
                "estimated_interview_probability": db_cd.estimated_interview_probability if db_cd else f"{min(95, max(40, db_job.match_score or 50))}%",
                "career_growth": db_cd.career_growth if db_cd else "High",
                "salary_competitiveness": db_cd.salary_competitiveness if db_cd else "Competitive",
                "learning_effort": db_job.learning_effort or "Medium"
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch application detail for ID {app_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve application package details: {e}"
        )

def _serve_application_file(app_id: int, doc_type: str, requested_format: str, repo: JobRepository):
    """
    Secure file download helper with error handling and fallback on-the-fly compilation.
    """
    with repo.session_provider() as session:
        from app.database.models import ApplicationModel
        db_app = session.get(ApplicationModel, app_id)
        if not db_app:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Application ID {app_id} not found."
            )
        
        file_path = db_app.resume_path if doc_type == "resume" else db_app.cover_letter_path
        company_clean = "".join(c for c in db_app.company if c.isalnum() or c in (" ", "_", "-")).strip()
        pos_clean = "".join(c for c in db_app.position if c.isalnum() or c in (" ", "_", "-")).strip()

    if not file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No {doc_type.replace('_', ' ')} file path recorded for application ID {app_id}."
        )

    base_path = os.path.splitext(file_path)[0]
    target_path = f"{base_path}.{requested_format}"

    # 1. If target format file exists, serve immediately
    if os.path.exists(target_path):
        media_type = "application/pdf" if requested_format == "pdf" else "text/markdown"
        filename = f"{company_clean}_{pos_clean}_{doc_type.replace('_', ' ').title()}.{requested_format}"
        return FileResponse(path=target_path, media_type=media_type, filename=filename)

    # 2. If requested PDF but only MD exists, compile PDF on-the-fly
    md_path = f"{base_path}.md"
    if requested_format == "pdf" and os.path.exists(md_path):
        try:
            from app.resume.resume_generator import ResumeDocumentGenerator
            with open(md_path, "r", encoding="utf-8", errors="replace") as f:
                md_text = f.read()
            generator = ResumeDocumentGenerator()
            generator._compile_pdf(md_text, target_path)
            if os.path.exists(target_path):
                filename = f"{company_clean}_{pos_clean}_{doc_type.replace('_', ' ').title()}.pdf"
                return FileResponse(path=target_path, media_type="application/pdf", filename=filename)
        except Exception as e:
            logger.warning(f"On-the-fly PDF compilation failed: {e}")

    # 3. Clean 404 response if file missing
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{doc_type.replace('_', ' ').title()} file ({requested_format.upper()}) for application ID {app_id} not found on server."
    )

@router.get("/{app_id}/download/resume/pdf")
def download_resume_pdf(
    app_id: int,
    repo: JobRepository = Depends(JobRepository),
    username: str = Depends(get_current_user)
):
    """
    Secure download endpoint for Tailored Resume PDF document.
    """
    return _serve_application_file(app_id, "resume", "pdf", repo)

@router.get("/{app_id}/download/resume/md")
def download_resume_md(
    app_id: int,
    repo: JobRepository = Depends(JobRepository),
    username: str = Depends(get_current_user)
):
    """
    Secure download endpoint for Tailored Resume Markdown document.
    """
    return _serve_application_file(app_id, "resume", "md", repo)

@router.get("/{app_id}/download/cover-letter/pdf")
def download_cover_letter_pdf(
    app_id: int,
    repo: JobRepository = Depends(JobRepository),
    username: str = Depends(get_current_user)
):
    """
    Secure download endpoint for Tailored Cover Letter PDF document.
    """
    return _serve_application_file(app_id, "cover_letter", "pdf", repo)

@router.get("/{app_id}/download/cover-letter/md")
def download_cover_letter_md(
    app_id: int,
    repo: JobRepository = Depends(JobRepository),
    username: str = Depends(get_current_user)
):
    """
    Secure download endpoint for Tailored Cover Letter Markdown document.
    """
    return _serve_application_file(app_id, "cover_letter", "md", repo)

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
    valid_statuses = ["Approved", "Rejected", "Ignored", "Regenerate", "Applied", "Interview", "Offer", "Accepted"]
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
            
            from app.rag.retriever import Retriever
            from app.rag.embedding_service import EmbeddingService
            from app.rag.vector_store import VectorStore
            from app.agents.retrieval_agent import RetrievalAgent
            
            retriever = Retriever(embedding_service=EmbeddingService(), vector_store=VectorStore())
            retrieval_agent = RetrievalAgent(retriever=retriever)
            contexts, _ = retrieval_agent.retrieve([job_dict])
            context = contexts.get(job_url, "Skills: Python, FastAPI")
            
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
            
            packages = app_agent.prepare_applications([job_dict], {job_url: context})
            if packages:
                pkg = packages[0]
                with repo.session_provider() as session:
                    active_app = session.get(ApplicationModel, app_id)
                    active_app.status = "Draft"
                    active_app.resume_path = pkg["resume_path"]
                    active_app.cover_letter_path = pkg["cover_letter_path"]
            else:
                repo.update_application_status(app_id, "Draft")
        else:
            repo.update_application_status(app_id, target_status)
            
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
