from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.auth.authentication import get_current_user
from app.database.repository import JobRepository
from app.schemas.job import Job

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])

@router.get("", response_model=List[Job])
def get_jobs(
    min_score: Optional[int] = Query(None, description="Minimum match score"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    repo: JobRepository = Depends(JobRepository),
    username: str = Depends(get_current_user)
):
    """
    Retrieves job listings stored in SQLite database.
    Supports filtering by minimum match score and pagination.
    """
    try:
        # Fetch jobs
        all_jobs = repo.get_all_jobs()
        
        # Apply score filter
        if min_score is not None:
            all_jobs = [j for j in all_jobs if j.match_score is not None and j.match_score >= min_score]
            
        # Paginate
        paginated_jobs = all_jobs[offset:offset + limit]
        return paginated_jobs
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve jobs from database: {e}"
        )

@router.get("/{job_id}", response_model=Job)
def get_job_by_id(
    job_id: int,
    repo: JobRepository = Depends(JobRepository),
    username: str = Depends(get_current_user)
):
    """
    Fetches job details by its auto-increment ID.
    """
    try:
        with repo.session_provider() as session:
            from app.database.models import JobModel
            db_job = session.get(JobModel, job_id)
            if not db_job:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Job ID {job_id} not found."
                )
            return Job.model_validate(db_job)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch job record: {e}"
        )
