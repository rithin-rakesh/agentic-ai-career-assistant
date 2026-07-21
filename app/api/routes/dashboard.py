from datetime import datetime, time, timezone, timedelta
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from app.auth.authentication import get_current_user
from app.database.repository import JobRepository
from app.database.models import JobModel, ApplicationModel, ExecutionLogModel
from app.logger import logger

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

@router.get("")
def get_dashboard_metrics(
    repo: JobRepository = Depends(JobRepository),
    username: str = Depends(get_current_user)
):
    """
    Aggregates statistical KPIs and monitoring logs for dashboard widgets.
    """
    try:
        with repo.session_provider() as session:
            # 1. Jobs collected today (since midnight UTC)
            today_start = datetime.combine(datetime.now(timezone.utc).date(), time.min)
            today_jobs_query = select(func.count(JobModel.id)).where(JobModel.created_at >= today_start)
            jobs_today_count = session.execute(today_jobs_query).scalar() or 0
            
            # 2. High Priority jobs count
            high_priority_query = select(func.count(JobModel.id)).where(JobModel.priority == "High")
            high_priority_count = session.execute(high_priority_query).scalar() or 0
            
            # 3. Average match score (for jobs evaluated)
            avg_score_query = select(func.avg(JobModel.match_score)).where(JobModel.match_score != None)
            avg_score = session.execute(avg_score_query).scalar() or 0.0
            
            # 4. Total application packages generated (Draft, Applied, etc.)
            total_apps_query = select(func.count(ApplicationModel.id))
            total_apps_count = session.execute(total_apps_query).scalar() or 0
            
            # 5. Retrieve recent notification delivery logs
            from app.notifications.notification_models import NotificationModel
            notif_query = select(NotificationModel).order_by(NotificationModel.sent_at.desc()).limit(10)
            db_notifs = session.execute(notif_query).scalars().all()
            notifications = [
                {
                    "id": n.id,
                    "job_id": n.job_id,
                    "channel": n.channel,
                    "status": n.status,
                    "sent_at": n.sent_at,
                    "retry_count": n.retry_count,
                    "error_message": n.error_message
                }
                for n in db_notifs
            ]

            # 6. Retrieve recent node execution logs for observability
            exec_query = select(ExecutionLogModel).order_by(ExecutionLogModel.created_at.desc()).limit(15)
            db_logs = session.execute(exec_query).scalars().all()
            executions = [
                {
                    "id": l.id,
                    "node_name": l.node_name,
                    "duration": l.duration,
                    "status": l.status,
                    "error_message": l.error_message,
                    "created_at": l.created_at
                }
                for l in db_logs
            ]
            
            # Get background scheduler status
            from app.api.app import scheduler_instance
            scheduler_active = False
            next_run_time = None
            if scheduler_instance:
                scheduler_active = scheduler_instance.running
                job = scheduler_instance.get_job('periodic_job_sync')
                if job:
                    next_run_time = job.next_run_time

            return {
                "metrics": {
                    "jobs_today": jobs_today_count,
                    "high_priority_count": high_priority_count,
                    "average_match_score": round(avg_score, 1),
                    "applications_count": total_apps_count,
                },
                "scheduler": {
                    "active": scheduler_active,
                    "next_run_time": next_run_time.isoformat() if next_run_time else None
                },
                "notifications": notifications,
                "executions": executions
            }
            
    except Exception as e:
        logger.error(f"Dashboard metrics query failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query dashboard analytics: {e}"
        )
