from typing import Optional
from sqlalchemy import select
from app.database.database import get_db_session
from app.database.models import JobModel
from app.notifications.notification_models import NotificationModel
from app.logger import logger

class NotificationRepository:
    """
    Repository layer wrapping notification logs and delivery histories inside SQLite.
    Protects the system from sending duplicate alerts for the same job URL.
    """
    def __init__(self, session_provider=None):
        self.session_provider = session_provider or get_db_session

    def log_notification(self, job_id: int, channel: str, status: str, sent_at=None, retry_count: int = 0, error_message: Optional[str] = None) -> NotificationModel:
        """
        Creates and logs a notification execution entry in SQLite.
        """
        db_record = NotificationModel(
            job_id=job_id,
            channel=channel,
            status=status,
            sent_at=sent_at,
            retry_count=retry_count,
            error_message=error_message
        )
        try:
            with self.session_provider() as session:
                session.add(db_record)
                session.flush()
                session.refresh(db_record)
                logger.info(f"NotificationRepository: Logged status '{status}' for Job ID {job_id} under Channel '{channel}'")
                return db_record
        except Exception as e:
            logger.error(f"NotificationRepository: Failed to write log for Job ID {job_id}: {e}", exc_info=True)
            raise

    def has_been_notified(self, job_url: str) -> bool:
        """
        Queries database history to check if a job URL has already been notified.
        Returns True if a successful ('sent') notification log exists.
        """
        try:
            with self.session_provider() as session:
                query = select(NotificationModel.id).join(NotificationModel.job).where(
                    JobModel.job_url == job_url,
                    NotificationModel.status == "sent"
                )
                result = session.execute(query).scalar_one_or_none()
                return result is not None
        except Exception as e:
            logger.error(f"NotificationRepository: Query error checking notification status for URL {job_url}: {e}", exc_info=True)
            return False
