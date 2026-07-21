import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Callable
from apscheduler.schedulers.background import BackgroundScheduler
from app.config import settings
from app.logger import logger

class SchedulerManager:
    """
    Singleton manager controlling background task scheduling, status tracking,
    and interactive dashboard actions (Start, Pause, Resume, Restart, Run Now).
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SchedulerManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.scheduler: Optional[BackgroundScheduler] = None
        self.status: str = "Stopped"
        self.last_run: Optional[datetime] = None
        self.next_run: Optional[datetime] = None
        self.last_duration: float = 0.0
        self.last_jobs_collected: int = 0
        self.current_queue: int = 0
        self.sync_callback: Optional[Callable] = None

    def initialize(self, sync_callback: Callable, interval_hours: int = 4):
        """
        Initializes the BackgroundScheduler daemon with task callback and frequency.
        """
        self.sync_callback = sync_callback
        if not self.scheduler:
            self.scheduler = BackgroundScheduler()

        self.reschedule(interval_hours)
        self.start()

    def start(self):
        """
        Starts the scheduler if not already running.
        """
        if self.scheduler:
            if not self.scheduler.running:
                self.scheduler.start()
                logger.info("SchedulerManager: Scheduler started.")
            else:
                try:
                    self.scheduler.resume()
                except Exception:
                    pass
            self.status = "Running"
            self._update_next_run()

    def pause(self):
        """
        Pauses the active scheduled sync job.
        """
        if self.scheduler and self.scheduler.running:
            try:
                self.scheduler.pause_job('periodic_job_sync')
            except Exception as e:
                logger.warning(f"SchedulerManager: Pause failed: {e}")
            self.status = "Paused"
            logger.info("SchedulerManager: Scheduler paused.")

    def resume(self):
        """
        Resumes the paused scheduled sync job.
        """
        if self.scheduler and self.scheduler.running:
            try:
                self.scheduler.resume_job('periodic_job_sync')
            except Exception as e:
                logger.warning(f"SchedulerManager: Resume failed: {e}")
            self.status = "Running"
            self._update_next_run()

    def restart(self, interval_hours: Optional[int] = None):
        """
        Restarts scheduler daemon with optional new interval.
        """
        if self.scheduler:
            interval = interval_hours or settings.COLLECTION_INTERVAL_HOURS
            self.reschedule(interval)
            self.start()

    def reschedule(self, interval_hours: int):
        """
        Reconfigures the periodic job interval.
        """
        settings.COLLECTION_INTERVAL_HOURS = interval_hours
        if self.scheduler:
            try:
                self.scheduler.add_job(
                    self.execute_task_wrapper,
                    'interval',
                    hours=interval_hours,
                    id='periodic_job_sync',
                    replace_existing=True
                )
                logger.info(f"SchedulerManager: Rescheduled sync every {interval_hours} hour(s).")
                self._update_next_run()
            except Exception as e:
                logger.error(f"SchedulerManager: Reschedule error: {e}")

    def run_now(self) -> Dict[str, Any]:
        """
        Triggers an immediate collection sync.
        """
        logger.info("SchedulerManager: Manual 'Run Now' triggered.")
        return self.execute_task_wrapper()

    def execute_task_wrapper(self) -> Dict[str, Any]:
        """
        Executes the registered sync callback, measuring duration and collecting stats.
        """
        previous_status = self.status
        self.status = "Executing"
        self.current_queue += 1
        start_time = time.perf_counter()
        now_utc = datetime.now(timezone.utc)
        self.last_run = now_utc

        result_stats = {"collected": 0, "matched": 0}
        try:
            if self.sync_callback:
                res = self.sync_callback()
                if isinstance(res, dict):
                    result_stats = res
                    self.last_jobs_collected = res.get("total_collected", res.get("collected", 0))
        except Exception as e:
            logger.error(f"SchedulerManager task execution error: {e}", exc_info=True)
        finally:
            self.last_duration = round(time.perf_counter() - start_time, 2)
            self.current_queue = max(0, self.current_queue - 1)
            self.status = previous_status if previous_status != "Executing" else "Running"
            self._update_next_run()

        return result_stats

    def _update_next_run(self):
        """
        Updates calculated next run time.
        """
        if self.scheduler and self.scheduler.running:
            job = self.scheduler.get_job('periodic_job_sync')
            if job and job.next_run_time:
                self.next_run = job.next_run_time
            elif self.last_run:
                self.next_run = self.last_run + timedelta(hours=settings.COLLECTION_INTERVAL_HOURS)
            else:
                self.next_run = datetime.now(timezone.utc) + timedelta(hours=settings.COLLECTION_INTERVAL_HOURS)

    def get_status_dict(self) -> Dict[str, Any]:
        """
        Returns status dictionary for dashboard and API endpoints.
        """
        self._update_next_run()
        return {
            "current_status": self.status,
            "last_run": self.last_run.isoformat() if self.last_run else "Never",
            "next_run": self.next_run.isoformat() if self.next_run else "N/A",
            "duration": f"{self.last_duration:.2f} seconds",
            "jobs_collected": self.last_jobs_collected,
            "current_queue": self.current_queue,
            "interval_hours": settings.COLLECTION_INTERVAL_HOURS
        }

# Global Singleton Instance
scheduler_manager = SchedulerManager()
