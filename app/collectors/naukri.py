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

class NaukriCollector(BaseCollector):
    """
    Collector for Naukri jobs.
    Implements BeautifulSoup scraping logic with a configurable mock fallback.
    """
    
    def __init__(self, mock_mode: Optional[bool] = None):
        self.mock_mode = settings.MOCK_COLLECTOR if mock_mode is None else mock_mode
        self.url = "https://www.naukri.com/python-developer-jobs"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
        }

    def collect(self) -> List[JobCreate]:
        logger.info("Collector started: NaukriCollector")
        
        if self.mock_mode:
            logger.info("NaukriCollector running in MOCK mode. Returning simulated jobs.")
            return self._get_mock_jobs()
            
        try:
            # Naukri standard GET request usually returns JS rendered content or 403 blocks.
            response = requests.get(self.url, headers=self.headers, timeout=15)
            
            if response.status_code in (403, 503):
                logger.warning("Access to Naukri was blocked (bot detection). Falling back to mock jobs.")
                return self._get_mock_jobs()
                
            response.raise_for_status()
            return self._parse_html(response.text)
            
        except requests.RequestException as e:
            logger.error(f"Network error in NaukriCollector: {e}. Falling back to mock jobs.")
            return self._get_mock_jobs()
        except Exception as e:
            logger.error(f"Unexpected error in NaukriCollector: {e}. Falling back to mock jobs.")
            return self._get_mock_jobs()

    def _parse_html(self, html_content: str) -> List[JobCreate]:
        soup = BeautifulSoup(html_content, "html.parser")
        jobs: List[JobCreate] = []
        
        # Naukri HTML uses custom CSS classes. Select job cards:
        job_cards = soup.select("article.jobTuple") or soup.select(".cust-job-tuple")
        
        if not job_cards:
            logger.warning("No job cards found during Naukri HTML parsing. Selector might be outdated.")
            return []

        for card in job_cards:
            try:
                # Title
                title_elem = card.select_one("a.title") or card.select_one(".title")
                title = clean_text(title_elem.text) if title_elem else ""

                # Company
                company_elem = card.select_one("a.subTitle") or card.select_one(".subTitle")
                company = clean_text(company_elem.text) if company_elem else ""

                # Location
                loc_elem = card.select_one("li.location") or card.select_one(".location")
                location = clean_text(loc_elem.text) if loc_elem else "Remote"

                # URL
                job_url = ""
                if title_elem and title_elem.get("href"):
                    href = title_elem["href"]
                    job_url = href if href.startswith("http") else f"https://www.naukri.com{href}"

                # Description
                desc_elem = card.select_one(".jobDescription") or card.select_one(".ellipsis")
                description = clean_text(desc_elem.text) if desc_elem else "No description provided."

                if not title or not company or not job_url:
                    continue

                job = JobCreate(
                    title=title,
                    company=company,
                    location=location,
                    job_url=job_url,
                    description=description,
                    source="Naukri",
                    date_posted=datetime.now(timezone.utc)
                )
                jobs.append(job)
                
            except Exception as e:
                logger.warning(f"Error parsing Naukri job card: {e}")
                continue
                
        return jobs

    def _get_mock_jobs(self) -> List[JobCreate]:
        now = datetime.now(timezone.utc)
        return [
            # 1. Allowed title, Preferred location, 0-2 yrs experience, matches Machine Learning -> KEEP
            JobCreate(
                title="AI Engineer",
                company="Naukri AI Solutions",
                location="Pune, MH",
                job_url="https://naukri.com/jobs/naukri111",
                description="We need an AI Engineer. Experience requirement is 0-2 years. Skillset includes Machine Learning and Python.",
                source="Naukri",
                date_posted=now - timedelta(hours=5)
            ),
            # 2. Non-allowed title (Java Developer) -> FILTER OUT
            JobCreate(
                title="Java Software Developer",
                company="Enterprise Systems",
                location="Kochi",
                job_url="https://naukri.com/jobs/naukri222",
                description="We are seeking Java Developers with 1 year experience. Python or SQL is nice to have.",
                source="Naukri",
                date_posted=now - timedelta(days=1)
            ),
            # 3. Allowed title, Preferred location (Kochi), 1 year experience, matches skill Generative AI -> KEEP
            JobCreate(
                title="Generative AI Engineer",
                company="GenAI Labs",
                location="Kochi, Kerala",
                job_url="https://naukri.com/jobs/naukri333",
                description="Join as a Generative AI Engineer with at least 1 year of experience. Must know Generative AI, LLM, PyTorch.",
                source="Naukri",
                date_posted=now - timedelta(hours=8)
            ),
            # 4. Allowed title, Non-preferred location (Delhi) -> FILTER OUT
            JobCreate(
                title="Data Scientist",
                company="Capitol Analytics",
                location="Delhi / NCR",
                job_url="https://naukri.com/jobs/naukri444",
                description="Looking for Data Scientist with Python and SQL. Entry level or fresher is allowed.",
                source="Naukri",
                date_posted=now - timedelta(days=3)
            ),
            # 5. Duplicate of Indeed Job 1 (to test service-level compound de-duplication) -> FILTER OUT
            JobCreate(
                title="Python Developer",
                company="Indeed Tech Partners",
                location="Remote",
                job_url="https://naukri.com/jobs/naukri-dup",
                description="We are hiring a Python Developer with 1 year of experience. Must know Python, SQL, and Git.",
                source="Naukri",
                date_posted=now - timedelta(hours=3)
            )
        ]
