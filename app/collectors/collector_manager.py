import time
from typing import List, Tuple, Dict, Any
from app.collectors.base import BaseCollector
from app.schemas.job import JobCreate
from app.logger import logger

class CollectorManager:
    """
    Manages registration and execution of multiple source-specific collectors.
    Ensures pipeline resilience by catching crashes in individual collectors
    and merging successful results. Tracks collector health and latency status.
    """
    def __init__(self, collectors: List[BaseCollector] = None):
        self.collectors: List[BaseCollector] = collectors or []
        self.collector_status: Dict[str, Dict[str, Any]] = {}
        self.last_collection_time: float = 0.0
        self.last_collection_duration: float = 0.0

    def register_collector(self, collector: BaseCollector) -> None:
        """
        Registers a new collector into the manager.
        """
        self.collectors.append(collector)
        collector_name = collector.__class__.__name__
        self.collector_status[collector_name] = {
            "status": "registered",
            "latency": 0.0,
            "jobs_collected": 0,
            "last_error": None
        }
        logger.info(f"Registered collector: {collector_name}")

    def collect_all(self) -> Tuple[List[JobCreate], int]:
        """
        Runs all registered collectors sequentially.
        Catches collector-specific exceptions to avoid stopping the overall pipeline.
        Returns a tuple: (merged_job_list, failed_collectors_count).
        """
        merged_jobs: List[JobCreate] = []
        failed_count = 0
        overall_start = time.perf_counter()
        
        logger.info(f"Starting multi-source collection. Total collectors registered: {len(self.collectors)}")
        
        for collector in self.collectors:
            collector_name = collector.__class__.__name__
            col_start = time.perf_counter()
            try:
                logger.info(f"Executing collector: {collector_name}")
                jobs = collector.collect()
                col_duration = time.perf_counter() - col_start
                merged_jobs.extend(jobs)
                
                self.collector_status[collector_name] = {
                    "status": "healthy",
                    "latency": round(col_duration, 3),
                    "jobs_collected": len(jobs),
                    "last_error": None
                }
                logger.info(f"Collector completed: {collector_name}. Gathered {len(jobs)} jobs in {col_duration:.3f}s.")
            except Exception as e:
                col_duration = time.perf_counter() - col_start
                failed_count += 1
                self.collector_status[collector_name] = {
                    "status": "failed",
                    "latency": round(col_duration, 3),
                    "jobs_collected": 0,
                    "last_error": str(e)
                }
                logger.error(f"Collector failed: {collector_name}. Error details: {e}", exc_info=True)
                continue
                
        self.last_collection_duration = time.perf_counter() - overall_start
        self.last_collection_time = time.time()
        logger.info(f"Multi-source collection finished. Total collected jobs: {len(merged_jobs)}. Failed collectors: {failed_count}. Duration: {self.last_collection_duration:.2f}s")
        return merged_jobs, failed_count
