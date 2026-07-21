from typing import List, Dict, Any, Tuple
from app.database.repository import JobRepository, DuplicateJobError
from app.schemas.job import JobCreate
from app.logger import logger

class PersistenceAgent:
    """
    PersistenceAgent writes evaluated job structures to the SQLite database:
    - Inserts new job listings.
    - Saves match scores, recommendations, and reasoning.
    - Writes retrieval metadata (IDs, scores, and latency metrics) to SQL columns.
    """
    def __init__(self, repository: JobRepository):
        self.repository = repository

    def persist_jobs(self, ranked_jobs: List[Dict[str, Any]], retrieval_metrics: Dict[str, Dict[str, Any]], notification_records: List[Dict[str, Any]] = None, application_packages: List[Dict[str, Any]] = None) -> Tuple[int, int]:
        """
        Inserts new jobs and writes their evaluations to SQLite.
        Saves corresponding notification delivery logs.
        Returns: (inserted_count, duplicate_count)
        """
        logger.info(f"PersistenceAgent: Starting database write for {len(ranked_jobs)} jobs.")
        inserted = 0
        duplicates = 0
        
        # Build map of job URL to its corresponding notification status record
        record_map = {}
        if notification_records:
            for rec in notification_records:
                record_map[rec["job_url"]] = rec
        
        for job_payload in ranked_jobs:
            url = job_payload.get("job_url", "")
            
            try:
                # 1. Map fields back to JobCreate schema
                job_create = JobCreate.model_validate(job_payload)
                
                # Double check duplicates just in case
                db_job = self.repository.get_job_by_url(url)
                if not db_job:
                    if self.repository.job_exists(job_create.job_url, job_create.title, job_create.company, job_create.location):
                        duplicates += 1
                        logger.info(f"PersistenceAgent: Duplicate skip for '{job_create.title}' at '{job_payload.get('company')}'")
                        continue
                    # 2. Insert raw job details into SQLite
                    db_job = self.repository.insert_job(job_create)
                else:
                    if db_job.match_score is not None:
                        duplicates += 1
                        logger.info(f"PersistenceAgent: Duplicate skip (matching score exists) for '{job_create.title}'")
                        continue
                
                # 3. Consolidate evaluation + RAG metrics
                metrics = retrieval_metrics.get(url, {})
                evaluation_data = {
                    "match_score": job_payload.get("match_score"),
                    "should_apply": job_payload.get("should_apply"),
                    "priority": job_payload.get("priority"),
                    "summary": job_payload.get("summary"),
                    "strengths": job_payload.get("strengths"),
                    "missing_skills": job_payload.get("missing_skills"),
                    "learning_effort": job_payload.get("learning_effort"),
                    "confidence": job_payload.get("confidence"),
                    # Day 4 RAG metrics
                    "retrieved_chunk_ids": metrics.get("retrieved_chunk_ids"),
                    "retrieval_time": metrics.get("retrieval_time"),
                    "embedding_model": job_payload.get("embedding_model"),
                    "retrieval_score": metrics.get("retrieval_score")
                }
                
                # 4. Save evaluation and RAG metadata columns in SQLite
                self.repository.update_job_ai_evaluation(db_job.id, evaluation_data)
                inserted += 1
                
                # 5. Log corresponding notification history record for this new job
                rec = record_map.get(url)
                if rec:
                    from app.notifications.notification_repository import NotificationRepository
                    noti_repo = NotificationRepository(session_provider=self.repository.session_provider)
                    noti_repo.log_notification(
                        job_id=db_job.id,
                        channel=rec.get("channel", "email"),
                        status=rec.get("status", "skipped"),
                        sent_at=rec.get("sent_at"),
                        retry_count=rec.get("retry_count", 0),
                        error_message=rec.get("error_message")
                    )
                
            except DuplicateJobError:
                duplicates += 1
                logger.info(f"PersistenceAgent: Duplicate skip (DB trigger) for '{job_payload.get('title')}'")
                continue
            except Exception as e:
                logger.error(f"PersistenceAgent: Database write failed for job URL {url}: {e}", exc_info=True)
                continue
                
        logger.info(f"PersistenceAgent: Complete. Inserted: {inserted}, Duplicates: {duplicates}")
        return inserted, duplicates
