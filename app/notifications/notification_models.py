from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database.models import Base

class NotificationModel(Base):
    """
    SQLAlchemy ORM model representing the 'notifications' table.
    Tracks delivery logs, channels, statuses, and retry attempts for job recommendations.
    """
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    channel = Column(String, nullable=False, default="email")
    status = Column(String, nullable=False)           # 'sent', 'failed', 'skipped', 'queued'
    sent_at = Column(DateTime, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Establish ORM relationship link to JobModel
    job = relationship("JobModel", backref="notifications")

    def __repr__(self) -> str:
        return f"<NotificationModel(id={self.id}, job_id={self.job_id}, channel='{self.channel}', status='{self.status}', sent_at={self.sent_at})>"
