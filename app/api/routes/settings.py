import os
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

class EmailValidationRequest(BaseModel):
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None

class EmailTestRequest(EmailValidationRequest):
    notification_email: Optional[str] = None

class SettingsUpdateRequest(BaseModel):
    # Candidate Profile
    candidate_name: Optional[str] = None
    email_address: Optional[str] = None
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    portfolio: Optional[str] = None
    years_of_experience: Optional[float] = None
    preferred_salary: Optional[str] = None
    notice_period: Optional[str] = None

    # Job Preferences
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

    # AI Settings
    gemini_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    primary_model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    retry_count: Optional[int] = None
    request_timeout: Optional[int] = None

    # Email Settings
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    notification_email: Optional[str] = None

    # System & Scheduler & Resume
    minimum_match_score: Optional[int] = None
    scheduler_frequency_hours: Optional[int] = None
    resume_content: Optional[str] = None

@router.get("")
def get_current_settings(
    repo: JobRepository = Depends(JobRepository),
    username: str = Depends(get_current_user)
):
    """
    Retrieves all application settings across Profile, Job Preferences, AI Settings,
    Email Configurations, Scheduler Controls, and Resume Knowledge Base.
    """
    memory_manager = ApplicationMemoryManager()
    memory = memory_manager.memory
    profile = repo.get_candidate_profile()

    # Read resume markdown content
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

    return {
        # Candidate Profile
        "candidate_name": profile.name if profile and profile.name else profile_dict.get("name", "Candidate Name"),
        "email_address": profile.email if profile and profile.email else memory.get("email_address", settings.TO_EMAIL),
        "phone": profile.phone if profile and profile.phone else profile_dict.get("phone", ""),
        "linkedin": profile.linkedin if profile and profile.linkedin else profile_dict.get("linkedin", ""),
        "github": profile.github if profile and profile.github else profile_dict.get("github", ""),
        "portfolio": profile.portfolio if profile and profile.portfolio else profile_dict.get("portfolio", ""),
        "years_of_experience": profile.years_of_experience if profile and profile.years_of_experience is not None else profile_dict.get("years_of_experience", settings.MAX_EXPERIENCE),
        "preferred_salary": profile.preferred_salary if profile and profile.preferred_salary else profile_dict.get("preferred_salary", ""),
        "notice_period": profile.notice_period if profile and profile.notice_period else profile_dict.get("notice_period", ""),

        # Job Preferences
        "preferred_roles": job_pref_dict.get("preferred_roles", memory.get("preferred_technologies", settings.JOB_KEYWORDS)),
        "preferred_locations": memory.get("preferred_locations", settings.PREFERRED_LOCATIONS),
        "enable_remote": job_pref_dict.get("enable_remote", settings.ENABLE_REMOTE),
        "enable_hybrid": job_pref_dict.get("enable_hybrid", True),
        "enable_onsite": job_pref_dict.get("enable_onsite", False),
        "minimum_salary": job_pref_dict.get("minimum_salary", "$80,000 / yr"),
        "maximum_salary": job_pref_dict.get("maximum_salary", "$200,000 / yr"),
        "experience_level": job_pref_dict.get("experience_level", "Mid-Level"),
        "preferred_skills": job_pref_dict.get("preferred_skills", settings.REQUIRED_SKILLS),
        "ignored_companies": memory.get("ignored_companies", []),
        "ignored_keywords": job_pref_dict.get("ignored_keywords", ["Crypto", "Unpaid", "Sales"]),

        # AI Settings
        "gemini_api_key": ai_dict.get("gemini_api_key", os.getenv("GEMINI_API_KEY", "")),
        "openai_api_key": ai_dict.get("openai_api_key", settings.OPENAI_API_KEY or ""),
        "primary_model": ai_dict.get("primary_model", settings.MODEL_NAME),
        "temperature": ai_dict.get("temperature", settings.TEMPERATURE),
        "max_tokens": ai_dict.get("max_tokens", settings.MAX_TOKENS),
        "retry_count": ai_dict.get("retry_count", settings.MAX_RETRIES),
        "request_timeout": ai_dict.get("request_timeout", settings.REQUEST_TIMEOUT),

        # Email Settings
        "smtp_host": email_dict.get("smtp_host", settings.SMTP_HOST),
        "smtp_port": email_dict.get("smtp_port", settings.SMTP_PORT),
        "smtp_username": email_dict.get("smtp_username", settings.SMTP_USERNAME or ""),
        "smtp_password": email_dict.get("smtp_password", settings.SMTP_PASSWORD or ""),
        "notification_email": email_dict.get("notification_email", memory.get("email_address", settings.TO_EMAIL)),
        "email_status": email_dict.get("status", "Unvalidated" if not settings.SMTP_USERNAME else "Connected"),

        # System & Scheduler & Resume
        "minimum_match_score": memory.get("minimum_match_score", settings.MATCH_THRESHOLD),
        "scheduler_frequency_hours": memory.get("scheduler_frequency_hours", settings.COLLECTION_INTERVAL_HOURS),
        "resume_content": resume_content
    }

