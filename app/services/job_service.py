from typing import Dict, Any, List
from app.collectors.base import BaseCollector
from app.database.repository import JobRepository
from app.schemas.job import JobCreate
from app.logger import logger

class JobService:
    """
    Service layer coordinating collection, validation, deduplication, and database insertion.
    Uses Dependency Injection to receive repository and collector instances.
    """
    def __init__(self, repository: JobRepository, collector: BaseCollector):
        self.repository = repository
        self.collector = collector

    def sync_jobs(self) -> Dict[str, int]:
        """
        Runs the job collection pipeline.
        Fetches jobs, validates them, filters duplicates, stores new jobs, and returns statistics.
        Does not crash the entire process if an individual job fails to parse or insert.
        """
        stats = {
            "Collected": 0,
            "Inserted": 0,
            "Duplicates": 0,
            "Failed": 0
        }
        
        # 1. Fetch raw jobs from the collector
        logger.info("Starting job collection pipeline.")
        try:
            raw_jobs = self.collector.collect()
            stats["Collected"] = len(raw_jobs)
            logger.info(f"Jobs collected: {stats['Collected']} jobs found from source.")
        except Exception as e:
            logger.error(f"Failed to collect jobs: {e}", exc_info=True)
            stats["Failed"] += 1
            return stats

        # 2. Iterate through each collected job
        for job_data in raw_jobs:
            try:
                # Ensure the data conforms to the JobCreate schema
                # (If it's already a JobCreate instance, this validates it,
                # if it was a dictionary or raw structure, this validates and casts it)
                if not isinstance(job_data, JobCreate):
                    validated_job = JobCreate.model_validate(job_data)
                else:
                    validated_job = job_data
                
                # Check for duplication using job URL
                if self.repository.job_exists(validated_job.job_url):
                    stats["Duplicates"] += 1
                    logger.info(f"Duplicates skipped: '{validated_job.title}' from '{validated_job.company}' (URL already exists)")
                    continue
                
                # Insert job into database
                self.repository.insert_job(validated_job)
                stats["Inserted"] += 1
                
            except Exception as e:
                # Fault Tolerance: log the error and increment Failed counter, do not terminate pipeline
                stats["Failed"] += 1
                logger.error(f"Error processing individual job: {e}", exc_info=True)
                continue
                
        logger.info(
            f"Sync complete. Statistics - Collected: {stats['Collected']}, "
            f"Inserted: {stats['Inserted']}, Duplicates: {stats['Duplicates']}, "
            f"Failed: {stats['Failed']}"
        )
        return stats
