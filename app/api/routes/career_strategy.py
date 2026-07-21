import json
from typing import List, Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, Body, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from app.auth.authentication import get_current_user
from app.database.repository import JobRepository
from app.agents.feedback_agent import FeedbackAgent
from app.agents.preference_agent import PreferenceAgent
from app.agents.learning_agent import LearningAgent
from app.logger import logger

router = APIRouter(prefix="/api/career", tags=["Career Strategy & Learning"])

class FeedbackEventRequest(BaseModel):
    event_type: str
    job_url: Optional[str] = None
    application_id: Optional[int] = None
    payload: Optional[dict] = None

@router.post("/feedback", status_code=status.HTTP_201_CREATED)
def post_feedback_event(
    request: FeedbackEventRequest = Body(...),
    repo: JobRepository = Depends(JobRepository),
    username: str = Depends(get_current_user)
):
    """
    Manually logs a user interaction/feedback event.
    Triggers company profiles updates and learning metrics where applicable.
    """
    agent = FeedbackAgent(repository=repo)
    event = agent.log_event(
        event_type=request.event_type,
        job_url=request.job_url,
        application_id=request.application_id,
        payload=request.payload
    )
    if not event:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record feedback event in database."
        )
    return {"status": "success", "message": f"Recorded event: {request.event_type}"}

@router.get("/preferences")
def get_preferences(
    repo: JobRepository = Depends(JobRepository),
    username: str = Depends(get_current_user)
):
    """
    Retrieves all dynamic preferences weights grouped by category.
    """
    agent = PreferenceAgent(repository=repo)
    categories = ["technology", "location", "remote_pref"]
    grouped = {}
    for cat in categories:
        grouped[cat] = agent.get_category_preferences(cat)
    return grouped

@router.get("/strategy/{job_id}")
def get_job_career_strategy(
    job_id: int,
    repo: JobRepository = Depends(JobRepository),
    username: str = Depends(get_current_user)
):
    """
    Fetches the deep career strategy evaluation recommendations for a specific job.
    """
    decision = repo.get_career_decision(job_id)
    if not decision:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Strategic career advice for Job ID {job_id} not found."
        )
    
    # Query recommendation history audit score details if exist
    scores = {}
    with repo.session_provider() as session:
        from app.database.models import RecommendationHistoryModel
        query = select(RecommendationHistoryModel).where(RecommendationHistoryModel.job_id == job_id).order_by(RecommendationHistoryModel.created_at.desc())
        history = session.execute(query).scalars().first()
        if history:
            scores = {
                "llm_match": history.llm_match_score,
                "behavior": history.behavior_score,
                "company_pref": history.company_preference_score,
                "location_pref": history.location_preference_score,
                "technology_pref": history.technology_preference_score,
                "salary_match": history.salary_match_score,
                "growth": history.growth_score,
                "risk": history.risk_score,
                "final_score": history.final_score
            }

    return {
        "id": decision.id,
        "job_id": decision.job_id,
        "recommendation": decision.recommendation,
        "confidence": decision.confidence,
        "priority": decision.priority,
        "estimated_interview_probability": decision.estimated_interview_probability,
        "career_growth": decision.career_growth,
        "salary_competitiveness": decision.salary_competitiveness,
        "learning_effort": decision.learning_effort,
        "resume_changes_required": decision.resume_changes_required,
        "cover_letter_required": decision.cover_letter_required,
        "estimated_application_time": decision.estimated_application_time,
        "reasoning": json.loads(decision.reasoning) if decision.reasoning else [],
        "missing_skills": json.loads(decision.missing_skills) if decision.missing_skills else [],
        "scores": scores
    }

@router.get("/companies")
def get_companies_intelligence(
    repo: JobRepository = Depends(JobRepository),
    username: str = Depends(get_current_user)
):
    """
    Retrieves all company intelligence logs (applied, rejected counts, interview rates).
    """
    profiles = repo.get_company_profiles()
    return [
        {
            "id": p.id,
            "name": p.name,
            "status": p.status,
            "applied_count": p.applied_count,
            "rejected_count": p.rejected_count,
            "interview_count": p.interview_count,
            "offer_count": p.offer_count,
            "success_rate": p.success_rate,
            "last_updated": p.last_updated
        }
        for p in profiles
    ]

@router.get("/learning-analytics")
def get_learning_analytics(
    repo: JobRepository = Depends(JobRepository),
    username: str = Depends(get_current_user)
):
    """
    Fetches the logged self-improvement weekly learning metrics and recommendation accuracies.
    """
    metrics = repo.get_learning_metrics()
    return [
        {
            "id": m.id,
            "metric_date": m.metric_date,
            "accepted_recommendations": m.accepted_recommendations,
            "ignored_recommendations": m.ignored_recommendations,
            "interview_conversion_rate": m.interview_conversion_rate,
            "offer_conversion_rate": m.offer_conversion_rate
        }
        for m in metrics
    ]

@router.post("/trigger-learning")
def trigger_feedback_learning(
    repo: JobRepository = Depends(JobRepository),
    username: str = Depends(get_current_user)
):
    """
    Forces the LearningAgent to run preference weight update analysis manually.
    """
    agent = LearningAgent(repository=repo)
    result = agent.learn_from_feedback()
    return {"status": "success", "result": result}
