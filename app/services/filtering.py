from datetime import datetime, timezone, timedelta
from typing import List, Tuple
from app.config import settings
from app.schemas.job import JobCreate
from app.utils.helpers import extract_experience
from app.logger import logger
from app.monitoring.metrics import JOBS_FILTERED_TOTAL

class FilteringService:
    """
    Service responsible for filtering job listings against user configuration requirements.
    Filters by title keywords, location, skills, experience limits, blacklisted companies,
    ignored keywords, and job freshness.
    """
    def __init__(self):
        # Read from global settings config
        self.allowed_titles = settings.JOB_KEYWORDS
        self.preferred_locations = settings.PREFERRED_LOCATIONS
        self.max_experience = settings.MAX_EXPERIENCE
        self.enable_remote = settings.ENABLE_REMOTE
        self.required_skills = settings.REQUIRED_SKILLS
        self.blacklisted_companies = getattr(settings, "BLACKLISTED_COMPANIES", [])
        self.ignored_keywords = getattr(settings, "IGNORED_KEYWORDS", ["internship", "volunteer", "unpaid"])
        self.max_job_age_days = getattr(settings, "MAX_JOB_AGE_DAYS", 30)

    def filter_job(self, job: JobCreate) -> bool:
        """
        Determines whether a single job listing meets all configuration filters.
        Returns True if the job is allowed, and False if it should be filtered out.
        """
        passed, _ = self.filter_job_with_reason(job)
        return passed

    def filter_job_with_reason(self, job: JobCreate) -> Tuple[bool, str]:
        """
        Determines whether a single job listing meets all configuration filters.
        Returns tuple: (is_allowed: bool, exclusion_reason: str).
        """
        title_lower = job.title.lower()
        company_lower = job.company.lower()
        desc_lower = job.description.lower()

        # 1. Blacklisted Companies Filter
        if any(b.lower().strip() in company_lower for b in self.blacklisted_companies if b.strip()):
            JOBS_FILTERED_TOTAL.labels(reason="blacklisted_company").inc()
            logger.debug(f"Filtered OUT: Company '{job.company}' is blacklisted.")
            return False, "blacklisted_company"

        # 2. Ignored Keywords Filter (e.g. internship, volunteer)
        for ik in self.ignored_keywords:
            if ik.strip() and (ik.lower() in title_lower or ik.lower() in desc_lower):
                JOBS_FILTERED_TOTAL.labels(reason="ignored_keyword").inc()
                logger.debug(f"Filtered OUT: Job '{job.title}' contains ignored keyword '{ik}'.")
                return False, "ignored_keyword"

        # 3. Job Title Filter (case-insensitive substring check)
        if not any(kw.lower() in title_lower for kw in self.allowed_titles):
            JOBS_FILTERED_TOTAL.labels(reason="unmatched_title").inc()
            logger.debug(f"Filtered OUT: Title '{job.title}' does not match allowed keywords.")
            return False, "unmatched_title"

        # 4. Location & Remote Mode Filter
        location_lower = job.location.lower()
        location_allowed = False
        if self.enable_remote and ("remote" in location_lower or (job.remote_type and job.remote_type.lower() == "remote")):
            location_allowed = True
        elif any(loc.lower() in location_lower for loc in self.preferred_locations):
            location_allowed = True
            
        if not location_allowed:
            JOBS_FILTERED_TOTAL.labels(reason="unmatched_location").inc()
            logger.debug(f"Filtered OUT: Location '{job.location}' is not in preferred locations list.")
            return False, "unmatched_location"

        # 5. Experience Filter
        experience_required = extract_experience(job.description)
        if experience_required is not None and experience_required > self.max_experience:
            JOBS_FILTERED_TOTAL.labels(reason="exceeded_experience").inc()
            logger.debug(f"Filtered OUT: Experience requirement {experience_required} years exceeds MAX_EXPERIENCE ({self.max_experience}).")
            return False, "exceeded_experience"

        # 6. Skills (Keyword matching on title or description)
        skills_matched = any(
            skill.lower() in desc_lower or skill.lower() in title_lower 
            for skill in self.required_skills
        )
        if not skills_matched:
            JOBS_FILTERED_TOTAL.labels(reason="missing_required_skills").inc()
            logger.debug(f"Filtered OUT: Job '{job.title}' does not contain required skills keywords.")
            return False, "missing_required_skills"

        # 7. Job Freshness Filter
        if job.date_posted:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.max_job_age_days)
            job_posted = job.date_posted if job.date_posted.tzinfo else job.date_posted.replace(tzinfo=timezone.utc)
            if job_posted < cutoff_date:
                JOBS_FILTERED_TOTAL.labels(reason="stale_job").inc()
                logger.debug(f"Filtered OUT: Job '{job.title}' posted on {job.date_posted} exceeds age limit of {self.max_job_age_days} days.")
                return False, "stale_job"

        logger.debug(f"Filter PASSED: '{job.title}' at '{job.company}' ({job.location})")
        return True, "passed"

    def filter_jobs(self, jobs: List[JobCreate]) -> List[JobCreate]:
        """
        Filters a list of JobCreate models.
        Returns a new list containing only jobs that pass all filters.
        """
        filtered_list = []
        logger.info(f"Filtering service started. Processing {len(jobs)} jobs...")
        for job in jobs:
            if self.filter_job(job):
                filtered_list.append(job)
        logger.info(f"Filtering complete. Jobs passed: {len(filtered_list)} / {len(jobs)}. Filtered out: {len(jobs) - len(filtered_list)}")
        return filtered_list
