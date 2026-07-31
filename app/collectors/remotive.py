import time
import json
import requests
from datetime import datetime, timezone
from typing import List, Optional
from app.collectors.base import BaseCollector
from app.schemas.job import JobCreate
from app.config import settings
from app.logger import logger
from app.utils.helpers import clean_text
from app.monitoring.metrics import COLLECTOR_REQUESTS_TOTAL, COLLECTOR_LATENCY_SECONDS

class RemotiveCollector(BaseCollector):
    """
    Collector for Remotive Remote Jobs API (https://remotive.com/api/remote-jobs).
    Includes retry logic, exponential backoff, response validation, latency tracking,
    and schema normalization.
    """
    def __init__(self, mock_mode: Optional[bool] = None, max_retries: int = 3, timeout: int = 15):
        self.mock_mode = settings.MOCK_COLLECTOR if mock_mode is None else mock_mode
        self.api_url = "https://remotive.com/api/remote-jobs?limit=50"
        self.max_retries = max_retries
        self.timeout = timeout
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json"
        }

    def collect(self) -> List[JobCreate]:
        collector_name = "RemotiveCollector"
        logger.info(f"Collector started: {collector_name}")
        
        if self.mock_mode:
            logger.info(f"{collector_name} running in MOCK mode. Returning simulated jobs.")
            COLLECTOR_REQUESTS_TOTAL.labels(collector=collector_name, status="mock").inc()
            return self._get_mock_jobs()

        start_time = time.perf_counter()
        data = None
        last_exception = None

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"{collector_name}: Attempt {attempt}/{self.max_retries} requesting {self.api_url}")
                response = requests.get(self.api_url, headers=self.headers, timeout=self.timeout)
                response.raise_for_status()
                data = response.json()
                
                # Response validation
                if not isinstance(data, dict) or "jobs" not in data:
                    raise ValueError(f"{collector_name}: Expected JSON dict with 'jobs' array, got {type(data)}")
                
                COLLECTOR_REQUESTS_TOTAL.labels(collector=collector_name, status="success").inc()
                logger.info(f"{collector_name}: HTTP request succeeded on attempt {attempt}.")
                break
            except Exception as e:
                last_exception = e
                logger.warning(f"{collector_name}: Attempt {attempt} failed: {e}")
                if attempt < self.max_retries:
                    backoff = 2 ** attempt
                    logger.info(f"{collector_name}: Waiting {backoff}s before retry...")
                    time.sleep(backoff)

        latency = time.perf_counter() - start_time
        COLLECTOR_LATENCY_SECONDS.labels(collector=collector_name).observe(latency)
        logger.info(f"{collector_name}: Latency: {latency:.3f}s")

        if data is None:
            COLLECTOR_REQUESTS_TOTAL.labels(collector=collector_name, status="failure").inc()
            logger.error(f"{collector_name}: All {self.max_retries} attempts failed: {last_exception}. Falling back to mock jobs.")
            return self._get_mock_jobs()

        jobs: List[JobCreate] = []
        job_items = data.get("jobs", [])

        for item in job_items:
            try:
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
                    content_hash = self.generate_content_hash(company, title, description)
                    now_utc = datetime.now(timezone.utc)
                    
                    jobs.append(JobCreate(
                        title=title,
                        company=company,
                        location=location,
                        job_url=url,
                        description=description,
                        source="Remotive",
                        date_posted=date_posted,
                        remote_type="Remote",
                        employment_type=clean_text(item.get("job_type", "Full-time")) or "Full-time",
                        salary_range=clean_text(item.get("salary", "")) or None,
                        experience_level="Senior/Architect",
                        apply_url=url,
                        company_url=None,
                        collected_timestamp=now_utc,
                        content_hash=content_hash,
                        raw_metadata=json.dumps({"id": item.get("id"), "category": item.get("category", "")})
                    ))
            except Exception as item_err:
                logger.debug(f"{collector_name}: Skipping invalid item: {item_err}")
                continue

        logger.info(f"{collector_name}: Successfully collected and normalized {len(jobs)} live jobs.")
        return jobs

    def _get_mock_jobs(self) -> List[JobCreate]:
        now_utc = datetime.now(timezone.utc)
        desc = "Python, Machine Learning, Qdrant, PostgreSQL, FastAPI, LangGraph knowledge preferred."
        return [
            JobCreate(
                title="Senior ML & AI Backend Architect",
                company="Remotive Labs",
                location="Worldwide (Remote)",
                job_url="https://remotive.com/remote-jobs/software-dev/senior-ml-ai-backend-architect-101",
                description=desc,
                source="Remotive",
                date_posted=now_utc,
                remote_type="Remote",
                employment_type="Full-time",
                salary_range="$140k - $190k",
                experience_level="Senior",
                apply_url="https://remotive.com/remote-jobs/software-dev/senior-ml-ai-backend-architect-101",
                company_url="https://remotive.com",
                collected_timestamp=now_utc,
                content_hash=self.generate_content_hash("Remotive Labs", "Senior ML & AI Backend Architect", desc),
                raw_metadata=json.dumps({"mock": True})
            )
        ]
