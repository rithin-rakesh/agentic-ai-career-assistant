from typing import List, Dict, Any
from app.services.filtering import FilteringService
from app.database.repository import JobRepository
from app.schemas.job import JobCreate
from app.logger import logger

class FilteringAgent:
    """
    FilteringAgent processes raw collected job listings:
    - Runs duplicate check filters against SQLite records.
    - Applies keyword matching on titles and skills.
    - Limits experience thresholds.
    - Resolves geographic location criteria.
    """
    def __init__(self, filtering_service: FilteringService, repository: JobRepository):
        self.filtering_service = filtering_service
        self.repository = repository

    def filter_jobs(self, raw_jobs: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], int, int]:
        """
        Filters out ineligible listings and database duplicate matches.
        Returns: (filtered_jobs_list, rule_filtered_count, duplicate_count)
        """
        logger.info(f"FilteringAgent: Starting rules verification for {len(raw_jobs)} collected jobs.")
        filtered_list = []
        duplicate_count = 0
        rule_filtered_count = 0
        
        for job_dict in raw_jobs:
            try:
                # 1. Transform raw dict to Pydantic validator model
                job_create = JobCreate.model_validate(job_dict)
                
                # 2. Run rule-based title/skills/location filters
                if not self.filtering_service.filter_job(job_create):
                    rule_filtered_count += 1
                    continue
                    
                # 3. Query SQLite for duplicate detection (compound keys or URL)
                if self.repository.job_exists(
                    url=job_create.job_url,
                    title=job_create.title,
                    company=job_create.company,
                    location=job_create.location
                ):
                    duplicate_count += 1
                    logger.debug(f"FilteringAgent: Skipping duplicate listing '{job_create.title}' at '{job_create.company}'")
                    continue
                    
                # Store passed job back as dictionary for GraphState
                filtered_list.append(job_create.model_dump())
                
            except Exception as e:
                logger.error(f"FilteringAgent: Validation error on job payload: {e}. Payload: {job_dict}")
                continue
                
        logger.info(
            f"FilteringAgent: Filtering complete. Passed: {len(filtered_list)}, "
            f"Rule Excluded: {rule_filtered_count}, Duplicates: {duplicate_count}"
        )
        return filtered_list, rule_filtered_count, duplicate_count
