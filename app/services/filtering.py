from typing import List
from app.config import settings
from app.schemas.job import JobCreate
from app.utils.helpers import extract_experience
from app.logger import logger

class FilteringService:
    """
    Service responsible for filtering job listings against user configuration requirements.
    Filters by title keywords, location, skills, and experience limits.
    """
    def __init__(self):
        # Read from global settings config
        self.allowed_titles = settings.JOB_KEYWORDS
        self.preferred_locations = settings.PREFERRED_LOCATIONS
        self.max_experience = settings.MAX_EXPERIENCE
        self.enable_remote = settings.ENABLE_REMOTE
        self.required_skills = settings.REQUIRED_SKILLS

    def filter_job(self, job: JobCreate) -> bool:
        """
        Determines whether a single job listing meets all configuration filters.
        Returns True if the job is allowed, and False if it should be filtered out.
        """
        # 1. Job Title Filter (case-insensitive substring check)
        title_lower = job.title.lower()
        if not any(kw.lower() in title_lower for kw in self.allowed_titles):
            logger.debug(f"Filtered OUT: Title '{job.title}' does not match allowed keywords.")
            return False

        # 2. Location Filter
        # If remote is enabled and location contains 'remote', it passes location check
        location_lower = job.location.lower()
        location_allowed = False
        if self.enable_remote and "remote" in location_lower:
            location_allowed = True
        elif any(loc.lower() in location_lower for loc in self.preferred_locations):
            location_allowed = True
            
        if not location_allowed:
            logger.debug(f"Filtered OUT: Location '{job.location}' is not in preferred locations list.")
            return False

        # 3. Experience Filter
        experience_required = extract_experience(job.description)
        if experience_required is not None:
            if experience_required > self.max_experience:
                logger.debug(f"Filtered OUT: Experience requirement {experience_required} years exceeds MAX_EXPERIENCE ({self.max_experience}).")
                return False

        # 4. Skills (Keyword matching on title or description)
        desc_lower = job.description.lower()
        skills_matched = any(
            skill.lower() in desc_lower or skill.lower() in title_lower 
            for skill in self.required_skills
        )
        if not skills_matched:
            logger.debug(f"Filtered OUT: Job '{job.title}' does not contain any required skills keywords.")
            return False

        logger.debug(f"Filter PASSED: '{job.title}' at '{job.company}' ({job.location})")
        return True

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
