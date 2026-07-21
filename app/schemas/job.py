import json
from datetime import datetime, timezone
from typing import Optional, List, Any
from pydantic import BaseModel, Field, HttpUrl, field_validator, ConfigDict

class JobBase(BaseModel):
    """
    Base data model for job details with basic validation rules.
    """
    title: str = Field(..., min_length=1, description="Title of the job position")
    company: str = Field(..., min_length=1, description="Name of the hiring company")
    location: str = Field(..., min_length=1, description="Geographic location of the job")
    job_url: str = Field(..., description="Unique URL directly pointing to the job posting")
    description: str = Field(..., min_length=1, description="Full description or snippet of the job role")
    source: str = Field(..., min_length=1, description="Source of the job listing (e.g. Wellfound)")
    date_posted: datetime = Field(..., description="Timestamp of when the job was posted")

    @field_validator("job_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """
        Validates that the URL matches basic HTTP/HTTPS format.
        """
        if not v.startswith("http://") and not v.startswith("https://"):
            raise ValueError("URL must start with http:// or https://")
        return v

class JobCreate(JobBase):
    """
    Schema for creating a new job. Represents input data before database insertion.
    """
    pass

class Job(JobBase):
    """
    Schema representing a job retrieved from the database, containing system fields,
    AI evaluation scores, and RAG retrieval metadata.
    """
    id: int = Field(..., description="Unique auto-incrementing identifier from the database")
    created_at: datetime = Field(..., description="Timestamp of database record creation")

    # AI evaluation fields (Day 3)
    match_score: Optional[int] = Field(None, description="Semantic match score from 0 to 100")
    should_apply: Optional[bool] = Field(None, description="AI recommendation on whether the candidate should apply")
    priority: Optional[str] = Field(None, description="Application priority level (e.g., High, Medium, Low)")
    summary: Optional[str] = Field(None, description="Detailed explanation of the AI recommendation")
    strengths: Optional[List[str]] = Field(None, description="List of candidate's strengths matching this job")
    missing_skills: Optional[List[str]] = Field(None, description="List of skills required by the job but missing from the resume")
    learning_effort: Optional[str] = Field(None, description="Estimated effort to acquire missing skills (Low, Medium, High)")
    confidence: Optional[float] = Field(None, description="AI agent confidence score from 0.0 to 1.0")
    analysis_timestamp: Optional[datetime] = Field(None, description="Timestamp of the AI analysis execution")

    # RAG metadata fields (Day 4)
    retrieved_chunk_ids: Optional[List[str]] = Field(None, description="List of chunks parsed and retrieved for this matching query")
    retrieval_time: Optional[float] = Field(None, description="Latency of the vector DB query search in seconds")
    embedding_model: Optional[str] = Field(None, description="Model used to embed job/resume elements")
    retrieval_score: Optional[float] = Field(None, description="Semantic similarity score returned by Vector Store search")

    # Enable ORM mode for compatibility with SQLAlchemy model instances
    model_config = ConfigDict(from_attributes=True)

    @field_validator("strengths", "missing_skills", "retrieved_chunk_ids", mode="before")
    @classmethod
    def parse_json_list(cls, v: Any) -> Optional[List[str]]:
        """
        Pydantic validator to automatically convert SQLite string-serialized JSON arrays
        back into Python Lists of strings when validating database records.
        Supports list loading directly and handles fallback commas.
        """
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return [str(item) for item in parsed]
            except Exception:
                # Fallback in case of parsing failures
                return [s.strip() for s in v.split(",") if s.strip()] if v else []
        elif isinstance(v, list):
            return [str(item) for item in v]
        return v

class Application(BaseModel):
    """
    Pydantic schema representing an application tracking record.
    Matches ApplicationModel SQLite attributes.
    """
    id: int
    job_id: int
    company: str
    position: str
    status: str
    resume_path: Optional[str] = None
    cover_letter_path: Optional[str] = None
    applied_at: Optional[datetime] = None
    last_updated: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class CandidateProfile(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    portfolio: Optional[str] = None
    years_of_experience: Optional[float] = 0.0
    preferred_salary: Optional[str] = None
    notice_period: Optional[str] = None
    last_updated: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class ResumeVersion(BaseModel):
    id: Optional[int] = None
    filename: str
    file_path: str
    file_hash: str
    version: int
    is_active: bool
    upload_date: Optional[datetime] = None
    extracted_text_path: Optional[str] = None
    embedding_status: str
    last_indexed: Optional[datetime] = None
    chunk_count: int
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

