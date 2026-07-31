from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Float, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class JobModel(Base):
    """
    SQLAlchemy ORM model representing the 'jobs' table.
    Extended with Day 4 columns for RAG (Retrieval-Augmented Generation) metrics.
    """
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=False)
    company = Column(String, nullable=False)
    location = Column(String, nullable=False)
    job_url = Column(String, unique=True, index=True, nullable=False)
    description = Column(Text, nullable=False)
    source = Column(String, nullable=False)
    date_posted = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # AI evaluation fields (Day 3)
    match_score = Column(Integer, nullable=True)
    should_apply = Column(Boolean, nullable=True)
    priority = Column(String, nullable=True)
    summary = Column(Text, nullable=True)
    strengths = Column(Text, nullable=True)          # Stored as serialized JSON list
    missing_skills = Column(Text, nullable=True)     # Stored as serialized JSON list
    learning_effort = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    analysis_timestamp = Column(DateTime, nullable=True)

    # RAG metadata fields (Day 4)
    retrieved_chunk_ids = Column(Text, nullable=True) # Stored as serialized JSON list of strings/ints
    retrieval_time = Column(Float, nullable=True)      # Vector DB query latency in seconds
    embedding_model = Column(String, nullable=True)   # Model name used for embeddings
    retrieval_score = Column(Float, nullable=True)     # Max/Average semantic similarity score achieved

    # Phase 2.4 Normalization & Deduplication fields
    remote_type = Column(String, nullable=True)
    employment_type = Column(String, nullable=True)
    salary_range = Column(String, nullable=True)
    experience_level = Column(String, nullable=True)
    apply_url = Column(String, nullable=True)
    company_url = Column(String, nullable=True)
    collected_timestamp = Column(DateTime, nullable=True)
    content_hash = Column(String, nullable=True, index=True)
    raw_metadata = Column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<JobModel(id={self.id}, title='{self.title}', company='{self.company}', source='{self.source}', match_score={self.match_score}, retrieval_score={self.retrieval_score})>"

class ApplicationModel(Base):
    """
    SQLAlchemy ORM model representing the 'applications' table.
    Stores and tracks prepared cover letters, tailored resumes, and submission statuses.
    """
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    company = Column(String, nullable=False)
    position = Column(String, nullable=False)
    status = Column(String, nullable=False, default="Draft") # Draft, Ready, Applied, Interview, Rejected, Offer, Accepted
    resume_path = Column(String, nullable=True)
    cover_letter_path = Column(String, nullable=True)
    applied_at = Column(DateTime, nullable=True)
    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Establish relationship linking to JobModel
    job = relationship("JobModel", backref="applications")

    def __repr__(self) -> str:
        return f"<ApplicationModel(id={self.id}, job_id={self.job_id}, company='{self.company}', position='{self.position}', status='{self.status}')>"

