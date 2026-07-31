import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from app.logger import logger
from app.monitoring.metrics import (
    PIPELINE_RUNS_TOTAL,
    PIPELINE_FAILURES_TOTAL,
    PIPELINE_DURATION_SECONDS,
    PIPELINE_CURRENT_STAGE,
    SCHEDULER_LAST_SUCCESS,
    SCHEDULER_LAST_FAILURE
)

# Numeric stage indices for Prometheus PIPELINE_CURRENT_STAGE Gauge
STAGE_MAP = {
    "IDLE": 0,
    "COLLECT_JOBS": 1,
    "NORMALIZE": 2,
    "DEDUPLICATE": 3,
    "FILTER_JOBS": 4,
    "PERSIST_JOBS": 5,
    "RETRIEVE_CONTEXT": 6,
    "GEMINI_MATCHING": 7,
    "RANK_JOBS": 8,
    "GENERATE_RESUME": 9,
    "GENERATE_COVER_LETTER": 10,
    "QUEUE_NOTIFICATIONS": 11,
    "SEND_DAILY_DIGEST": 12,
    "UPDATE_METRICS": 13,
    "COMPLETED": 14,
    "FAILED": -1
}

class PipelineTracker:
    """
    Singleton tracker maintaining detailed real-time state, stage completion logs,
    and Prometheus metric updates for the autonomous AI pipeline execution.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PipelineTracker, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.reset()

    def reset(self):
        """
        Resets active state properties.
        """
        self.pipeline_id: Optional[str] = None
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.status: str = "Idle"
        self.current_stage: str = "IDLE"
        self.completed_stages: List[str] = []
        self.failed_stage: Optional[str] = None
        self.retry_count: int = 0
        self.execution_duration: float = 0.0
        self.jobs_collected: int = 0
        self.jobs_filtered: int = 0
        self.jobs_ranked: int = 0
        self.emails_sent: int = 0

    def start_pipeline(self, pipeline_id: Optional[str] = None) -> str:
        """
        Marks commencement of an autonomous pipeline run.
        """
        now_utc = datetime.now(timezone.utc)
        self.pipeline_id = pipeline_id or f"pipe_{now_utc.strftime('%Y%m%d_%H%M%S')}"
        self.start_time = now_utc
        self.end_time = None
        self.status = "Executing"
        self.current_stage = "COLLECT_JOBS"
        self.completed_stages = []
        self.failed_stage = None
        self.retry_count = 0
        self.execution_duration = 0.0
        self.jobs_collected = 0
        self.jobs_filtered = 0
        self.jobs_ranked = 0
        self.emails_sent = 0

        PIPELINE_CURRENT_STAGE.set(STAGE_MAP.get("COLLECT_JOBS", 1))
        logger.info(f"PipelineTracker: Started autonomous pipeline run '{self.pipeline_id}'.")
        return self.pipeline_id

    def set_stage(self, stage_name: str):
        """
        Updates current active pipeline stage.
        """
        if self.current_stage and self.current_stage not in self.completed_stages and self.current_stage != "IDLE":
            self.completed_stages.append(self.current_stage)

        self.current_stage = stage_name
        stage_num = STAGE_MAP.get(stage_name, 0)
        PIPELINE_CURRENT_STAGE.set(stage_num)
        logger.info(f"PipelineTracker [{self.pipeline_id}]: Stage transitioned to '{stage_name}'.")

    def record_stage_failure(self, stage_name: str, error_message: str):
        """
        Logs a non-fatal or fatal node error during pipeline execution.
        """
        self.failed_stage = stage_name
        self.retry_count += 1
        PIPELINE_FAILURES_TOTAL.labels(stage=stage_name).inc()
        logger.warning(f"PipelineTracker [{self.pipeline_id}]: Stage '{stage_name}' reported failure: {error_message}")

    def finish_pipeline(self, stats: Dict[str, Any], is_success: bool = True):
        """
        Finalizes pipeline run, updates Prometheus metrics, and records final stats.
        """
        self.end_time = datetime.now(timezone.utc)
        if self.start_time:
            self.execution_duration = round((self.end_time - self.start_time).total_seconds(), 2)

        if self.current_stage and self.current_stage not in self.completed_stages and self.current_stage not in ["IDLE", "COMPLETED", "FAILED"]:
            self.completed_stages.append(self.current_stage)

        self.jobs_collected = stats.get("collected", 0)
        self.jobs_filtered = stats.get("filtered", 0)
        self.jobs_ranked = stats.get("ranked", 0)
        self.emails_sent = stats.get("emails_sent", 0)

        if is_success:
            self.status = "Completed"
            self.current_stage = "COMPLETED"
            PIPELINE_CURRENT_STAGE.set(STAGE_MAP["COMPLETED"])
            PIPELINE_RUNS_TOTAL.labels(status="success").inc()
            SCHEDULER_LAST_SUCCESS.set(self.end_time.timestamp())
        else:
            self.status = "Failed"
            self.current_stage = "FAILED"
            PIPELINE_CURRENT_STAGE.set(STAGE_MAP["FAILED"])
            PIPELINE_RUNS_TOTAL.labels(status="failure").inc()
            SCHEDULER_LAST_FAILURE.set(self.end_time.timestamp())

        PIPELINE_DURATION_SECONDS.observe(self.execution_duration)
        logger.info(f"PipelineTracker [{self.pipeline_id}]: Finished run with status '{self.status}' in {self.execution_duration}s.")

    def get_status_dict(self) -> Dict[str, Any]:
        """
        Returns structured dictionary for dashboard endpoints and status queries.
        """
        return {
            "pipeline_id": self.pipeline_id or "N/A",
            "pipeline_status": self.status,
            "current_stage": self.current_stage,
            "start_time": self.start_time.isoformat() if self.start_time else "Never",
            "end_time": self.end_time.isoformat() if self.end_time else "N/A",
            "pipeline_duration": f"{self.execution_duration:.2f}s",
            "execution_duration_seconds": self.execution_duration,
            "completed_stages": list(self.completed_stages),
            "failed_stage": self.failed_stage,
            "retry_count": self.retry_count,
            "jobs_collected": self.jobs_collected,
            "jobs_filtered": self.jobs_filtered,
            "jobs_ranked": self.jobs_ranked,
            "jobs_processed": self.jobs_collected,
            "emails_sent": self.emails_sent,
            "notifications_sent": self.emails_sent
        }

# Global Singleton Instance
pipeline_tracker = PipelineTracker()
