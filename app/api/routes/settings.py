import os
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Body, status
from pydantic import BaseModel
from app.auth.authentication import get_current_user
from app.config import settings
from app.database.repository import JobRepository
from app.memory.application_memory import ApplicationMemoryManager
from app.notifications.email_service import EmailService
from app.scheduler.scheduler_manager import scheduler_manager
from app.logger import logger

router = APIRouter(prefix="/api/settings", tags=["Settings"])

def _mask_secret(secret: Optional[str]) -> str:
    """
    Masks sensitive values (API Keys, SMTP Passwords) for GET API responses.
    Never exposes raw secrets in plain text.
    """
    if not secret or not secret.strip():
        return ""
    s = secret.strip()
    if s.startswith("••••") or s == "********":
        return s
    if len(s) > 8:
        return f"{s[:4]}••••••••{s[-4:]}"
    return "••••••••"

class EmailValidationRequest(BaseModel):
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None

class EmailTestRequest(EmailValidationRequest):
    notification_email: Optional[str] = None

class GeminiTestRequest(BaseModel):
    gemini_api_key: Optional[str] = None
    provider: Optional[str] = "Google Gemini"
    primary_model: Optional[str] = "gemini-2.5-flash"

class SettingsUpdateRequest(BaseModel):
    # Module 1: Candidate Profile
    candidate_name: Optional[str] = None
    email_address: Optional[str] = None
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    portfolio: Optional[str] = None
    current_location: Optional[str] = None
    years_of_experience: Optional[float] = None
    preferred_salary: Optional[str] = None
    notice_period: Optional[str] = None

    # Module 5: Job Preferences
    preferred_roles: Optional[List[str]] = None
    preferred_locations: Optional[List[str]] = None
    enable_remote: Optional[bool] = None
    enable_hybrid: Optional[bool] = None
    enable_onsite: Optional[bool] = None
    minimum_salary: Optional[str] = None
    maximum_salary: Optional[str] = None
    experience_level: Optional[str] = None
    preferred_skills: Optional[List[str]] = None
    ignored_companies: Optional[List[str]] = None
    ignored_keywords: Optional[List[str]] = None
    max_jobs_per_day: Optional[int] = None
    minimum_match_score: Optional[int] = None

    # Module 3: AI Gateway & Settings
    gemini_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    provider: Optional[str] = None
    primary_model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    retry_count: Optional[int] = None
    request_timeout: Optional[int] = None

    # Module 4: Email Configuration
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    notification_email: Optional[str] = None
    enable_daily_digest: Optional[bool] = None
    enable_instant_alerts: Optional[bool] = None

    # Module 6: Scheduler & System
    enable_scheduler: Optional[bool] = None
    scheduler_frequency_hours: Optional[int] = None
    digest_time: Optional[str] = None
    timezone: Optional[str] = None
    max_concurrent_jobs: Optional[int] = None
    retry_policy: Optional[str] = None
    resume_content: Optional[str] = None

