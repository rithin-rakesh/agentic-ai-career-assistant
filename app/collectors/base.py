import hashlib
from abc import ABC, abstractmethod
from typing import List, Optional
from app.schemas.job import JobCreate

class BaseCollector(ABC):
    """
    Abstract Base Class for all job collectors.
    All source-specific collectors must inherit from this class and implement collect().
    """
    @abstractmethod
    def collect(self) -> List[JobCreate]:
        """
        Fetches jobs from the target source, parses them, validates them,
        and returns a list of JobCreate schema instances.
        """
        pass

    @staticmethod
    def generate_content_hash(company: str, title: str, description: Optional[str] = "") -> str:
        """
        Generates a normalized SHA-256 hash string from company, title, and description.
        """
        norm_company = (company or "").lower().strip()
        norm_title = (title or "").lower().strip()
        norm_desc = (description or "")[:200].lower().strip()
        raw_key = f"{norm_company}:{norm_title}:{norm_desc}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
