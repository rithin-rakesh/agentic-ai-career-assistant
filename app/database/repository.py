import json
from datetime import datetime, timezone, time
from typing import List, Optional, Any, Dict
from sqlalchemy import select, func, or_, text
from sqlalchemy.orm import Session
from app.database.database import engine as global_engine, get_db_session
from app.database.models import Base, JobModel
from app.schemas.job import Job, JobCreate
from app.logger import logger

class DuplicateJobError(Exception):
    """
    Raised when trying to insert a job that already exists in the database.
    """
    pass

class JobRepository:
    """
    Repository class encapsulating database access patterns.
    Hides SQLAlchemy specifics from the upper layers of the application.
    Supports Dependency Injection by accepting a session provider callback.
    """
    def __init__(self, session_provider=None):
        self.session_provider = session_provider or get_db_session

    def create_database(self) -> None:
        """
        Creates all tables defined in models if they do not already exist.
        Performs incremental columns migration to add AI and RAG fields if table already exists.
        Extracts the bound engine dynamically from the session provider to ensure
        correctness during testing and isolation.
        """
        try:
            # Get the dynamically bound engine from the session provider
            with self.session_provider() as session:
                db_engine = session.bind
            
            if db_engine is None:
                db_engine = global_engine

            # 1. Create tables if they do not exist
            from app.notifications.notification_models import NotificationModel
            from app.database.models import (
                ApplicationModel, ExecutionLogModel, FeedbackEventModel,
                PreferenceModel, CompanyProfileModel, CareerDecisionModel,
                LearningMetricModel, RecommendationHistoryModel,
                CandidateProfileModel, ResumeVersionModel
            )
            Base.metadata.create_all(bind=db_engine)
            
            # 2. Run column migration checks for existing tables (SQLite specific)
            from sqlalchemy import inspect
            inspector = inspect(db_engine)
            
            if "jobs" in inspector.get_table_names():
                existing_columns = {col["name"] for col in inspector.get_columns("jobs")}
                
                # Check for new columns and execute dynamic ALTER TABLE statements (Days 3 & 4)
                new_columns = {
                    "match_score": "INTEGER NULL",
                    "should_apply": "BOOLEAN NULL",
                    "priority": "VARCHAR NULL",
                    "summary": "TEXT NULL",
                    "strengths": "TEXT NULL",
                    "missing_skills": "TEXT NULL",
                    "learning_effort": "VARCHAR NULL",
                    "confidence": "FLOAT NULL",
                    "analysis_timestamp": "DATETIME NULL",
                    # RAG metadata (Day 4)
                    "retrieved_chunk_ids": "TEXT NULL",
                    "retrieval_time": "FLOAT NULL",
                    "embedding_model": "VARCHAR NULL",
                    "retrieval_score": "FLOAT NULL",
                    # Phase 2.4 Normalization & Deduplication fields
                    "remote_type": "VARCHAR NULL",
                    "employment_type": "VARCHAR NULL",
                    "salary_range": "VARCHAR NULL",
                    "experience_level": "VARCHAR NULL",
                    "apply_url": "VARCHAR NULL",
                    "company_url": "VARCHAR NULL",
                    "collected_timestamp": "DATETIME NULL",
                    "content_hash": "VARCHAR NULL",
                    "raw_metadata": "TEXT NULL"
                }
                
                with self.session_provider() as session:
                    for col_name, col_type in new_columns.items():
                        if col_name not in existing_columns:
                            logger.info(f"Database migration: Adding missing column '{col_name}' to 'jobs' table.")
                            session.execute(text(f"ALTER TABLE jobs ADD COLUMN {col_name} {col_type}"))
                            
            logger.info("Database initialized successfully.")
        except Exception as e:
            logger.error(f"Error during database initialization: {e}", exc_info=True)
            raise

    def insert_job(self, job_in: JobCreate) -> Job:
        """
        Inserts a validated JobCreate schema into the database.
        Raises DuplicateJobError if the job already exists (by URL, content hash, or company+title).
        """
        if self.job_exists(
            url=job_in.job_url,
            title=job_in.title,
            company=job_in.company,
            location=job_in.location,
            content_hash=getattr(job_in, "content_hash", None)
        ):
            raise DuplicateJobError(
                f"Job already exists in database: Title='{job_in.title}', Company='{job_in.company}', Location='{job_in.location}', URL='{job_in.job_url}'"
            )

        db_job = JobModel(
            title=job_in.title,
            company=job_in.company,
            location=job_in.location,
            job_url=job_in.job_url,
            description=job_in.description,
            source=job_in.source,
            date_posted=job_in.date_posted,
            remote_type=getattr(job_in, "remote_type", None),
            employment_type=getattr(job_in, "employment_type", None),
            salary_range=getattr(job_in, "salary_range", None),
            experience_level=getattr(job_in, "experience_level", None),
            apply_url=getattr(job_in, "apply_url", None),
            company_url=getattr(job_in, "company_url", None),
            collected_timestamp=getattr(job_in, "collected_timestamp", None),
            content_hash=getattr(job_in, "content_hash", None),
            raw_metadata=getattr(job_in, "raw_metadata", None)
        )
        
        try:
            with self.session_provider() as session:
                session.add(db_job)
                session.flush()
                session.refresh(db_job)
                domain_job = Job.model_validate(db_job)
                
            logger.info(f"Database insertion successful: '{domain_job.title}' at '{domain_job.company}'")
            return domain_job
        except Exception as e:
            logger.error(f"Failed to insert job with URL {job_in.job_url}: {e}", exc_info=True)
            raise

    def job_exists(
        self,
        url: str,
        title: Optional[str] = None,
        company: Optional[str] = None,
        location: Optional[str] = None,
        content_hash: Optional[str] = None
    ) -> bool:
        """
        Queries the database to check if a job already exists.
        Multi-stage deduplication check:
        1. Exact job URL match.
        2. SHA-256 content_hash match.
        3. Normalized case & whitespace company + title match.
        """
        from app.monitoring.metrics import DUPLICATE_JOBS_TOTAL
        try:
            with self.session_provider() as session:
                # Check 1: Match by exact URL
                url_query = select(JobModel.id).where(JobModel.job_url == url)
                if session.execute(url_query).scalar_one_or_none() is not None:
                    DUPLICATE_JOBS_TOTAL.labels(reason="exact_url").inc()
                    return True

                # Check 2: Match by SHA-256 content_hash
                if content_hash:
                    hash_query = select(JobModel.id).where(JobModel.content_hash == content_hash)
                    if session.execute(hash_query).scalar_one_or_none() is not None:
                        DUPLICATE_JOBS_TOTAL.labels(reason="content_hash").inc()
                        return True

                # Check 3: Normalized case & whitespace company + title match
                if title and company:
                    norm_title = title.lower().strip()
                    norm_company = company.lower().strip()
                    compound_query = select(JobModel.id).where(
                        func.lower(JobModel.title) == norm_title,
                        func.lower(JobModel.company) == norm_company
                    )
                    if session.execute(compound_query).scalar_one_or_none() is not None:
                        DUPLICATE_JOBS_TOTAL.labels(reason="normalized_title_company").inc()
                        return True
                        
                return False
        except Exception as e:
            logger.error(f"Database query error when checking duplicate for URL {url}: {e}", exc_info=True)
            raise

    def get_all_jobs(self) -> List[Job]:
        """
        Retrieves all jobs stored in the database.
        Returns a list of Job Pydantic schemas.
        """
        try:
            with self.session_provider() as session:
                query = select(JobModel)
                db_jobs = session.execute(query).scalars().all()
                return [Job.model_validate(db_job) for db_job in db_jobs]
        except Exception as e:
            logger.error(f"Error fetching all jobs from database: {e}", exc_info=True)
            raise

    def count_jobs(self) -> int:
        """
        Returns the total count of jobs in the database.
        """
        try:
            with self.session_provider() as session:
                query = select(func.count()).select_from(JobModel)
                count = session.execute(query).scalar() or 0
                return count
        except Exception as e:
            logger.error(f"Error counting database job records: {e}", exc_info=True)
            raise

    def update_job_ai_evaluation(self, job_id: int, eval_data: dict) -> None:
        """
        Updates a job record with AI evaluation details and RAG search metadata.
        Serializes List[str] fields to JSON strings for SQLite TEXT columns compatibility.
        """
        from datetime import datetime, timezone
        try:
            with self.session_provider() as session:
                db_job = session.get(JobModel, job_id)
                if not db_job:
                    raise ValueError(f"Job ID {job_id} not found in database.")
                
                db_job.match_score = eval_data.get("match_score")
                db_job.should_apply = eval_data.get("should_apply")
                db_job.priority = eval_data.get("priority")
                db_job.summary = eval_data.get("summary")
                
                strengths = eval_data.get("strengths") or []
                db_job.strengths = json.dumps(strengths)
                
                missing = eval_data.get("missing_skills") or []
                db_job.missing_skills = json.dumps(missing)
                
                db_job.learning_effort = eval_data.get("learning_effort")
                db_job.confidence = eval_data.get("confidence")
                db_job.analysis_timestamp = datetime.now(timezone.utc)
                
                # RAG metadata (Day 4)
                chunks = eval_data.get("retrieved_chunk_ids") or []
                db_job.retrieved_chunk_ids = json.dumps(chunks)
                db_job.retrieval_time = eval_data.get("retrieval_time")
                db_job.embedding_model = eval_data.get("embedding_model")
                db_job.retrieval_score = eval_data.get("retrieval_score")
                
            logger.info(f"AI evaluation and RAG metadata updated successfully for Job ID {job_id}.")
        except Exception as e:
            logger.error(f"Failed to update AI evaluation and RAG metadata for Job ID {job_id}: {e}", exc_info=True)
            raise

    def get_unevaluated_jobs(self) -> List[Job]:
        """
        Retrieves all jobs that have not yet been evaluated by the AI Matching Agent
        (where match_score is NULL).
        """
        try:
            with self.session_provider() as session:
                query = select(JobModel).where(JobModel.match_score == None)
                db_jobs = session.execute(query).scalars().all()
                return [Job.model_validate(db_job) for db_job in db_jobs]
        except Exception as e:
            logger.error(f"Failed to fetch unevaluated jobs: {e}", exc_info=True)
            raise

    def get_job_by_url(self, url: str) -> Optional[Job]:
        """
        Retrieves a job record matching the specified URL.
        """
        try:
            with self.session_provider() as session:
                query = select(JobModel).where(JobModel.job_url == url)
                db_job = session.execute(query).scalars().first()
                if db_job:
                    return Job.model_validate(db_job)
                return None
        except Exception as e:
            logger.error(f"Failed to fetch job by URL {url}: {e}", exc_info=True)
            return None

    def create_application(self, job_id: int, company: str, position: str, status: str = "Draft", resume_path: str = None, cover_letter_path: str = None) -> Any:
        """
        Creates and inserts a new job application preparation record in SQLite.
        """
        from app.database.models import ApplicationModel
        from app.schemas.job import Application
        db_app = ApplicationModel(
            job_id=job_id,
            company=company,
            position=position,
            status=status,
            resume_path=resume_path,
            cover_letter_path=cover_letter_path
        )
        try:
            with self.session_provider() as session:
                session.add(db_app)
                session.flush()
                session.refresh(db_app)
                domain_app = Application.model_validate(db_app)
                logger.info(f"Database: Logged Application '{position}' at '{company}' (Job ID: {job_id}) with status '{status}'")
                return domain_app
        except Exception as e:
            logger.error(f"Failed to write application record for Job ID {job_id}: {e}", exc_info=True)
            raise

    def get_application_by_job_id(self, job_id: int) -> Optional[Any]:
        """
        Retrieves the application tracking record associated with a job ID.
        """
        from app.database.models import ApplicationModel
        from app.schemas.job import Application
        try:
            with self.session_provider() as session:
                query = select(ApplicationModel).where(ApplicationModel.job_id == job_id)
                db_app = session.execute(query).scalar_one_or_none()
                if db_app:
                    return Application.model_validate(db_app)
                return None
        except Exception as e:
            logger.error(f"Failed to fetch application for Job ID {job_id}: {e}", exc_info=True)
            return None

    def update_application_status(self, app_id: int, status: str, applied_at=None) -> None:
        """
        Updates the execution status of an application package.
        """
        from app.database.models import ApplicationModel
        try:
            with self.session_provider() as session:
                query = select(ApplicationModel).where(ApplicationModel.id == app_id)
                db_app = session.execute(query).scalar_one()
                db_app.status = status
                if applied_at:
                    db_app.applied_at = applied_at
                logger.info(f"Database: Updated Application ID {app_id} status to '{status}'")
        except Exception as e:
            logger.error(f"Failed to update status for Application ID {app_id}: {e}", exc_info=True)
            raise

    def log_node_execution(self, node_name: str, start_time: Any, end_time: Any, status: str, error_message: str = None, token_usage: int = 0) -> None:
        """
        Logs a LangGraph node execution performance metrics in execution_logs table.
        """
        from app.database.models import ExecutionLogModel
        duration = (end_time - start_time).total_seconds()
        log_rec = ExecutionLogModel(
            node_name=node_name,
            start_time=start_time,
            end_time=end_time,
            duration=duration,
            status=status,
            error_message=error_message,
            token_usage=token_usage
        )
        try:
            with self.session_provider() as session:
                session.add(log_rec)
                logger.info(f"Observability: Logged execution for '{node_name}' ({status}) - {duration:.3f}s")
        except Exception as e:
            logger.error(f"Failed to log execution for node {node_name}: {e}", exc_info=True)

    def get_execution_logs(self, limit: int = 50) -> List[Any]:
        """
        Retrieves the latest execution logs.
        """
        from app.database.models import ExecutionLogModel
        try:
            with self.session_provider() as session:
                query = select(ExecutionLogModel).order_by(ExecutionLogModel.created_at.desc()).limit(limit)
                db_logs = session.execute(query).scalars().all()
                return [
                    {
                        "id": log.id,
                        "node_name": log.node_name,
                        "start_time": log.start_time,
                        "end_time": log.end_time,
                        "duration": log.duration,
                        "status": log.status,
                        "error_message": log.error_message,
                        "token_usage": log.token_usage,
                        "created_at": log.created_at
                    }
                    for log in db_logs
                ]
        except Exception as e:
            logger.error(f"Failed to fetch execution logs: {e}", exc_info=True)
            return []

    def log_feedback_event(self, event_type: str, job_url: Optional[str] = None, application_id: Optional[int] = None, payload: Optional[dict] = None) -> Any:
        """
        Logs a user or system interaction event in feedback_events table.
        """
        from app.database.models import FeedbackEventModel
        try:
            with self.session_provider() as session:
                job_id = None
                if job_url:
                    db_job = self.get_job_by_url(job_url)
                    if db_job:
                        job_id = db_job.id
                
                # Check if application_id is provided and we can get job_id from it
                if application_id and not job_id:
                    from app.database.models import ApplicationModel
                    app_rec = session.get(ApplicationModel, application_id)
                    if app_rec:
                        job_id = app_rec.job_id

                event = FeedbackEventModel(
                    job_id=job_id,
                    application_id=application_id,
                    event_type=event_type,
                    payload=json.dumps(payload) if payload else None
                )
                session.add(event)
                session.commit()
                logger.info(f"Feedback Event Logged: {event_type} (Job ID: {job_id})")
                return event
        except Exception as e:
            logger.error(f"Failed to log feedback event: {e}", exc_info=True)
            return None

    def get_feedback_events(self, limit: int = 100) -> List[Any]:
        """
        Retrieves recent feedback events.
        """
        from app.database.models import FeedbackEventModel
        try:
            with self.session_provider() as session:
                query = select(FeedbackEventModel).order_by(FeedbackEventModel.created_at.desc()).limit(limit)
                events = session.execute(query).scalars().all()
                return events
        except Exception as e:
            logger.error(f"Failed to retrieve feedback events: {e}", exc_info=True)
            return []

    def update_preference_score(self, category: str, name: str, score: float) -> Any:
        """
        Inserts or updates a candidate preference score.
        """
        from app.database.models import PreferenceModel
        try:
            with self.session_provider() as session:
                query = select(PreferenceModel).where(
                    PreferenceModel.category == category,
                    PreferenceModel.name == name
                )
                pref = session.execute(query).scalars().first()
                if pref:
                    pref.score = score
                else:
                    pref = PreferenceModel(category=category, name=name, score=score)
                    session.add(pref)
                session.commit()
                return pref
        except Exception as e:
            logger.error(f"Failed to update preference score: {e}", exc_info=True)
            return None

    def get_all_preferences(self) -> List[Any]:
        """
        Retrieves all preference weights.
        """
        from app.database.models import PreferenceModel
        try:
            with self.session_provider() as session:
                query = select(PreferenceModel).order_by(PreferenceModel.score.desc())
                return session.execute(query).scalars().all()
        except Exception as e:
            logger.error(f"Failed to fetch preference scores: {e}", exc_info=True)
            return []

    def update_company_profile(self, name: str, applied_inc: int = 0, rejected_inc: int = 0, interview_inc: int = 0, offer_inc: int = 0, status: Optional[str] = None) -> Any:
        """
        Updates aggregated intelligence statistics for a specific company.
        """
        from app.database.models import CompanyProfileModel
        try:
            with self.session_provider() as session:
                query = select(CompanyProfileModel).where(CompanyProfileModel.name == name)
                profile = session.execute(query).scalars().first()
                if not profile:
                    profile = CompanyProfileModel(
                        name=name,
                        status=status or "Neutral",
                        applied_count=applied_inc,
                        rejected_count=rejected_inc,
                        interview_count=interview_inc,
                        offer_count=offer_inc
                    )
                    session.add(profile)
                else:
                    profile.applied_count += applied_inc
                    profile.rejected_count += rejected_inc
                    profile.interview_count += interview_inc
                    profile.offer_count += offer_inc
                    if status:
                        profile.status = status

                # Calculate success rate: interviews/applied, or offers/applied
                # Here we do success_rate = (interview_count / applied_count) * 100
                if profile.applied_count > 0:
                    profile.success_rate = round((profile.interview_count / profile.applied_count) * 100, 2)
                else:
                    profile.success_rate = 0.0

                session.commit()
                return profile
        except Exception as e:
            logger.error(f"Failed to update company profile for {name}: {e}", exc_info=True)
            return None

    def get_company_profiles(self) -> List[Any]:
        """
        Retrieves all company intelligence logs.
        """
        from app.database.models import CompanyProfileModel
        try:
            with self.session_provider() as session:
                query = select(CompanyProfileModel).order_by(CompanyProfileModel.success_rate.desc())
                return session.execute(query).scalars().all()
        except Exception as e:
            logger.error(f"Failed to fetch company profiles: {e}", exc_info=True)
            return []

    def save_career_decision(self, job_id: int, recommendation: str, confidence: float, priority: str, estimated_interview_probability: str, career_growth: str, salary_competitiveness: str, learning_effort: str, resume_changes_required: bool, cover_letter_required: bool, estimated_application_time: Optional[str] = None, reasoning: Optional[List[str]] = None, missing_skills: Optional[List[str]] = None) -> Any:
        """
        Saves or updates strategic decision recommendations from LLM evaluation.
        """
        from app.database.models import CareerDecisionModel
        try:
            with self.session_provider() as session:
                query = select(CareerDecisionModel).where(CareerDecisionModel.job_id == job_id)
                decision = session.execute(query).scalars().first()
                
                reasoning_str = json.dumps(reasoning) if reasoning else None
                missing_skills_str = json.dumps(missing_skills) if missing_skills else None

                if decision:
                    decision.recommendation = recommendation
                    decision.confidence = confidence
                    decision.priority = priority
                    decision.estimated_interview_probability = estimated_interview_probability
                    decision.career_growth = career_growth
                    decision.salary_competitiveness = salary_competitiveness
                    decision.learning_effort = learning_effort
                    decision.resume_changes_required = resume_changes_required
                    decision.cover_letter_required = cover_letter_required
                    decision.estimated_application_time = estimated_application_time
                    decision.reasoning = reasoning_str
                    decision.missing_skills = missing_skills_str
                else:
                    decision = CareerDecisionModel(
                        job_id=job_id,
                        recommendation=recommendation,
                        confidence=confidence,
                        priority=priority,
                        estimated_interview_probability=estimated_interview_probability,
                        career_growth=career_growth,
                        salary_competitiveness=salary_competitiveness,
                        learning_effort=learning_effort,
                        resume_changes_required=resume_changes_required,
                        cover_letter_required=cover_letter_required,
                        estimated_application_time=estimated_application_time,
                        reasoning=reasoning_str,
                        missing_skills=missing_skills_str
                    )
                    session.add(decision)
                
                session.commit()
                return decision
        except Exception as e:
            logger.error(f"Failed to save career decision for Job ID {job_id}: {e}", exc_info=True)
            return None

    def get_career_decision(self, job_id: int) -> Optional[Dict[str, Any]]:
        """
        Fetches strategic career strategies for a specific job ID as a detached dictionary.
        """
        from app.database.models import CareerDecisionModel
        try:
            with self.session_provider() as session:
                query = select(CareerDecisionModel).where(CareerDecisionModel.job_id == job_id)
                decision = session.execute(query).scalars().first()
                if decision:
                    return {
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
                        "missing_skills": json.loads(decision.missing_skills) if decision.missing_skills else []
                    }
                return None
        except Exception as e:
            logger.error(f"Failed to fetch career decision for Job ID {job_id}: {e}", exc_info=True)
            return None

    def log_recommendation_history(self, job_id: int, scores: dict, reason: Optional[List[str]] = None) -> Any:
        """
        Logs a scoring record history in recommendation_history.
        """
        from app.database.models import RecommendationHistoryModel
        try:
            with self.session_provider() as session:
                rec = RecommendationHistoryModel(
                    job_id=job_id,
                    llm_match_score=scores.get("llm_match", 0.0),
                    behavior_score=scores.get("behavior", 0.0),
                    company_preference_score=scores.get("company_pref", 0.0),
                    location_preference_score=scores.get("location_pref", 0.0),
                    technology_preference_score=scores.get("technology_pref", 0.0),
                    salary_match_score=scores.get("salary_match", 0.0),
                    growth_score=scores.get("growth", 0.0),
                    risk_score=scores.get("risk", 0.0),
                    final_score=scores.get("final_score", 0.0),
                    recommendation_reason=json.dumps(reason) if reason else None
                )
                session.add(rec)
                session.commit()
                return rec
        except Exception as e:
            logger.error(f"Failed to log recommendation score history: {e}", exc_info=True)
            return None

    def get_learning_metrics(self) -> List[Any]:
        """
        Retrieves recorded weekly self-improvement statistics logs.
        """
        from app.database.models import LearningMetricModel
        try:
            with self.session_provider() as session:
                query = select(LearningMetricModel).order_by(LearningMetricModel.metric_date.desc()).limit(30)
                return session.execute(query).scalars().all()
        except Exception as e:
            logger.error(f"Failed to retrieve learning metrics: {e}", exc_info=True)
            return []

    def update_learning_metrics(self, accepted_delta: int = 0, ignored_delta: int = 0, interview_conv: Optional[float] = None, offer_conv: Optional[float] = None) -> Any:
        """
        Updates or appends the metrics log records for the current day.
        """
        from app.database.models import LearningMetricModel
        try:
            with self.session_provider() as session:
                # Find today's metric record (truncate time to start of day)
                today_start = datetime.combine(datetime.now(timezone.utc).date(), time.min).replace(tzinfo=timezone.utc)
                query = select(LearningMetricModel).where(LearningMetricModel.metric_date >= today_start)
                metric = session.execute(query).scalars().first()
                
                if not metric:
                    metric = LearningMetricModel(
                        metric_date=datetime.now(timezone.utc),
                        accepted_recommendations=accepted_delta,
                        ignored_recommendations=ignored_delta,
                        interview_conversion_rate=interview_conv or 0.0,
                        offer_conversion_rate=offer_conv or 0.0
                    )
                    session.add(metric)
                else:
                    metric.accepted_recommendations += accepted_delta
                    metric.ignored_recommendations += ignored_delta
                    if interview_conv is not None:
                        metric.interview_conversion_rate = interview_conv
                    if offer_conv is not None:
                        metric.offer_conversion_rate = offer_conv
                
                session.commit()
                return metric
        except Exception as e:
            logger.error(f"Failed to update learning metrics: {e}", exc_info=True)
            return None

    def get_candidate_profile(self) -> Optional[Any]:
        """
        Retrieves candidate personal profile details.
        """
        from app.database.models import CandidateProfileModel
        from app.schemas.job import CandidateProfile
        try:
            with self.session_provider() as session:
                query = select(CandidateProfileModel).order_by(CandidateProfileModel.id.asc())
                profile = session.execute(query).scalars().first()
                return CandidateProfile.model_validate(profile) if profile else None
        except Exception as e:
            logger.error(f"Failed to get candidate profile: {e}", exc_info=True)
            return None

    def update_candidate_profile(self, **kwargs) -> Any:
        """
        Updates or creates candidate personal profile details.
        """
        from app.database.models import CandidateProfileModel
        from app.schemas.job import CandidateProfile
        from datetime import datetime, timezone
        try:
            with self.session_provider() as session:
                query = select(CandidateProfileModel).order_by(CandidateProfileModel.id.asc())
                profile = session.execute(query).scalars().first()
                if not profile:
                    profile = CandidateProfileModel(**kwargs)
                    session.add(profile)
                else:
                    for key, val in kwargs.items():
                        if hasattr(profile, key) and val is not None:
                            setattr(profile, key, val)
                    profile.last_updated = datetime.now(timezone.utc)
                session.commit()
                return CandidateProfile.model_validate(profile)
        except Exception as e:
            logger.error(f"Failed to update candidate profile: {e}", exc_info=True)
            return None

    def get_active_resume_version(self) -> Optional[Any]:
        """
        Retrieves active resume version metadata.
        """
        from app.database.models import ResumeVersionModel
        from app.schemas.job import ResumeVersion
        try:
            with self.session_provider() as session:
                query = select(ResumeVersionModel).where(ResumeVersionModel.is_active == True).order_by(ResumeVersionModel.version.desc())
                ver = session.execute(query).scalars().first()
                return ResumeVersion.model_validate(ver) if ver else None
        except Exception as e:
            logger.error(f"Failed to get active resume version: {e}", exc_info=True)
            return None

    def get_all_resume_versions(self) -> List[Any]:
        """
        Retrieves history of all uploaded resume versions.
        """
        from app.database.models import ResumeVersionModel
        from app.schemas.job import ResumeVersion
        try:
            with self.session_provider() as session:
                query = select(ResumeVersionModel).order_by(ResumeVersionModel.version.desc())
                vers = session.execute(query).scalars().all()
                return [ResumeVersion.model_validate(v) for v in vers]
        except Exception as e:
            logger.error(f"Failed to get resume versions: {e}", exc_info=True)
            return []

    def create_resume_version(self, filename: str, file_path: str, file_hash: str, extracted_text_path: str = None, chunk_count: int = 0, embedding_status: str = "Indexed") -> Any:
        """
        Archives previous resume versions and creates a new active version.
        """
        from app.database.models import ResumeVersionModel
        from app.schemas.job import ResumeVersion
        from datetime import datetime, timezone
        try:
            with self.session_provider() as session:
                # 1. Archive previous active versions
                query_active = select(ResumeVersionModel).where(ResumeVersionModel.is_active == True)
                actives = session.execute(query_active).scalars().all()
                for prev in actives:
                    prev.is_active = False

                # 2. Get next version number
                max_ver_query = select(func.max(ResumeVersionModel.version))
                max_ver = session.execute(max_ver_query).scalar() or 0
                new_version = max_ver + 1

                now = datetime.now(timezone.utc)
                new_resume_version = ResumeVersionModel(
                    filename=filename,
                    file_path=file_path,
                    file_hash=file_hash,
                    version=new_version,
                    is_active=True,
                    upload_date=now,
                    extracted_text_path=extracted_text_path,
                    embedding_status=embedding_status,
                    last_indexed=now,
                    chunk_count=chunk_count,
                    created_at=now
                )
                session.add(new_resume_version)
                session.commit()
                return ResumeVersion.model_validate(new_resume_version)
        except Exception as e:
            logger.error(f"Failed to create resume version: {e}", exc_info=True)
            return None