@router.get("")
def get_current_settings(
    repo: JobRepository = Depends(JobRepository),
    username: str = Depends(get_current_user)
):
    """
    Retrieves configuration values across all 7 Control Center modules.
    Masks all sensitive credentials (API Keys, SMTP passwords) for privacy and security.
    """
    memory_manager = ApplicationMemoryManager()
    memory = memory_manager.memory
    profile = repo.get_candidate_profile()

    # Read active resume template content
    resume_content = ""
    resume_path = os.path.abspath(settings.RESUME_TEMPLATE)
    if os.path.exists(resume_path):
        try:
            with open(resume_path, "r", encoding="utf-8") as f:
                resume_content = f.read()
        except Exception as e:
            logger.warning(f"Failed to read resume template file: {e}")

    profile_dict = memory.get("candidate_profile", {})
    ai_dict = memory.get("ai_settings", {})
    job_pref_dict = memory.get("job_preferences", {})
    email_dict = memory.get("email_settings", {})
    sch_dict = memory.get("scheduler_settings", {})

    raw_gemini_key = ai_dict.get("gemini_api_key", os.getenv("GEMINI_API_KEY", ""))
    raw_smtp_pass = email_dict.get("smtp_password", settings.SMTP_PASSWORD or "")

    return {
        # Module 1: Candidate Profile
        "candidate_name": profile.name if profile and profile.name else profile_dict.get("name", "Candidate Name"),
        "email_address": profile.email if profile and profile.email else memory.get("email_address", settings.TO_EMAIL),
        "phone": profile.phone if profile and profile.phone else profile_dict.get("phone", ""),
        "linkedin": profile.linkedin if profile and profile.linkedin else profile_dict.get("linkedin", ""),
        "github": profile.github if profile and profile.github else profile_dict.get("github", ""),
        "portfolio": profile.portfolio if profile and profile.portfolio else profile_dict.get("portfolio", ""),
        "current_location": profile.current_location if profile and hasattr(profile, 'current_location') and profile.current_location else profile_dict.get("current_location", "San Francisco, CA"),
        "years_of_experience": profile.years_of_experience if profile and profile.years_of_experience is not None else profile_dict.get("years_of_experience", settings.MAX_EXPERIENCE),
        "preferred_salary": profile.preferred_salary if profile and profile.preferred_salary else profile_dict.get("preferred_salary", "$120,000 / yr"),
        "notice_period": profile.notice_period if profile and profile.notice_period else profile_dict.get("notice_period", "2 Weeks"),

        # Module 5: Job Preferences
        "preferred_roles": job_pref_dict.get("preferred_roles", memory.get("preferred_technologies", settings.JOB_KEYWORDS)),
        "preferred_locations": memory.get("preferred_locations", settings.PREFERRED_LOCATIONS),
        "enable_remote": job_pref_dict.get("enable_remote", settings.ENABLE_REMOTE),
        "enable_hybrid": job_pref_dict.get("enable_hybrid", True),
        "enable_onsite": job_pref_dict.get("enable_onsite", False),
        "minimum_salary": job_pref_dict.get("minimum_salary", "$100,000 / yr"),
        "maximum_salary": job_pref_dict.get("maximum_salary", "$250,000 / yr"),
        "experience_level": job_pref_dict.get("experience_level", "Senior"),
        "preferred_skills": job_pref_dict.get("preferred_skills", settings.REQUIRED_SKILLS),
        "ignored_companies": memory.get("ignored_companies", []),
        "ignored_keywords": job_pref_dict.get("ignored_keywords", ["Crypto", "Unpaid", "Sales"]),
        "max_jobs_per_day": job_pref_dict.get("max_jobs_per_day", 50),
        "minimum_match_score": memory.get("minimum_match_score", settings.MATCH_THRESHOLD),

        # Module 3: AI Configuration (Masked Secrets)
        "gemini_api_key": _mask_secret(raw_gemini_key),
        "provider": ai_dict.get("provider", "Google Gemini"),
        "primary_model": ai_dict.get("primary_model", settings.MODEL_NAME),
        "temperature": ai_dict.get("temperature", settings.TEMPERATURE),
        "max_tokens": ai_dict.get("max_tokens", settings.MAX_TOKENS),
        "top_p": ai_dict.get("top_p", 0.95),
        "retry_count": ai_dict.get("retry_count", settings.MAX_RETRIES),
        "request_timeout": ai_dict.get("request_timeout", settings.REQUEST_TIMEOUT),
        "ai_connection_status": "Configured" if raw_gemini_key or os.getenv("GEMINI_API_KEY") else "Mock / Offline",

        # Module 4: Email Configuration (Masked Secrets)
        "smtp_host": email_dict.get("smtp_host", settings.SMTP_HOST),
        "smtp_port": email_dict.get("smtp_port", settings.SMTP_PORT),
        "smtp_username": email_dict.get("smtp_username", settings.SMTP_USERNAME or ""),
        "smtp_password": _mask_secret(raw_smtp_pass),
        "notification_email": email_dict.get("notification_email", memory.get("email_address", settings.TO_EMAIL)),
        "enable_daily_digest": email_dict.get("enable_daily_digest", True),
        "enable_instant_alerts": email_dict.get("enable_instant_alerts", True),
        "email_status": email_dict.get("status", "Unvalidated" if not settings.SMTP_USERNAME else "Connected"),

        # Module 6: Scheduler & System
        "enable_scheduler": sch_dict.get("enable_scheduler", True),
        "scheduler_frequency_hours": memory.get("scheduler_frequency_hours", settings.COLLECTION_INTERVAL_HOURS),
        "digest_time": sch_dict.get("digest_time", "09:00 AM"),
        "timezone": sch_dict.get("timezone", "UTC"),
        "max_concurrent_jobs": sch_dict.get("max_concurrent_jobs", 5),
        "retry_policy": sch_dict.get("retry_policy", "Exponential Backoff"),
        "resume_content": resume_content
    }

