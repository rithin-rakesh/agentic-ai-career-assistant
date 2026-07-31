from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from app.config import settings
from app.ai.llm_client import BaseLLM, MockLLM, get_llm_client
from app.notifications.email_service import EmailService
from app.notifications.template_engine import TemplateEngine
from app.notifications.notification_repository import NotificationRepository
from app.logger import logger

class NotificationAgent:
    """
    Evaluates newly ranked jobs to determine immediate delivery alerts or digest queuing.
    Enhances instant alert titles and summaries using Gemini without altering routing logic.
    Filters out duplicate listings by querying historical sqlite logs via NotificationRepository.
    Rules:
      - High Priority: Triggers responsive HTML email instantly.
      - Medium Priority: Logged as 'queued' for standard Daily Digest compilation.
      - Low Priority: Logged as 'skipped' to conserve notification bandwidth.
    """
    def __init__(
        self,
        email_service: EmailService = None,
        template_engine: TemplateEngine = None,
        repository: NotificationRepository = None,
        llm_client: Optional[BaseLLM] = None
    ):
        self.email_service = email_service or EmailService()
        self.template_engine = template_engine or TemplateEngine()
        self.repository = repository or NotificationRepository()
        self.llm_client = llm_client or get_llm_client()

    def enhance_alert_summary(self, job_dict: Dict[str, Any]) -> str:
        """
        Uses Gemini to generate an engaging single-sentence alert summary for high priority emails.
        """
        if isinstance(self.llm_client, MockLLM) or getattr(self.llm_client, "mock_fallback", None) is not None:
            return job_dict.get("summary") or f"High match ({job_dict.get('match_score', 0)}%) for {job_dict.get('title')} at {job_dict.get('company')}."

        system_prompt = "You are a professional career alert writer. Write a concise, 1-sentence highlight for an urgent job match."
        user_prompt = f"Title: {job_dict.get('title')}\nCompany: {job_dict.get('company')}\nMatch Score: {job_dict.get('match_score')}"

        try:
            return self.llm_client.generate(system_prompt, user_prompt)
        except Exception:
            return job_dict.get("summary") or f"High match ({job_dict.get('match_score', 0)}%) for {job_dict.get('title')} at {job_dict.get('company')}."

    def evaluate_and_notify(self, ranked_jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Processes AI-ranked job lists, executing routing actions.
        Returns: List of notification metadata dictionaries for persistence execution.
        """
        logger.info(f"NotificationAgent: Evaluating alerts routing for {len(ranked_jobs)} ranked jobs.")
        records = []

        for job_dict in ranked_jobs:
            job_url = job_dict.get("job_url", "")
            title = job_dict.get("title", "Unknown Title")
            company = job_dict.get("company", "Unknown Company")
            priority = job_dict.get("priority", "Low")
            score = job_dict.get("match_score", 0)

            # 1. Prevent duplicate notifications for the same job URL
            if self.repository.has_been_notified(job_url):
                logger.info(f"NotificationAgent: Duplicate alert check hit. Skipping '{title}' at '{company}'.")
                records.append({
                    "job_url": job_url,
                    "channel": "email",
                    "status": "skipped",
                    "sent_at": None,
                    "retry_count": 0,
                    "error_message": "Duplicate prevention filter triggered"
                })
                continue

            # 2. Check routing priority rules
            is_high_priority = (priority == "High") or (score >= settings.INSTANT_THRESHOLD)
            
            if is_high_priority:
                # Deliver Instant HTML alert
                logger.info(f"NotificationAgent: Routing instant alert for High Priority job '{title}' at '{company}' (Score: {score}%)")
                
                try:
                    # Enrich alert with Gemini summary
                    enhanced_job = dict(job_dict)
                    enhanced_job["ai_summary"] = self.enhance_alert_summary(job_dict)

                    subject = f"Instant Job Alert: {title} at {company} ({score}% Match)"
                    html_content = self.template_engine.render("instant_alert.html", {"job": enhanced_job})
                    
                    # Dispatch via EmailService
                    success, attempts, error_msg = self.email_service.send_html_email(subject, html_content)
                    
                    records.append({
                        "job_url": job_url,
                        "channel": "email",
                        "status": "sent" if success else "failed",
                        "sent_at": datetime.now(timezone.utc) if success else None,
                        "retry_count": attempts,
                        "error_message": error_msg
                    })
                except Exception as e:
                    err_msg = f"Failed to assemble instant alert email: {e}"
                    logger.error(err_msg, exc_info=True)
                    records.append({
                        "job_url": job_url,
                        "channel": "email",
                        "status": "failed",
                        "sent_at": None,
                        "retry_count": 1,
                        "error_message": err_msg
                    })

            elif priority == "Medium":
                # Queue for daily digest
                logger.info(f"NotificationAgent: Queuing '{title}' at '{company}' (Score: {score}%) for daily digest.")
                records.append({
                    "job_url": job_url,
                    "channel": "email",
                    "status": "queued",
                    "sent_at": None,
                    "retry_count": 0,
                    "error_message": "Queued for Daily Digest"
                })

            else:
                # Skip Low Priority
                logger.info(f"NotificationAgent: Skipping alert for Low Priority job '{title}' at '{company}' (Score: {score}%)")
                records.append({
                    "job_url": job_url,
                    "channel": "email",
                    "status": "skipped",
                    "sent_at": None,
                    "retry_count": 0,
                    "error_message": "Skipped due to Low priority score"
                })

        return records
