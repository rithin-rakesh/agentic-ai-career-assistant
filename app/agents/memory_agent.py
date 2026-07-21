from typing import Dict, Any, Tuple
from app.memory.application_memory import ApplicationMemoryManager
from app.logger import logger

class MemoryAgent:
    """
    Inspects active listings against long-term memory configurations.
    Enforces filtering for blocked/ignored companies, and highlights
    opportunities matching favorite target firms, preferred technology stacks,
    or location profiles.
    """
    def __init__(self, memory_manager: ApplicationMemoryManager = None):
        self.memory_manager = memory_manager or ApplicationMemoryManager()

    def process_preferences(self, job_dict: Dict[str, Any]) -> Tuple[bool, bool, str]:
        """
        Evaluates a job against preference metrics.
        Returns: (should_block: bool, is_favorite: bool, reason: str)
        """
        company = job_dict.get("company", "").strip()
        location = job_dict.get("location", "").strip()
        description = job_dict.get("description", "").strip().lower()

        memory = self.memory_manager.memory

        # 1. Enforce blocked companies filter
        ignored_companies = [c.lower() for c in memory.get("ignored_companies", [])]
        if company.lower() in ignored_companies:
            logger.info(f"MemoryAgent: Flagged blocked company match for '{company}'. Routing to IGNORE.")
            return True, False, "Company is in the ignored list"

        # 2. Check for favorite companies
        favorite_companies = [c.lower() for c in memory.get("favorite_companies", [])]
        if company.lower() in favorite_companies:
            logger.info(f"MemoryAgent: Highlighted favorite target company match for '{company}'!")
            return False, True, "Matches target favorite company"

        # 3. Check for preferred technologies highlights
        preferred_tech = memory.get("preferred_technologies", [])
        matched_tech = []
        for tech in preferred_tech:
            if tech.lower() in description:
                matched_tech.append(tech)

        if matched_tech:
            logger.debug(f"MemoryAgent: Matched preferred technologies: {matched_tech}")
            return False, False, f"Matches technologies: {', '.join(matched_tech)}"

        return False, False, "Neutral match"