@router.patch("")
def update_settings(
    payload: SettingsUpdateRequest = Body(...),
    repo: JobRepository = Depends(JobRepository),
    username: str = Depends(get_current_user)
):
    """
    Updates configuration values across all 7 modules. Protects masked secrets from accidental overwrite.
    """
    try:
        memory_manager = ApplicationMemoryManager()
        memory = memory_manager.memory

        # 1. Candidate Profile Update
        profile_update_args = {}
        if payload.candidate_name is not None: profile_update_args["name"] = payload.candidate_name
        if payload.email_address is not None:
            profile_update_args["email"] = payload.email_address
            memory["email_address"] = payload.email_address
            settings.TO_EMAIL = payload.email_address
        if payload.phone is not None: profile_update_args["phone"] = payload.phone
        if payload.linkedin is not None: profile_update_args["linkedin"] = payload.linkedin
        if payload.github is not None: profile_update_args["github"] = payload.github
        if payload.portfolio is not None: profile_update_args["portfolio"] = payload.portfolio
        if payload.current_location is not None: profile_update_args["current_location"] = payload.current_location
        if payload.years_of_experience is not None: profile_update_args["years_of_experience"] = payload.years_of_experience
        if payload.preferred_salary is not None: profile_update_args["preferred_salary"] = payload.preferred_salary
        if payload.notice_period is not None: profile_update_args["notice_period"] = payload.notice_period

        if profile_update_args:
            repo.update_candidate_profile(**profile_update_args)
            if "candidate_profile" not in memory or not isinstance(memory["candidate_profile"], dict):
                memory["candidate_profile"] = {}
            memory["candidate_profile"].update(profile_update_args)

        # 2. Job Preferences Update
        if "job_preferences" not in memory: memory["job_preferences"] = {}
        jp = memory["job_preferences"]
        if payload.preferred_roles is not None: jp["preferred_roles"] = payload.preferred_roles
        if payload.preferred_locations is not None:
            memory["preferred_locations"] = payload.preferred_locations
            settings.PREFERRED_LOCATIONS = payload.preferred_locations
        if payload.enable_remote is not None:
            jp["enable_remote"] = payload.enable_remote
            settings.ENABLE_REMOTE = payload.enable_remote
        if payload.enable_hybrid is not None: jp["enable_hybrid"] = payload.enable_hybrid
        if payload.enable_onsite is not None: jp["enable_onsite"] = payload.enable_onsite
        if payload.minimum_salary is not None: jp["minimum_salary"] = payload.minimum_salary
        if payload.maximum_salary is not None: jp["maximum_salary"] = payload.maximum_salary
        if payload.experience_level is not None: jp["experience_level"] = payload.experience_level
        if payload.preferred_skills is not None:
            jp["preferred_skills"] = payload.preferred_skills
            settings.REQUIRED_SKILLS = payload.preferred_skills
        if payload.ignored_companies is not None: memory["ignored_companies"] = payload.ignored_companies
        if payload.ignored_keywords is not None: jp["ignored_keywords"] = payload.ignored_keywords
        if payload.max_jobs_per_day is not None: jp["max_jobs_per_day"] = payload.max_jobs_per_day
        if payload.minimum_match_score is not None:
            memory["minimum_match_score"] = payload.minimum_match_score
            settings.MATCH_THRESHOLD = payload.minimum_match_score

        # 3. AI Gateway Settings Update (Protect Masked Key)
        if "ai_settings" not in memory: memory["ai_settings"] = {}
        ai = memory["ai_settings"]
        if payload.gemini_api_key is not None:
            k = payload.gemini_api_key.strip()
            if k and not k.startswith("••••") and k != "********":
                ai["gemini_api_key"] = k
                os.environ["GEMINI_API_KEY"] = k
        if payload.provider is not None: ai["provider"] = payload.provider
        if payload.primary_model is not None:
            ai["primary_model"] = payload.primary_model
            settings.MODEL_NAME = payload.primary_model
        if payload.temperature is not None:
            ai["temperature"] = payload.temperature
            settings.TEMPERATURE = payload.temperature
        if payload.max_tokens is not None:
            ai["max_tokens"] = payload.max_tokens
            settings.MAX_TOKENS = payload.max_tokens
        if payload.top_p is not None: ai["top_p"] = payload.top_p
        if payload.retry_count is not None:
            ai["retry_count"] = payload.retry_count
            settings.MAX_RETRIES = payload.retry_count
        if payload.request_timeout is not None:
            ai["request_timeout"] = payload.request_timeout
            settings.REQUEST_TIMEOUT = payload.request_timeout

        # 4. Email Settings Update (Protect Masked Password)
        if "email_settings" not in memory: memory["email_settings"] = {}
        em = memory["email_settings"]
        if payload.smtp_host is not None:
            em["smtp_host"] = payload.smtp_host
            settings.SMTP_HOST = payload.smtp_host
        if payload.smtp_port is not None:
            em["smtp_port"] = payload.smtp_port
            settings.SMTP_PORT = payload.smtp_port
        if payload.smtp_username is not None:
            em["smtp_username"] = payload.smtp_username
            settings.SMTP_USERNAME = payload.smtp_username
        if payload.smtp_password is not None:
            p = payload.smtp_password.strip()
            if p and not p.startswith("••••") and p != "********":
                em["smtp_password"] = p
                settings.SMTP_PASSWORD = p
        if payload.notification_email is not None:
            em["notification_email"] = payload.notification_email
            settings.TO_EMAIL = payload.notification_email
        if payload.enable_daily_digest is not None: em["enable_daily_digest"] = payload.enable_daily_digest
        if payload.enable_instant_alerts is not None: em["enable_instant_alerts"] = payload.enable_instant_alerts

        # 5. Scheduler Settings Update
        if "scheduler_settings" not in memory: memory["scheduler_settings"] = {}
        sch = memory["scheduler_settings"]
        if payload.enable_scheduler is not None: sch["enable_scheduler"] = payload.enable_scheduler
        if payload.digest_time is not None: sch["digest_time"] = payload.digest_time
        if payload.timezone is not None: sch["timezone"] = payload.timezone
        if payload.max_concurrent_jobs is not None: sch["max_concurrent_jobs"] = payload.max_concurrent_jobs
        if payload.retry_policy is not None: sch["retry_policy"] = payload.retry_policy
        if payload.scheduler_frequency_hours is not None:
            memory["scheduler_frequency_hours"] = payload.scheduler_frequency_hours
            settings.COLLECTION_INTERVAL_HOURS = payload.scheduler_frequency_hours
            scheduler_manager.restart(interval_hours=payload.scheduler_frequency_hours)

        # 6. Resume Text Content Overwrite
        if payload.resume_content is not None and payload.resume_content.strip():
            resume_path = os.path.abspath(settings.RESUME_TEMPLATE)
            os.makedirs(os.path.dirname(resume_path), exist_ok=True)
            with open(resume_path, "w", encoding="utf-8") as f:
                f.write(payload.resume_content)
                
            hash_file_path = os.path.join(settings.BASE_DIR, "data", "resume_hash.txt")
            if os.path.exists(hash_file_path):
                os.remove(hash_file_path)

            from app.rag.embedding_service import EmbeddingService
            from app.rag.vector_store import VectorStore
            from app.rag.indexing import ResumeIndexingPipeline
            pipeline = ResumeIndexingPipeline(EmbeddingService(), VectorStore())
            pipeline.run(payload.resume_content)

        # 7. Save Memory File
        memory_manager.save_memory()

        return {
            "status": "success",
            "message": "Control Center settings saved successfully across all configuration panels."
        }
    except Exception as e:
        logger.error(f"Failed to update settings: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save settings: {e}"
        )