@router.patch("")
def update_settings(
    payload: SettingsUpdateRequest = Body(...),
    repo: JobRepository = Depends(JobRepository),
    username: str = Depends(get_current_user)
):
    """
    Updates configuration values, overwrites resume files, and persists settings.
    """
    try:
        memory_manager = ApplicationMemoryManager()
        memory = memory_manager.memory

        # 1. Update Candidate Profile in DB & Memory
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
        if payload.years_of_experience is not None: profile_update_args["years_of_experience"] = payload.years_of_experience
        if payload.preferred_salary is not None: profile_update_args["preferred_salary"] = payload.preferred_salary
        if payload.notice_period is not None: profile_update_args["notice_period"] = payload.notice_period

        if profile_update_args:
            repo.update_candidate_profile(**profile_update_args)
            if "candidate_profile" not in memory or not isinstance(memory["candidate_profile"], dict):
                memory["candidate_profile"] = {}
            memory["candidate_profile"].update(profile_update_args)

        # 2. Update Job Preferences in Memory
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

        # 3. Update AI Settings in Memory & Runtime Settings
        if "ai_settings" not in memory: memory["ai_settings"] = {}
        ai = memory["ai_settings"]
        if payload.gemini_api_key is not None:
            ai["gemini_api_key"] = payload.gemini_api_key
            os.environ["GEMINI_API_KEY"] = payload.gemini_api_key
        if payload.openai_api_key is not None:
            ai["openai_api_key"] = payload.openai_api_key
            settings.OPENAI_API_KEY = payload.openai_api_key
        if payload.primary_model is not None:
            ai["primary_model"] = payload.primary_model
            settings.MODEL_NAME = payload.primary_model
        if payload.temperature is not None:
            ai["temperature"] = payload.temperature
            settings.TEMPERATURE = payload.temperature
        if payload.max_tokens is not None:
            ai["max_tokens"] = payload.max_tokens
            settings.MAX_TOKENS = payload.max_tokens
        if payload.retry_count is not None:
            ai["retry_count"] = payload.retry_count
            settings.MAX_RETRIES = payload.retry_count
        if payload.request_timeout is not None:
            ai["request_timeout"] = payload.request_timeout
            settings.REQUEST_TIMEOUT = payload.request_timeout

        # 4. Update Email Settings in Memory & Runtime Settings
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
            em["smtp_password"] = payload.smtp_password
            settings.SMTP_PASSWORD = payload.smtp_password
        if payload.notification_email is not None:
            em["notification_email"] = payload.notification_email
            settings.TO_EMAIL = payload.notification_email

        # 5. System & Scheduler Settings
        if payload.minimum_match_score is not None:
            memory["minimum_match_score"] = payload.minimum_match_score
            settings.MATCH_THRESHOLD = payload.minimum_match_score
        if payload.scheduler_frequency_hours is not None:
            memory["scheduler_frequency_hours"] = payload.scheduler_frequency_hours
            settings.COLLECTION_INTERVAL_HOURS = payload.scheduler_frequency_hours
            scheduler_manager.restart(interval_hours=payload.scheduler_frequency_hours)

        # 6. Update resume content if provided
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

        # 7. Save memory file
        memory_manager.save_memory()

        return {
            "status": "success",
            "message": "All configuration settings and preferences saved successfully."
        }
    except Exception as e:
        logger.error(f"Failed to update settings: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save settings: {e}"
        )

@router.post("/email/validate")
def validate_email_settings(
    payload: EmailValidationRequest = Body(...),
    username: str = Depends(get_current_user)
):
    """
    Validates Gmail / SMTP host, port, username, and app password connection without sending an email.
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

@router.post("/email/test")
def send_test_email(
    payload: EmailTestRequest = Body(...),
    username: str = Depends(get_current_user)
):
    """
    Sends a test email to the configured notification recipient address.
    """
    email_service = EmailService()
    target_recipient = payload.notification_email or settings.TO_EMAIL
    
    if not target_recipient:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Notification email recipient address is required."
        )

    success, message = email_service.send_test_email(
        to_email=target_recipient,
        host=payload.smtp_host,
        port=payload.smtp_port,
        username=payload.smtp_username,
        password=payload.smtp_password
    )

    return {
        "status": "success" if success else "error",
        "message": message
    }
