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

class RemoteOKCollector(BaseCollector):
    """
    Collector for RemoteOK live API (https://remoteok.com/api).
    Includes retry logic, exponential backoff, response validation, latency tracking,
    and schema normalization.
    """
    def __init__(self, mock_mode: Optional[bool] = None, max_retries: int = 3, timeout: int = 15):
        self.mock_mode = settings.MOCK_COLLECTOR if mock_mode is None else mock_mode
        self.api_url = "https://remoteok.com/api"
        self.max_retries = max_retries
        self.timeout = timeout
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json"
        }

    def collect(self) -> List[JobCreate]:
        collector_name = "RemoteOKCollector"
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
                if not isinstance(data, list):
                    raise ValueError(f"{collector_name}: Expected JSON list, got {type(data)}")
                
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

        # Normalize jobs
        jobs: List[JobCreate] = []
        job_items = [item for item in data if isinstance(item, dict) and "position" in item]

        for item in job_items:
            try:
                title = clean_text(item.get("position", ""))
                company = clean_text(item.get("company", ""))
                description = clean_text(item.get("description", ""))
                location = clean_text(item.get("location", "Remote")) or "Remote"
                url = item.get("url") or f"https://remoteok.com/remote-jobs/{item.get('id')}"
                
                epoch = item.get("date")
                if epoch:
                    try:
                        date_posted = datetime.fromtimestamp(int(epoch), tz=timezone.utc)
                    except Exception:
                        date_posted = datetime.now(timezone.utc)
                else:
                    date_posted = datetime.now(timezone.utc)

                if title and company and description:
                    content_hash = self.generate_content_hash(company, title, description)
                    now_utc = datetime.now(timezone.utc)
                    
                    jobs.append(JobCreate(
                        title=title,
                        company=company,
                        location=location,
                        job_url=url,
                        description=description,
                        source="RemoteOK",
                        date_posted=date_posted,
                        remote_type="Remote",
                        employment_type="Full-time",
                        salary_range=clean_text(str(item.get("salary", ""))) or None,
                        experience_level="Senior/Mid",
                        apply_url=url,
                        company_url=item.get("company_url") or None,
                        collected_timestamp=now_utc,
                        content_hash=content_hash,
                        raw_metadata=json.dumps({"id": item.get("id"), "tags": item.get("tags", [])})
                    ))
            except Exception as item_err:
                logger.debug(f"{collector_name}: Skipping invalid item: {item_err}")
                continue

        logger.info(f"{collector_name}: Successfully collected and normalized {len(jobs)} live jobs.")
        return jobs

    def _get_mock_jobs(self) -> List[JobCreate]:
        now_utc = datetime.now(timezone.utc)
        desc = "Looking for Python, LLMs, LangChain, PyTorch, and Qdrant experience for AI systems."
        return [
            JobCreate(
                title="Remote AI Systems Engineer",
                company="Nexus AI",
                location="Remote",
                job_url="https://remoteok.com/remote-jobs/nexus-ai-systems-engineer",
                description=desc,
                source="RemoteOK",
                date_posted=now_utc,
                remote_type="Remote",
                employment_type="Full-time",
                salary_range="$120k - $160k",
                experience_level="Mid-Senior",
                apply_url="https://remoteok.com/remote-jobs/nexus-ai-systems-engineer",
                company_url="https://nexusai.com",
                collected_timestamp=now_utc,
                content_hash=self.generate_content_hash("Nexus AI", "Remote AI Systems Engineer", desc),
                raw_metadata=json.dumps({"mock": True})
            )
        ]
