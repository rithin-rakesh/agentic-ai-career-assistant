import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple, Optional
from app.ai.llm_client import BaseLLM, MockLLM, get_llm_client
from app.notifications.email_service import EmailService
from app.notifications.template_engine import TemplateEngine
from app.logger import logger

class DigestAgent:
    """
    DigestAgent processes collected job listings, groups them by priority,
    uses Gemini to generate executive summaries and strategic recommendations,
    renders a responsive daily digest HTML template, and transmits it via EmailService.
    """
    def __init__(self, email_service: EmailService = None, template_engine: TemplateEngine = None, llm_client: Optional[BaseLLM] = None):
        self.email_service = email_service or EmailService()
        self.template_engine = template_engine or TemplateEngine()
        self.llm_client = llm_client or get_llm_client()

    def generate_digest_summary(self, high_jobs: List[Dict[str, Any]], medium_jobs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generates executive summary and career advice via Gemini for daily digest reports.
        """
        total_jobs = len(high_jobs) + len(medium_jobs)
        top_titles = [j.get("title", "") for j in high_jobs[:3]]

        if isinstance(self.llm_client, MockLLM) or getattr(self.llm_client, "mock_fallback", None) is not None:
            return {
                "executive_summary": f"Identified {total_jobs} relevant career opportunities today with high match scores in GenAI and Full Stack Python.",
                "daily_recommendation": f"Focus immediate application efforts on top matches: {', '.join(top_titles) if top_titles else 'High Priority listings'}.",
                "top_opportunities": top_titles,
                "career_advice": "Ensure your resume highlights FastAPI and Qdrant RAG implementation experience."
            }

        system_prompt = (
            "You are an executive career coach writing a daily digest summary for an AI engineer.\n"
            "Provide a brief executive summary, daily recommendation, and actionable career advice in clean JSON."
        )
        user_prompt = (
            f"Total New Matches Today: {total_jobs}\n"
            f"High Priority Jobs: {[j.get('title') + ' at ' + j.get('company') for j in high_jobs]}\n"
            f"Medium Priority Jobs: {[j.get('title') + ' at ' + j.get('company') for j in medium_jobs]}"
        )

        try:
            res = self.llm_client.generate(system_prompt, user_prompt, response_format={"type": "json_object"})
            parsed = json.loads(res)
            return {
                "executive_summary": parsed.get("executive_summary", f"Identified {total_jobs} opportunities today."),
                "daily_recommendation": parsed.get("daily_recommendation", "Review high-priority application links on your control center."),
                "top_opportunities": top_titles,
                "career_advice": parsed.get("career_advice", "Keep resume keywords tailored to target engineering postings.")
            }
        except Exception as e:
            logger.warning(f"DigestAgent: Failed to generate LLM summary: {e}")
            return {
                "executive_summary": f"Identified {total_jobs} relevant career opportunities today.",
                "daily_recommendation": "Prioritize high match score applications.",
                "top_opportunities": top_titles,
                "career_advice": "Focus on high-impact technology stack competencies."
            }

    def send_daily_digest(self, high_jobs: List[Dict[str, Any]], medium_jobs: List[Dict[str, Any]]) -> Tuple[bool, int, Optional[str]]:
        """
        Gathers ranked jobs, generates Gemini executive summary, renders daily_digest.html, and transmits email.
        Returns: (success: bool, attempts_made: int, error_message: Optional[str])
        """
        date_str = datetime.now(timezone.utc).strftime("%B %d, %Y")
        logger.info(f"DigestAgent: Compiling Daily Digest for {date_str} (High: {len(high_jobs)}, Medium: {len(medium_jobs)})")
        
        try:
            digest_info = self.generate_digest_summary(high_jobs, medium_jobs)
            subject = f"Daily AI Career Report - {date_str}"
            context = {
                "high_priority_jobs": high_jobs,
                "medium_priority_jobs": medium_jobs,
                "new_jobs_count": len(high_jobs) + len(medium_jobs),
                "ready_resumes_count": len(high_jobs),
                "dashboard_url": "http://127.0.0.1:8000/dashboard",
                "date": date_str,
                "executive_summary": digest_info["executive_summary"],
                "daily_recommendation": digest_info["daily_recommendation"],
                "career_advice": digest_info["career_advice"]
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
