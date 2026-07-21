import requests
from datetime import datetime, timezone
from typing import List, Optional
from app.collectors.base import BaseCollector
from app.schemas.job import JobCreate
from app.config import settings
from app.logger import logger
from app.utils.helpers import clean_text

class RemoteOKCollector(BaseCollector):
    """
    Collector for RemoteOK live API (https://remoteok.com/api).
    Fetches real remote tech, AI, software engineering, and data science jobs.
    """
    def __init__(self, mock_mode: Optional[bool] = None):
        self.mock_mode = settings.MOCK_COLLECTOR if mock_mode is None else mock_mode
        self.api_url = "https://remoteok.com/api"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json"
        }

    def collect(self) -> List[JobCreate]:
        logger.info("Collector started: RemoteOKCollector")
        if self.mock_mode:
            logger.info("RemoteOKCollector running in MOCK mode. Returning simulated jobs.")
            return self._get_mock_jobs()

        try:
            response = requests.get(self.api_url, headers=self.headers, timeout=15)
            response.raise_for_status()
            data = response.json()

            # First element in RemoteOK API response is legal metadata disclaimer object
            job_items = [item for item in data if isinstance(item, dict) and "position" in item]
            jobs: List[JobCreate] = []

            for item in job_items:
                title = clean_text(item.get("position", ""))
                company = clean_text(item.get("company", ""))
                description = clean_text(item.get("description", ""))
                location = clean_text(item.get("location", "Remote")) or "Remote"
                url = item.get("url") or f"https://remoteok.com/remote-jobs/{item.get('id')}"
                
                # Parse posting date
                epoch = item.get("date")
                if epoch:
                    try:
                        date_posted = datetime.fromtimestamp(int(epoch), tz=timezone.utc)
                    except Exception:
                        date_posted = datetime.now(timezone.utc)
                else:
                    date_posted = datetime.now(timezone.utc)

                if title and company and description:
                    jobs.append(JobCreate(
                        title=title,
                        company=company,
                        location=location,
                        job_url=url,
                        description=description,
                        source="RemoteOK",
                        date_posted=date_posted
                    ))

            logger.info(f"RemoteOKCollector: Collected {len(jobs)} live jobs.")
            return jobs
        except Exception as e:
            logger.error(f"RemoteOKCollector API request failed: {e}. Falling back to mock jobs.")
            return self._get_mock_jobs()

    def _get_mock_jobs(self) -> List[JobCreate]:
        return [
            JobCreate(
                title="Remote AI Systems Engineer",
                company="Nexus AI",
                location="Remote",
                job_url="https://remoteok.com/remote-jobs/nexus-ai-systems-engineer",
                description="Looking for Python, LLMs, LangChain, PyTorch, and Qdrant experience for AI systems.",
                source="RemoteOK",
                date_posted=datetime.now(timezone.utc)
            )
        ]
