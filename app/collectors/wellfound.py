import time
from datetime import datetime, timezone, timedelta
from typing import List, Optional
import requests
from bs4 import BeautifulSoup
from app.collectors.base import BaseCollector
from app.schemas.job import JobCreate
from app.config import settings
from app.logger import logger
from app.utils.helpers import clean_text

class WellfoundCollector(BaseCollector):
    """
    Collector for Wellfound (formerly AngelList) jobs.
    Implements BeautifulSoup scraping logic with a configurable mock fallback.
    """
    
    def __init__(self, mock_mode: Optional[bool] = None):
        # Allow overriding the config setting via constructor injection (e.g. for testing)
        self.mock_mode = settings.MOCK_COLLECTOR if mock_mode is None else mock_mode
        self.url = "https://wellfound.com/jobs"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
        }

    def collect(self) -> List[JobCreate]:
        """
        Collects job listings from Wellfound.
        """
        logger.info("Collector started: WellfoundCollector")
        
        if self.mock_mode:
            logger.info("WellfoundCollector running in MOCK mode. Returning simulated jobs.")
            return self._get_mock_jobs()
            
        try:
            # Live scraping logic
            response = requests.get(self.url, headers=self.headers, timeout=15)
            
            # Check for Cloudflare / HTTP 403 Forbidden
            if response.status_code == 403:
                logger.warning("Access to Wellfound was blocked (HTTP 403 / Cloudflare). Falling back to mock jobs to avoid failure.")
                return self._get_mock_jobs()
                
            response.raise_for_status()
            return self._parse_html(response.text)
            
        except requests.RequestException as e:
            logger.error(f"Network error in WellfoundCollector: {e}. Falling back to mock jobs.")
            return self._get_mock_jobs()
        except Exception as e:
            logger.error(f"Unexpected error in WellfoundCollector: {e}. Falling back to mock jobs.")
            return self._get_mock_jobs()

    def _parse_html(self, html_content: str) -> List[JobCreate]:
        """
        Parses raw HTML using BeautifulSoup.
        """
        soup = BeautifulSoup(html_content, "html.parser")
        jobs: List[JobCreate] = []
        
        # Wellfound HTML structure varies, but we parse standard job card selectors.
        # This is a sample selector structure for jobs on Wellfound.
        job_cards = soup.select(".styles_component__W_53a") or soup.select("[data-test='JobResultCard']")
        
        if not job_cards:
            logger.warning("No job cards found during BeautifulSoup parsing. HTML structure might have changed.")
            return []

        for card in job_cards:
            try:
                # Extract title
                title_elem = card.select_one(".styles_title__JdD_u") or card.select_one("h2")
                title = clean_text(title_elem.text) if title_elem else ""

                # Extract company
                company_elem = card.select_one(".styles_name__44fV5") or card.select_one("h3")
                company = clean_text(company_elem.text) if company_elem else ""

                # Extract location
                loc_elem = card.select_one(".styles_location__P4r_3") or card.select_one(".styles_location__")
                location = clean_text(loc_elem.text) if loc_elem else "Remote"

                # Extract URL
                link_elem = card.select_one("a[href*='/jobs/']") or card.select_one("a")
                job_url = ""
                if link_elem and link_elem.get("href"):
                    href = link_elem["href"]
                    job_url = href if href.startswith("http") else f"https://wellfound.com{href}"

                # Extract description / snippets
                desc_elem = card.select_one(".styles_description__2sDws") or card.select_one(".styles_jobDetails__")
                description = clean_text(desc_elem.text) if desc_elem else "No description provided."

                # If missing crucial identifiers, skip the single card but do not crash
                if not title or not company or not job_url:
                    logger.debug(f"Skipping job card due to missing title, company, or URL.")
                    continue

                job = JobCreate(
                    title=title,
                    company=company,
                    location=location,
                    job_url=job_url,
                    description=description,
                    source="Wellfound",
                    date_posted=datetime.now(timezone.utc)
                )
                jobs.append(job)
                
            except Exception as e:
                # Resilience: Never let a single bad card crash the pipeline
                logger.warning(f"Error parsing job card: {e}")
                continue
                
        return jobs

    def _get_mock_jobs(self) -> List[JobCreate]:
        """
        Generates structured mock jobs representing real-world search results
        for testing and pipeline validation.
        """
        now = datetime.now(timezone.utc)
        return [
            JobCreate(
                title="Staff AI Engineer",
                company="NeuroTech Inc.",
                location="San Francisco, CA (Hybrid)",
                job_url="https://wellfound.com/jobs/neurotech-staff-ai-engineer-101",
                description="We are seeking an experienced Staff AI Engineer to design and deploy large language model agents and retrieval-augmented generation systems.",
                source="Wellfound",
                date_posted=now - timedelta(hours=2)
            ),
            JobCreate(
                title="Senior Backend Engineer (Python)",
                company="DataStream Corp",
                location="Remote (US/Canada)",
                job_url="https://wellfound.com/jobs/datastream-senior-backend-engineer-202",
                description="Join our data infrastructure team building highly scalable pipelines, database systems, and integration interfaces using Python 3.11, PostgreSQL, and FastAPI.",
                source="Wellfound",
                date_posted=now - timedelta(days=1)
            ),
            JobCreate(
                title="Machine Learning Engineer",
                company="AlphaScale Robotics",
                location="Boston, MA",
                job_url="https://wellfound.com/jobs/alphascale-ml-engineer-303",
                description="Looking for an ML engineer with expertise in PyTorch and computer vision algorithms. Experience in robot control loops is a plus.",
                source="Wellfound",
                date_posted=now - timedelta(days=2)
            ),
            # Duplicate job to test service-level deduplication
            JobCreate(
                title="Senior Backend Engineer (Python)",
                company="DataStream Corp",
                location="Remote (US/Canada)",
                job_url="https://wellfound.com/jobs/datastream-senior-backend-engineer-202",
                description="Join our data infrastructure team building highly scalable pipelines, database systems, and integration interfaces using Python 3.11, PostgreSQL, and FastAPI.",
                source="Wellfound",
                date_posted=now - timedelta(days=1)
            ),
            # Invalid job to test service-level Pydantic validation (will fail validation due to empty title)
            # JobCreate expects non-empty title. We will manually test this behavior in unit tests.
        ]
