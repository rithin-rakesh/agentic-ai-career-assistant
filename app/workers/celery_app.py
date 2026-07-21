import os
from celery import Celery
from app.config import settings

# Initialize Celery app instance
celery_app = Celery(
    "job_agent_workers",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.workers.tasks"]
)

# Celery Configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=1800, # 30 minutes max per task
    worker_prefetch_multiplier=1,
)
