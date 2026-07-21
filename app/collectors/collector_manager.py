from typing import List, Tuple
from app.collectors.base import BaseCollector
from app.schemas.job import JobCreate
from app.logger import logger

class CollectorManager:
    """
    Manages registration and execution of multiple source-specific collectors.
    Ensures pipeline resilience by catching crashes in individual collectors
    and merging successful results.
    """
    def __init__(self, collectors: List[BaseCollector] = None):
        self.collectors: List[BaseCollector] = collectors or []

    def register_collector(self, collector: BaseCollector) -> None:
        """
        Registers a new collector into the manager.
        """
        self.collectors.append(collector)
        logger.info(f"Registered collector: {collector.__class__.__name__}")

    def collect_all(self) -> Tuple[List[JobCreate], int]:
        """
        Runs all registered collectors sequentially.
        Catches collector-specific exceptions to avoid stopping the overall pipeline.
        Returns a tuple: (merged_job_list, failed_collectors_count).
        """
        merged_jobs: List[JobCreate] = []
        failed_count = 0
        
        logger.info(f"Starting multi-source collection. Total collectors registered: {len(self.collectors)}")
        
        for collector in self.collectors:
            collector_name = collector.__class__.__name__
            try:
                logger.info(f"Executing collector: {collector_name}")
                jobs = collector.collect()
                merged_jobs.extend(jobs)
                logger.info(f"Collector completed: {collector_name}. Gathered {len(jobs)} jobs.")
            except Exception as e:
                failed_count += 1
                logger.error(f"Collector failed: {collector_name}. Error details: {e}", exc_info=True)
                continue
                
        logger.info(f"Multi-source collection finished. Total collected jobs: {len(merged_jobs)}. Failed collectors: {failed_count}")
        return merged_jobs, failed_count
