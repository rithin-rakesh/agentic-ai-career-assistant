from apscheduler.schedulers.blocking import BlockingScheduler
from app.services.collection_service import CollectionService
from app.logger import logger
from app.config import settings

class JobScheduler:
    """
    Periodic job scheduler wrapping APScheduler.
    Executes the CollectionService job sync pipeline at configured intervals.
    """
    def __init__(self, collection_service: CollectionService):
        self.scheduler = BlockingScheduler()
        self.collection_service = collection_service
        self.interval_hours = settings.COLLECTION_INTERVAL_HOURS

    def start(self) -> None:
        """
        Starts the scheduler daemon loop.
        Blocks the calling thread until stopped by system signals or KeyboardInterrupt.
        """
        logger.info(f"Scheduler execution initiated. Sync interval: every {self.interval_hours} hour(s).")
        
        # 1. Schedule periodic job
        self.scheduler.add_job(
            self._scheduled_task,
            'interval',
            hours=self.interval_hours,
            id='periodic_job_sync',
            replace_existing=True
        )
        
        # 2. Trigger an immediate execution on startup to verify setup and populate databases
        self.scheduler.add_job(
            self._scheduled_task,
            id='startup_job_sync'
        )
        
        try:
            self.scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler shutdown signal received. Stopping daemon gracefully...")
            self.scheduler.shutdown()
        except Exception as e:
            logger.error(f"Scheduler loop crashed: {e}", exc_info=True)
            raise

    def _scheduled_task(self) -> None:
        """
        Wrapper callback for scheduled pipeline runs.
        Catches internal pipeline exceptions to ensure the scheduler continues running forever.
        """
        logger.info("Scheduler task execution started.")
        try:
            stats = self.collection_service.run_sync()
            logger.info(f"Scheduler task completed. Current Run Stats: {stats}")
        except Exception as e:
            # Prevent schedule abortion by catching all high-level sync exceptions
            logger.error(f"Scheduler task run encountered fatal exception: {e}", exc_info=True)