@router.get("/ai-usage")
def get_ai_usage_metrics(username: str = Depends(get_current_user)):
    """
    Returns real-time usage stats, token consumption, latency, error states, and quota details.
    """
    from app.ai.usage_tracker import ai_usage_tracker
    return ai_usage_tracker.get_usage_summary()

@router.post("/test-gemini")
@router.post("/gemini/test")
def test_gemini_connection(
    payload: GeminiTestRequest = Body(...),
    username: str = Depends(get_current_user)
):
    """
    Performs a live API handshake with Google's Gemini service using google.genai.Client.
    Classifies error states: Connected, Invalid API Key, Quota Exceeded, Timeout, Rate Limited, Model Not Found.
    """
    from app.ai.usage_tracker import ai_usage_tracker

    from app.ai.llm_client import resolve_gemini_api_key
    clean_key = resolve_gemini_api_key(payload.gemini_api_key)

    model_name = payload.primary_model or settings.MODEL_NAME
    if model_name not in ("gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash", "gemini-1.5-pro"):
        model_name = "gemini-2.5-flash"

    if not clean_key:
        ai_usage_tracker.connection_status = "Offline / Mock Mode"
        return {
            "status": "warning",
            "connection_status": "Offline / Mock Mode",
            "provider": "Google Gemini",
            "model": model_name,
            "message": "No valid Gemini API key provided. System operating in local offline simulation mode."
        }
    try:
        from google import genai
        client = genai.Client(api_key=clean_key)
        # Verify API key validity by fetching model metadata
        client.models.get(model=model_name)

        ai_usage_tracker.connection_status = "Connected"
        ai_usage_tracker.active_model = model_name

        return {
            "status": "success",
            "connection_status": "Connected",
            "provider": "Google Gemini",
            "model": model_name,
            "message": f"Successfully authenticated with Google Gemini API ({model_name})."
        }
    except Exception as e:
        err_msg = str(e).encode("utf-8", errors="replace").decode("utf-8")
        err_lower = err_msg.lower()

        if "404" in err_lower or "not_found" in err_lower:
            conn_status = "Model Not Found"
        elif "400" in err_lower or "401" in err_lower or "api_key" in err_lower or "unauthenticated" in err_lower or "invalid" in err_lower:
            conn_status = "Invalid API Key"
        elif "quota" in err_lower or "resource_exhausted" in err_lower:
            conn_status = "Quota Exceeded"
        elif "429" in err_lower or "rate" in err_lower:
            conn_status = "Rate Limited"
        elif "timeout" in err_lower or "deadline" in err_lower:
            conn_status = "Timeout"
        else:
            conn_status = "Connection Error"

        ai_usage_tracker.connection_status = conn_status
        ai_usage_tracker.last_error_message = err_msg
        ai_usage_tracker.last_failed_request = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        logger.warning(f"Gemini API test failed for model '{model_name}' ({conn_status}): {err_msg}")

        return {
            "status": "error",
            "connection_status": conn_status,
            "provider": "Google Gemini",
            "model": model_name,
            "message": f"Gemini API handshake failed ({conn_status}): {err_msg}"
        }

