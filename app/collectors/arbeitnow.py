import requests
from datetime import datetime, timezone
from typing import List, Optional
from app.collectors.base import BaseCollector
from app.schemas.job import JobCreate
from app.config import settings
from app.logger import logger
from app.utils.helpers import clean_text

class ArbeitnowCollector(BaseCollector):
    """
    Collector for Arbeitnow open Job Board API (https://www.arbeitnow.com/api/job-board-api).
    Fetches real tech, developer, and data engineering job listings.
    """
    def __init__(self, mock_mode: Optional[bool] = None):
        self.mock_mode = settings.MOCK_COLLECTOR if mock_mode is None else mock_mode
        self.api_url = "https://www.arbeitnow.com/api/job-board-api"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json"
        }

    def collect(self) -> List[JobCreate]:
        logger.info("Collector started: ArbeitnowCollector")
        if self.mock_mode:
            logger.info("ArbeitnowCollector running in MOCK mode. Returning simulated jobs.")
            return self._get_mock_jobs()

        try:
            response = requests.get(self.api_url, headers=self.headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            job_items = data.get("data", [])
            jobs: List[JobCreate] = []

            for item in job_items:
                title = clean_text(item.get("title", ""))
                company = clean_text(item.get("company_name", ""))
                description = clean_text(item.get("description", ""))
                location = clean_text(item.get("location", "Remote")) or "Remote"
                url = item.get("url", "")
                
                # Check for remote flag
                if item.get("remote"):
                    location = f"{location} (Remote)" if location != "Remote" else "Remote"

                created_at_ts = item.get("created_at")
                if created_at_ts:
                    try:
                        date_posted = datetime.fromtimestamp(int(created_at_ts), tz=timezone.utc)
                    except Exception:
                        date_posted = datetime.now(timezone.utc)
                else:
                    date_posted = datetime.now(timezone.utc)

                if title and company and description and url:
                    jobs.append(JobCreate(
                        title=title,
                        company=company,
                        location=location,
                        job_url=url,
                        description=description,
                        source="Arbeitnow",
                        date_posted=date_posted
                    ))

            logger.info(f"ArbeitnowCollector: Collected {len(jobs)} live jobs.")
            return jobs
        except Exception as e:
            logger.error(f"ArbeitnowCollector API request failed: {e}. Falling back to mock jobs.")
            return self._get_mock_jobs()

    def _get_mock_jobs(self) -> List[JobCreate]:
        return [
            JobCreate(
                title="Full Stack Python AI Developer",
                company="Arbeit Tech",
                location="Remote",
                job_url="https://www.arbeitnow.com/jobs/companies/arbeit-tech/full-stack-python-ai-developer",
                description="Python, FastAPI, SQL, Docker, LLMs, and modern frontend experience required.",
                source="Arbeitnow",
                date_posted=datetime.now(timezone.utc)
            )
        ]