class ExecutionLogModel(Base):
    """
    SQLAlchemy ORM model representing the 'execution_logs' table.
    Tracks LangGraph node performance metrics, token usage, and exceptions.
    """
    __tablename__ = "execution_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    node_name = Column(String, nullable=False, index=True)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    duration = Column(Float, nullable=False) # In seconds
    status = Column(String, nullable=False) # success or failure
    error_message = Column(Text, nullable=True)
    token_usage = Column(Integer, nullable=True, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    def __repr__(self) -> str:
        return f"<ExecutionLogModel(id={self.id}, node_name='{self.node_name}', status='{self.status}', duration={self.duration})>"


class FeedbackEventModel(Base):
    """
    Tracks interaction and event actions (Viewed, Ignored, Applied, etc.).
    """
    __tablename__ = "feedback_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=True)
    application_id = Column(Integer, ForeignKey("applications.id", ondelete="CASCADE"), nullable=True)
    event_type = Column(String, nullable=False, index=True) # Viewed Job, Ignored Job, Bookmarked, Applied, Resume Generated, Cover Letter Generated, Interview Scheduled, Rejected, Offer Received, Offer Accepted, Application Withdrawn
    payload = Column(Text, nullable=True) # JSON details
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class PreferenceModel(Base):
    """
    Stores dynamically calculated candidate preference scores.
    """
    __tablename__ = "preferences"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String, nullable=False, index=True) # technology, role, location, salary, industry, work_style, company_size, remote_pref
    name = Column(String, nullable=False, index=True) # e.g. Python, Remote, Startup, FinTech
    score = Column(Float, nullable=False, default=0.5)
    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class CompanyProfileModel(Base):
    """
    Aggregates details for company intelligence.
    """
    __tablename__ = "company_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, index=True, nullable=False)
    status = Column(String, nullable=False, default="Neutral") # Favorite, Blocked, Neutral
    applied_count = Column(Integer, default=0, nullable=False)
    rejected_count = Column(Integer, default=0, nullable=False)
    interview_count = Column(Integer, default=0, nullable=False)
    offer_count = Column(Integer, default=0, nullable=False)
    success_rate = Column(Float, default=0.0, nullable=False)
    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class CareerDecisionModel(Base):
    """
    Stores the structured evaluation output from the CareerStrategyAgent.
    """
    __tablename__ = "career_decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), unique=True, nullable=False)
    recommendation = Column(String, nullable=False) # e.g. "Apply Immediately", "Ignore"
    confidence = Column(Float, nullable=False)
    priority = Column(String, nullable=False)
    estimated_interview_probability = Column(String, nullable=False)
    career_growth = Column(String, nullable=False)
    salary_competitiveness = Column(String, nullable=False)
    learning_effort = Column(String, nullable=False)
    resume_changes_required = Column(Boolean, nullable=False, default=False)
    cover_letter_required = Column(Boolean, nullable=False, default=False)
    estimated_application_time = Column(String, nullable=True)
    reasoning = Column(Text, nullable=True) # Serialized JSON list
    missing_skills = Column(Text, nullable=True) # Serialized JSON list
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class LearningMetricModel(Base):
    """
    Tracks self-improvement metrics over time.
    """
    __tablename__ = "learning_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    metric_date = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    accepted_recommendations = Column(Integer, default=0, nullable=False)
    ignored_recommendations = Column(Integer, default=0, nullable=False)
    interview_conversion_rate = Column(Float, default=0.0, nullable=False)
    offer_conversion_rate = Column(Float, default=0.0, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class RecommendationHistoryModel(Base):
    """
    Stores audit histories of multi-criteria recommendation scoring evaluations.
    """
    __tablename__ = "recommendation_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    llm_match_score = Column(Float, nullable=False)
    behavior_score = Column(Float, nullable=False)
    company_preference_score = Column(Float, nullable=False)
    location_preference_score = Column(Float, nullable=False)
    technology_preference_score = Column(Float, nullable=False)
    salary_match_score = Column(Float, nullable=False)
    growth_score = Column(Float, nullable=False)
    risk_score = Column(Float, nullable=False)
    final_score = Column(Float, nullable=False)
    recommendation_reason = Column(Text, nullable=True) # Serialized JSON list
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class CandidateProfileModel(Base):
    """
    Stores candidate personal details and career expectations.
    """
    __tablename__ = "candidate_profile"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=True)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    linkedin = Column(String, nullable=True)
    github = Column(String, nullable=True)
    portfolio = Column(String, nullable=True)
    current_location = Column(String, nullable=True)
    years_of_experience = Column(Float, nullable=True, default=0.0)
    preferred_salary = Column(String, nullable=True)
    notice_period = Column(String, nullable=True)
    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class ResumeVersionModel(Base):
    """
    Tracks uploaded resume versions, file hashes, embedding status, and chunk counts.
    """
    __tablename__ = "resume_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_hash = Column(String, nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    is_active = Column(Boolean, nullable=False, default=True)
    upload_date = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    extracted_text_path = Column(String, nullable=True)
    embedding_status = Column(String, nullable=False, default="Pending") # Pending, Indexed, Failed
    last_indexed = Column(DateTime, nullable=True)
    chunk_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class SystemSettingsModel(Base):
    """
    KeyValue store for system configuration settings and encrypted parameters.
    """
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    setting_key = Column(String, unique=True, index=True, nullable=False)
    setting_value = Column(Text, nullable=True)
    is_encrypted = Column(Boolean, default=False, nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