@router.post("/test-email")
@router.post("/email/test")
def send_test_email(
    payload: EmailTestRequest = Body(...),
    username: str = Depends(get_current_user)
):
    """
    Dispatches a test email notification to verify SMTP server handshake and recipient delivery.
    Returns recipient, subject, timestamp, delivery mode, and acceptance status.
    """
    email_service = EmailService()
    target_recipient = payload.notification_email or settings.TO_EMAIL
    
    if not target_recipient:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Notification email recipient address is required."
        )

    res = email_service.send_test_email(
        to_email=target_recipient,
        host=payload.smtp_host,
        port=payload.smtp_port,
        username=payload.smtp_username,
        password=payload.smtp_password
    )

    if isinstance(res, tuple) and len(res) == 3:
        success, message, details = res
        return details
    elif isinstance(res, tuple) and len(res) == 2:
        success, message = res
        return {
            "status": "success" if success else "error",
            "message": message,
            "recipient": target_recipient,
            "subject": "Test Email — Agentic AI Career Assistant",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "delivery_mode": email_service.mode,
            "acceptance_status": "Accepted" if success and not email_service.is_mock else ("Mocked" if success else "Failed")
        }
    else:
        return res

@router.post("/email/validate")
def validate_email_settings(
    payload: EmailValidationRequest = Body(...),
    username: str = Depends(get_current_user)
):
    """
    Validates Gmail / SMTP host, port, username, and app password connection.
    """
    email_service = EmailService()
    success, message = email_service.validate_connection(
        host=payload.smtp_host,
        port=payload.smtp_port,
        username=payload.smtp_username,
        password=payload.smtp_password
    )

    memory_manager = ApplicationMemoryManager()
    if "email_settings" not in memory_manager.memory:
        memory_manager.memory["email_settings"] = {}
    memory_manager.memory["email_settings"]["status"] = "Connected" if success else "Disconnected"
    memory_manager.save_memory()

    return {
        "status": "success" if success else "error",
        "connection_status": "Connected" if success else "Disconnected",
        "message": message
    }
