from typing import Optional, Any
from app.database.repository import JobRepository
from app.logger import logger

class FeedbackAgent:
    """
    FeedbackAgent is responsible for tracking candidate interactions.
    Records events (Viewed, Ignored, Bookmarked, Applied, etc.) to feedback_events table.
    """
    def __init__(self, repository: Optional[JobRepository] = None):
        self.repository = repository or JobRepository()

    def log_event(self, event_type: str, job_url: Optional[str] = None, application_id: Optional[int] = None, payload: Optional[dict] = None) -> Any:
        """
        Logs feedback event to the database.
        """
        logger.info(f"FeedbackAgent: Recording event '{event_type}' for URL='{job_url}', AppID={application_id}")
        
        # Log to SQLite
        event = self.repository.log_feedback_event(
            event_type=event_type,
            job_url=job_url,
            application_id=application_id,
            payload=payload
        )
        
        # Log learning metrics updates where appropriate
        if event:
            accepted_delta = 1 if event_type in ["Applied", "Bookmarked"] else 0
            ignored_delta = 1 if event_type == "Ignored Job" else 0
            
            # Check for conversion rates changes
            interview_conv = None
            offer_conv = None
            
            if event_type == "Interview Scheduled" or event_type == "Offer Received":
                # Compute conversion rates
                with self.repository.session_provider() as session:
                    from app.database.models import ApplicationModel
                    from sqlalchemy import func, select
                    
                    # Compute funnel conversions
                    total_apps_query = select(func.count(ApplicationModel.id))
                    total_apps = session.execute(total_apps_query).scalar() or 0
                    
                    interviews_query = select(func.count(ApplicationModel.id)).where(ApplicationModel.status == "Interview")
                    interviews = session.execute(interviews_query).scalar() or 0
                    
                    offers_query = select(func.count(ApplicationModel.id)).where(ApplicationModel.status.in_(["Offer", "Accepted"]))
                    offers = session.execute(offers_query).scalar() or 0
                    
                    if total_apps > 0:
                        interview_conv = round((interviews / total_apps) * 100, 2)
                        offer_conv = round((offers / total_apps) * 100, 2)
            
            self.repository.update_learning_metrics(
                accepted_delta=accepted_delta,
                ignored_delta=ignored_delta,
                interview_conv=interview_conv,
                offer_conv=offer_conv
            )
            
            # If applied, rejected, or interview, update company profile stats
            if event_type in ["Applied", "Rejected", "Interview Scheduled", "Offer Received"]:
                # Fetch company details from job
                db_job = None
                if job_url:
                    db_job = self.repository.get_job_by_url(job_url)
                
                if db_job:
                    company_name = db_job.company
                    applied_inc = 1 if event_type == "Applied" else 0
                    rejected_inc = 1 if event_type == "Rejected" else 0
                    interview_inc = 1 if event_type == "Interview Scheduled" else 0
                    offer_inc = 1 if event_type == "Offer Received" else 0
                    
                    self.repository.update_company_profile(
                        name=company_name,
                        applied_inc=applied_inc,
                        rejected_inc=rejected_inc,
                        interview_inc=interview_inc,
                        offer_inc=offer_inc
                    )
            
        return event
