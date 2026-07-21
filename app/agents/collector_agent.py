from typing import List, Dict, Any
from app.collectors.collector_manager import CollectorManager
from app.logger import logger

class CollectorAgent:
    """
    CollectorAgent runs all registered scraping collectors via CollectorManager.
    Combines raw outputs into a unified list of job dictionaries.
    """
    def __init__(self, collector_manager: CollectorManager):
        self.collector_manager = collector_manager

    def collect(self) -> tuple[List[Dict[str, Any]], int]:
        """
        Executes collectors and returns tuple of (list of collected jobs, count of failed collectors).
        """
        logger.info("CollectorAgent: Starting multi-source collections.")
        try:
            # collector_manager.collect_all() returns (list_of_jobs, failed_count)
            jobs, failed_count = self.collector_manager.collect_all()
            logger.info(f"CollectorAgent: Collection complete. Gathered {len(jobs)} jobs. Failed: {failed_count}")
            return jobs, failed_count
        except Exception as e:
            logger.error(f"CollectorAgent: Collection execution failed: {e}", exc_info=True)
            raise
