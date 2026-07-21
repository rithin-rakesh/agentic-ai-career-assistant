from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from app.auth.authentication import get_current_user
from app.scheduler.scheduler_manager import scheduler_manager
from app.logger import logger

router = APIRouter(prefix="/api/scheduler", tags=["Scheduler"])

class RescheduleRequest(BaseModel):
    interval_hours: Optional[int] = None

@router.get("/status")
def get_scheduler_status(
    username: str = Depends(get_current_user)
):
    """
    Returns current background scheduler status, execution counters, last run, and next run timestamps.
    """
    return scheduler_manager.get_status_dict()

@router.post("/start")
def start_scheduler(
    username: str = Depends(get_current_user)
):
    """
    Starts or resumes the background scheduler daemon.
    """
    try:
        scheduler_manager.start()
        return {
            "status": "success",
            "message": "Background scheduler daemon started successfully.",
            "data": scheduler_manager.get_status_dict()
        }
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start scheduler: {e}"
        )

@router.post("/pause")
def pause_scheduler(
    username: str = Depends(get_current_user)
):
    """
    Pauses periodic job execution.
    """
    try:
        scheduler_manager.pause()
        return {
            "status": "success",
            "message": "Background scheduler daemon paused.",
            "data": scheduler_manager.get_status_dict()
        }
    except Exception as e:
        logger.error(f"Failed to pause scheduler: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to pause scheduler: {e}"
        )

@router.post("/resume")
def resume_scheduler(
    username: str = Depends(get_current_user)
):
    """
    Resumes paused periodic job execution.
    """
    try:
        scheduler_manager.resume()
        return {
            "status": "success",
            "message": "Background scheduler daemon resumed.",
            "data": scheduler_manager.get_status_dict()
        }
    except Exception as e:
        logger.error(f"Failed to resume scheduler: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resume scheduler: {e}"
        )

@router.post("/restart")
def restart_scheduler(
    payload: Optional[RescheduleRequest] = None,
    username: str = Depends(get_current_user)
):
    """
    Restarts background scheduler daemon with updated interval.
    """
    try:
        interval = payload.interval_hours if payload and payload.interval_hours else None
        scheduler_manager.restart(interval_hours=interval)
        return {
            "status": "success",
            "message": "Background scheduler daemon restarted.",
            "data": scheduler_manager.get_status_dict()
        }
    except Exception as e:
        logger.error(f"Failed to restart scheduler: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to restart scheduler: {e}"
        )

@router.post("/run-now")
def run_now_scheduler(
    username: str = Depends(get_current_user)
):
    """
    Triggers an immediate job collection and matching execution.
    """
    try:
        stats = scheduler_manager.run_now()
        return {
            "status": "success",
            "message": "Manual job collection executed successfully.",
            "stats": stats,
            "data": scheduler_manager.get_status_dict()
        }
    except Exception as e:
        logger.error(f"Manual job collection run failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Job collection failed: {e}"
        )
