import requests
from datetime import datetime, timezone
from typing import List, Optional
from app.collectors.base import BaseCollector
from app.schemas.job import JobCreate
from app.config import settings
from app.logger import logger
from app.utils.helpers import clean_text

class RemotiveCollector(BaseCollector):
    """
    Collector for Remotive Remote Jobs API (https://remotive.com/api/remote-jobs).
    Fetches real software development, machine learning, and data engineering remote jobs.
    """
    def __init__(self, mock_mode: Optional[bool] = None):
        self.mock_mode = settings.MOCK_COLLECTOR if mock_mode is None else mock_mode
        self.api_url = "https://remotive.com/api/remote-jobs?limit=50"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json"
        }

    def collect(self) -> List[JobCreate]:
        logger.info("Collector started: RemotiveCollector")
        if self.mock_mode:
            logger.info("RemotiveCollector running in MOCK mode. Returning simulated jobs.")
            return self._get_mock_jobs()

        try:
            response = requests.get(self.api_url, headers=self.headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            job_items = data.get("jobs", [])
            jobs: List[JobCreate] = []

            for item in job_items:
                title = clean_text(item.get("title", ""))
                company = clean_text(item.get("company_name", ""))
                description = clean_text(item.get("description", ""))
                location = clean_text(item.get("candidate_required_location", "Remote")) or "Remote"
                url = item.get("url", "")
                
                pub_date_str = item.get("publication_date")
                date_posted = datetime.now(timezone.utc)
                if pub_date_str:
                    try:
                        date_posted = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
                    except Exception:
                        pass

                if title and company and description and url:
                    jobs.append(JobCreate(
                        title=title,
                        company=company,
                        location=location,
                        job_url=url,
                        description=description,
                        source="Remotive",
                        date_posted=date_posted
                    ))

            logger.info(f"RemotiveCollector: Collected {len(jobs)} live jobs.")
            return jobs
        except Exception as e:
            logger.error(f"RemotiveCollector API request failed: {e}. Falling back to mock jobs.")
            return self._get_mock_jobs()

    def _get_mock_jobs(self) -> List[JobCreate]:
        return [
            JobCreate(
                title="Senior ML & AI Backend Architect",
                company="Remotive Labs",
                location="Worldwide (Remote)",
                job_url="https://remotive.com/remote-jobs/software-dev/senior-ml-ai-backend-architect-101",
                description="Python, Machine Learning, Qdrant, PostgreSQL, FastAPI, LangGraph knowledge preferred.",
                source="Remotive",
                date_posted=datetime.now(timezone.utc)
            )
        ]
