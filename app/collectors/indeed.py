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

class IndeedCollector(BaseCollector):
    """
    Collector for Indeed jobs.
    Implements BeautifulSoup scraping logic with a configurable mock fallback.
    """
    
    def __init__(self, mock_mode: Optional[bool] = None):
        self.mock_mode = settings.MOCK_COLLECTOR if mock_mode is None else mock_mode
        self.url = "https://indeed.com/jobs?q=python+developer"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
        }

    def collect(self) -> List[JobCreate]:
        logger.info("Collector started: IndeedCollector")
        
        if self.mock_mode:
            logger.info("IndeedCollector running in MOCK mode. Returning simulated jobs.")
            return self._get_mock_jobs()
            
        try:
            response = requests.get(self.url, headers=self.headers, timeout=15)
            
            if response.status_code in (403, 503):
                logger.warning("Access to Indeed was blocked (bot detection). Falling back to mock jobs.")
                return self._get_mock_jobs()
                
            response.raise_for_status()
            return self._parse_html(response.text)
            
        except requests.RequestException as e:
            logger.error(f"Network error in IndeedCollector: {e}. Falling back to mock jobs.")
            return self._get_mock_jobs()
        except Exception as e:
            logger.error(f"Unexpected error in IndeedCollector: {e}. Falling back to mock jobs.")
            return self._get_mock_jobs()

    def _parse_html(self, html_content: str) -> List[JobCreate]:
        soup = BeautifulSoup(html_content, "html.parser")
        jobs: List[JobCreate] = []
        
        # Indeed DOM structure
        job_cards = soup.select(".job_seen_beacon") or soup.select(".tapItem")
        
        if not job_cards:
            logger.warning("No job cards found during Indeed HTML parsing. Selector might be outdated.")
            return []

        for card in job_cards:
            try:
                # Title
                title_elem = card.select_one("h2.jobTitle") or card.select_one("span[id^='jobTitle']")
                title = clean_text(title_elem.text) if title_elem else ""

                # Company
                company_elem = card.select_one(".companyName") or card.select_one("[data-testid='company-name']")
                company = clean_text(company_elem.text) if company_elem else ""

                # Location
                loc_elem = card.select_one(".companyLocation") or card.select_one("[data-testid='text-location']")
                location = clean_text(loc_elem.text) if loc_elem else "Remote"

                # URL
                link_elem = card.select_one("a[data-jk]") or card.select_one("a")
                job_url = ""
                if link_elem:
                    jk = link_elem.get("data-jk")
                    if jk:
                        job_url = f"https://www.indeed.com/viewjob?jk={jk}"
                    else:
                        href = link_elem.get("href", "")
                        job_url = href if href.startswith("http") else f"https://www.indeed.com{href}"

                # Description snippet
                desc_elem = card.select_one(".job-snippet") or card.select_one(".summary")
                description = clean_text(desc_elem.text) if desc_elem else "No description snippet."

                if not title or not company or not job_url:
                    continue

                job = JobCreate(
                    title=title,
                    company=company,
                    location=location,
                    job_url=job_url,
                    description=description,
                    source="Indeed",
                    date_posted=datetime.now(timezone.utc)
                )
                jobs.append(job)
                
            except Exception as e:
                logger.warning(f"Error parsing Indeed job card: {e}")
                continue
                
        return jobs

    def _get_mock_jobs(self) -> List[JobCreate]:
        now = datetime.now(timezone.utc)
        return [
            # 1. Allowed title, Remote location, 1 year experience, matches skill SQL -> KEEP
            JobCreate(
                title="Python Developer",
                company="Indeed Tech Partners",
                location="Remote",
                job_url="https://indeed.com/viewjob?jk=indeed111",
                description="We are hiring a Python Developer with 1 year of experience. Must know Python, SQL, and Git.",
                source="Indeed",
                date_posted=now - timedelta(hours=3)
            ),
            # 2. Non-allowed title (Product Manager) -> FILTER OUT
            JobCreate(
                title="Technical Product Manager",
                company="Future Scale",
                location="Bangalore",
                job_url="https://indeed.com/viewjob?jk=indeed222",
                description="Looking for PM with 1-3 years of experience. High growth startup.",
                source="Indeed",
                date_posted=now - timedelta(days=1)
            ),
            # 3. Allowed title, Non-preferred location (Mumbai) -> FILTER OUT
            JobCreate(
                title="Data Analyst",
                company="FinAnalytics Ltd",
                location="Mumbai, MH",
                job_url="https://indeed.com/viewjob?jk=indeed333",
                description="Hiring Data Analyst with Python and Power BI skills. Experience level is entry level.",
                source="Indeed",
                date_posted=now - timedelta(days=2)
            ),
            # 4. Allowed title, Preferred location, Too much experience (5 years) -> FILTER OUT
            JobCreate(
                title="Senior ML Engineer",
                company="RoboMind Solutions",
                location="Bangalore, KA",
                job_url="https://indeed.com/viewjob?jk=indeed444",
                description="Required ML Engineer with 5+ years of experience in Deep Learning, PyTorch, OpenCV, and TensorFlow.",
                source="Indeed",
                date_posted=now - timedelta(hours=10)
            ),
            # 5. Allowed title, Preferred location, 0 experience, Missing required skills (only mentions HTML/CSS/React) -> FILTER OUT
            JobCreate(
                title="Python Developer",
                company="ReactWeb Corp",
                location="Hyderabad",
                job_url="https://indeed.com/viewjob?jk=indeed555",
                description="Hiring Python Developer with 0 years of experience. Responsibilities include frontend HTML, CSS, React, and simple backend routines.",
                source="Indeed",
                date_posted=now - timedelta(hours=1)
            )
        ]
