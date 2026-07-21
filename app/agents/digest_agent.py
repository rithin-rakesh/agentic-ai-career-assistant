from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple, Optional
from app.notifications.email_service import EmailService
from app.notifications.template_engine import TemplateEngine
from app.logger import logger

class DigestAgent:
    """
    DigestAgent processes collected job listings, groups them by priority,
    renders a responsive daily digest HTML template, and transmits it via EmailService.
    """
    def __init__(self, email_service: EmailService = None, template_engine: TemplateEngine = None):
        self.email_service = email_service or EmailService()
        self.template_engine = template_engine or TemplateEngine()

    def send_daily_digest(self, high_jobs: List[Dict[str, Any]], medium_jobs: List[Dict[str, Any]]) -> Tuple[bool, int, Optional[str]]:
        """
        Gathers ranked jobs, renders daily_digest.html, and transmits the email.
        Returns: (success: bool, attempts_made: int, error_message: Optional[str])
        """
        date_str = datetime.now(timezone.utc).strftime("%B %d, %Y")
        logger.info(f"DigestAgent: Compiling Daily Digest for {date_str} (High: {len(high_jobs)}, Medium: {len(medium_jobs)})")
        
        try:
            subject = f"Daily AI Career Report - {date_str}"
            context = {
                "high_priority_jobs": high_jobs,
                "medium_priority_jobs": medium_jobs,
                "new_jobs_count": len(high_jobs) + len(medium_jobs),
                "ready_resumes_count": len(high_jobs),
                "dashboard_url": "http://127.0.0.1:8000/dashboard",
                "date": date_str
            }
            
            # Render responsive HTML content using templates
            html_content = self.template_engine.render("daily_digest.html", context)
            
            # Send using EmailService
            success, attempts, error_msg = self.email_service.send_html_email(subject, html_content)
            
            if success:
                logger.info(f"DigestAgent: Daily Digest email delivered successfully.")
            else:
                logger.error(f"DigestAgent: Daily Digest delivery failed: {error_msg}")
                
            return success, attempts, error_msg
            
        except Exception as e:
            err_msg = f"Failed to assemble Daily Digest email: {e}"
            logger.error(err_msg, exc_info=True)
            return False, 1, err_msg
