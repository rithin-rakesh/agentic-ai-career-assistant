import os
from pathlib import Path
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

# Base directory of the job_agent project
BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    """
    Application settings loaded from environment variables and .env file.
    Utilizes pydantic-settings for validation and type-casting.
    """
    BASE_DIR: str = str(BASE_DIR)
    
    # Environment & Security Configuration
    ENVIRONMENT: str = "development"
    SECRET_KEY: str = "dev_secret_key_change_in_production_32bytes_min"
    JWT_SECRET: str = "agentic-ai-job-search-secret-2026"
    SESSION_SECRET: str = "dev_session_secret_key_32bytes_min"
    COOKIE_SECURE: bool = False
    ALLOWED_ORIGINS: List[str] = ["http://localhost:8000", "http://localhost", "http://127.0.0.1:8000", "http://127.0.0.1"]

    # Authentication Credentials
    DASHBOARD_USERNAME: str = "admin"
    DASHBOARD_PASSWORD: Optional[str] = None
    
    # SQLite / PostgreSQL Database URL
    DATABASE_URL: str = "sqlite:///data/jobs.db"
    POSTGRES_PASSWORD: Optional[str] = None
    
    # Toggle for using a mock collector (returns simulated jobs) vs real requests
    MOCK_COLLECTOR: bool = True
    
    # Structured logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    
    # Collection interval for the scheduler (in hours)
    COLLECTION_INTERVAL_HOURS: int = 4
    
    # Filters configuration
    JOB_KEYWORDS: List[str] = [
        "AI Engineer", "ML Engineer", "Data Scientist", 
        "Generative AI Engineer", "LLM Engineer", 
        "Computer Vision Engineer", "Data Analyst", "Python Developer"
    ]
    
    PREFERRED_LOCATIONS: List[str] = [
        "Bangalore", "Hyderabad", "Pune", "Chennai", "Kochi"
    ]
    
    MAX_EXPERIENCE: int = 2
    ENABLE_REMOTE: bool = True
    
    REQUIRED_SKILLS: List[str] = [
        "Python", "SQL", "TensorFlow", "PyTorch", "OpenCV", 
        "YOLO", "Power BI", "Machine Learning", "Deep Learning", 
        "LLM", "Generative AI"
    ]
    
    # Phase 2.4 Smart Filtering Defaults
    BLACKLISTED_COMPANIES: List[str] = []
    IGNORED_KEYWORDS: List[str] = ["internship", "volunteer", "unpaid"]
    MINIMUM_SALARY: int = 0
    MAX_JOB_AGE_DAYS: int = 30
    
    # Day 3 & Phase 2.2 AI Agent & Gemini Configuration
    GEMINI_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    MODEL_NAME: str = "gemini-2.5-flash"
    MAX_TOKENS: int = 1000
    TEMPERATURE: float = 0.2
    REQUEST_TIMEOUT: int = 30
    MOCK_LLM: bool = True
    RESUME_PATH: str = "data/resume.md"

    # Day 4 Semantic Search & RAG Configuration
    VECTOR_DB_URL: str = "data/qdrant_db"
    COLLECTION_NAME: str = "resume_chunks"
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    TOP_K: int = 3
    SIMILARITY_THRESHOLD: float = 0.3
    QDRANT_API_KEY: Optional[str] = None

    # Day 9 Adaptive Learning & Career Strategy Configs
    LEARNING_ENABLED: bool = True
    CAREER_STRATEGY_ENABLED: bool = True
    MIN_FEEDBACK_EVENTS: int = 20
    LEARNING_INTERVAL: str = "24h"

    # Day 5 LangGraph Orchestration Configuration
    MAX_RETRIES: int = 2
    MATCH_THRESHOLD: int = 60
    CHECKPOINT_INTERVAL: int = 1

    # Day 6 SMTP Notification Configuration
    EMAIL_MODE: str = "SMTP"  # Options: SMTP | MOCK
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    FROM_EMAIL: str = "assistant@agenticjobsearch.com"
    TO_EMAIL: str = "candidate@example.com"
    NOTIFICATION_EMAIL: Optional[str] = None
    DIGEST_TIME: str = "18:00"
    INSTANT_THRESHOLD: int = 85
    SMTP_RETRIES: int = 3
    SMTP_TIMEOUT: int = 10

    # Day 7 Autonomous Career Assistant Configuration
    RESUME_TEMPLATE: str = "data/resume.md"
    OUTPUT_DIRECTORY: str = "data/applications"
    PDF_ENABLED: bool = True
    DOCX_ENABLED: bool = True

    # Day 9 Production Infrastructure Configs
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_PASSWORD: Optional[str] = None
    SENTRY_DSN: Optional[str] = None
    PROMETHEUS_ENABLED: bool = True
    USE_CELERY: bool = False

    # Configuration for Pydantic Settings
    model_config = SettingsConfigDict(
        env_file=os.path.join(BASE_DIR, ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def validate_production_config(self) -> None:
        """
        Validates environment configuration for production deployment.
        Raises ValueError if production mode is active but insecure defaults or missing secrets are detected.
        """
        if self.ENVIRONMENT.lower() != "production":
            return

        insecure_secrets = {
            "dev_secret_key_change_in_production_32bytes_min",
            "agentic-ai-job-search-secret-2026",
            "dev_session_secret_key_32bytes_min",
            "change_me",
            "admin",
            "secret",
            "password"
        }

        errors = []
        if self.SECRET_KEY in insecure_secrets:
            errors.append("SECRET_KEY is using a default insecure development value.")

        if self.JWT_SECRET in insecure_secrets:
            errors.append("JWT_SECRET is using a default insecure development value.")

        if len(self.SECRET_KEY) < 32:
            errors.append("SECRET_KEY must be at least 32 characters long.")

        if len(self.JWT_SECRET) < 32:
            errors.append("JWT_SECRET must be at least 32 characters long.")

        if errors:
            err_msg = "Production Configuration Validation Failed:\n- " + "\n- ".join(errors)
            raise ValueError(err_msg)

    @property
    def db_path_absolute(self) -> str:
        """
        Normalizes the SQLite connection string.
        Resolves it to an absolute path relative to the project root.
        """
        url = self.DATABASE_URL
        if url.startswith("sqlite:///"):
            path_part = url[10:]
            if not os.path.isabs(path_part) and not path_part.startswith("\\"):
                abs_path = os.path.abspath(os.path.join(BASE_DIR, path_part))
                os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                return f"sqlite:///{abs_path.replace(os.sep, '/')}"
        return url

    @property
    def qdrant_path_absolute(self) -> str:
        """
        Normalizes the Qdrant local path.
        If it's a relative path, resolves it to an absolute path relative to the project root
        to make sure it runs correctly from any directory context.
        """
        url = self.VECTOR_DB_URL
        if url.startswith("http://") or url.startswith("https://") or url == ":memory:":
            return url
        if not os.path.isabs(url):
            abs_path = os.path.abspath(os.path.join(BASE_DIR, url))
            os.makedirs(abs_path, exist_ok=True)
            return abs_path.replace(os.sep, "/")
        return url

# Global configuration instance
settings = Settings()
