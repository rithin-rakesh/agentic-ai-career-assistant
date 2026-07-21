import json
import os
import sys
from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI, Request, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from apscheduler.schedulers.background import BackgroundScheduler

# Ensure root of project is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.config import settings
from app.logger import setup_logging, logger
from app.database.repository import JobRepository
from app.database.models import Base, JobModel, ApplicationModel, ExecutionLogModel
from app.auth.authentication import (
    get_current_user, verify_password, create_access_token, 
    DEFAULT_USERNAME, DEFAULT_PASSWORD_HASH
)

# Initialize logging
setup_logging(level=settings.LOG_LEVEL)

# Global background scheduler instance reference
scheduler_instance: Optional[BackgroundScheduler] = None

app = FastAPI(
    title="Agentic Career Assistant API & Dashboard",
    description="Day 8 - Web Control Center and API Dashboard",
    version="1.0.0"
)

# Add Monitoring & Correlation ID Middleware
from app.monitoring.middleware import CorrelationIDMiddleware
from app.monitoring.metrics import metrics_response
from app.monitoring.sentry import init_sentry

app.add_middleware(CorrelationIDMiddleware)
init_sentry()

@app.get("/metrics", include_in_schema=False)
def get_prometheus_metrics():
    return metrics_response()

# Configure Jinja2 templates directory
templates = Jinja2Templates(directory=os.path.join(settings.BASE_DIR, "app", "dashboard", "templates"))

# --- 1. Mount API routers ---
from app.api.routes.jobs import router as jobs_router
from app.api.routes.resume import router as resume_router
from app.api.routes.applications import router as applications_router
from app.api.routes.settings import router as settings_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.health import router as health_router
from app.api.routes.career_strategy import router as career_strategy_router
from app.api.routes.scheduler import router as scheduler_router

app.include_router(jobs_router)
app.include_router(resume_router)
app.include_router(applications_router)
app.include_router(settings_router)
app.include_router(dashboard_router)
app.include_router(health_router)
app.include_router(career_strategy_router)
app.include_router(scheduler_router)

# --- 2. HTML Page Handlers ---

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    """
    Renders login view. Redirects to dashboard if already authenticated.
    """
    token = request.cookies.get("access_token")
    if token:
        from app.auth.authentication import verify_access_token
        if verify_access_token(token):
            return RedirectResponse(url="/dashboard", status_code=303)
            
    return templates.TemplateResponse(request=request, name="login.html", context={"error": None})

@app.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    """
    Validates login credentials, writes JWT access token cookie, and redirects.
    """
    if username != DEFAULT_USERNAME or not verify_password(password, DEFAULT_PASSWORD_HASH):
        return templates.TemplateResponse(
            request=request,
            name="login.html", 
            context={"error": "Invalid username or password credentials."}
        )
        
    # Generate JWT token
    access_token = create_access_token(data={"sub": username})
    
    response = RedirectResponse(url="/dashboard", status_code=303)
    # Store token in cookie
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=120 * 60, # 2 hours
        samesite="lax"
    )
    return response

@app.get("/logout")
def logout():
    """
    Clears session tokens and redirects to login.
    """
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("access_token")
    return response

@app.get("/", response_class=HTMLResponse)
def root_redirect():
    return RedirectResponse(url="/dashboard", status_code=303)

@app.get("/dashboard", response_class=HTMLResponse)
def get_dashboard_html(
    request: Request,
    repo: JobRepository = Depends(JobRepository)
):
    """
    Renders main dashboard overview page. Enforces authentication.
    """
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url="/login", status_code=303)
        
    from app.auth.authentication import verify_access_token
    username = verify_access_token(token)
    if not username:
        return RedirectResponse(url="/login", status_code=303)

    # 1. Fetch dashboard metrics from API endpoint function directly for compatibility
    from app.api.routes.dashboard import get_dashboard_metrics
    try:
        metrics_payload = get_dashboard_metrics(repo=repo, username=username)
    except Exception as e:
        metrics_payload = {
            "metrics": {"jobs_today": 0, "high_priority_count": 0, "average_match_score": 0.0, "applications_count": 0},
            "scheduler": {"active": False, "next_run_time": None},
            "notifications": [],
            "executions": []
        }

    # 2. Query recent jobs list from SQLite
    jobs = repo.get_all_jobs()
    # Sort by score desc, latest first
    jobs = sorted([j for j in jobs if j.match_score is not None], key=lambda x: x.match_score, reverse=True)[:10]

    # 3. Query applications approvals lists from SQLite
    from app.api.routes.applications import get_applications
    applications = get_applications(status_filter=None, limit=10, offset=0, repo=repo, username=username)

    return templates.TemplateResponse(request=request, name="dashboard.html", context={
        "metrics": metrics_payload["metrics"],
        "scheduler": metrics_payload["scheduler"],
        "executions": metrics_payload["executions"],
        "notifications": metrics_payload["notifications"],
        "jobs": jobs,
        "applications": applications
    })

@app.get("/analytics", response_class=HTMLResponse)
def get_analytics_html(
    request: Request,
    repo: JobRepository = Depends(JobRepository)
):
    """
    Renders career strategy decisions, preferences weights, learning metrics.
    """
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url="/login", status_code=303)
        
    from app.auth.authentication import verify_access_token
    username = verify_access_token(token)
    if not username:
        return RedirectResponse(url="/login", status_code=303)

    from app.agents.preference_agent import PreferenceAgent
    pref_agent = PreferenceAgent(repo)
    
    # 1. Fetch dynamic preferences category scores
    preferences = {
        "technology": pref_agent.get_category_preferences("technology"),
        "location": pref_agent.get_category_preferences("location"),
        "remote_pref": pref_agent.get_category_preferences("remote_pref")
    }

    # Sort preferences values descending
    preferences["technology"] = dict(sorted(preferences["technology"].items(), key=lambda x: x[1], reverse=True)[:10])
    preferences["location"] = dict(sorted(preferences["location"].items(), key=lambda x: x[1], reverse=True)[:5])
    preferences["remote_pref"] = dict(sorted(preferences["remote_pref"].items(), key=lambda x: x[1], reverse=True))

    # 2. Fetch company intelligence profiles
    companies = repo.get_company_profiles()

    # 3. Fetch learning metrics & logs
    learning_logs = repo.get_learning_metrics()
    latest_metric = learning_logs[0] if learning_logs else {
        "accepted_recommendations": 0, "ignored_recommendations": 0,
        "interview_conversion_rate": 0.0, "offer_conversion_rate": 0.0
    }

    # 4. Fetch career strategy decisions
    decisions = []
    try:
        with repo.session_provider() as session:
            from app.database.models import CareerDecisionModel, JobModel
            from sqlalchemy import select
            query = select(CareerDecisionModel, JobModel).join(JobModel, CareerDecisionModel.job_id == JobModel.id).order_by(CareerDecisionModel.created_at.desc()).limit(15)
            results = session.execute(query).all()
            for dec_mod, job_mod in results:
                decisions.append({
                    "job_title": job_mod.title,
                    "company": job_mod.company,
                    "recommendation": dec_mod.recommendation,
                    "priority": dec_mod.priority,
                    "confidence": dec_mod.confidence,
                    "estimated_interview_probability": dec_mod.estimated_interview_probability,
                    "career_growth": dec_mod.career_growth,
                    "reasoning": json.loads(dec_mod.reasoning) if dec_mod.reasoning else [],
                    "missing_skills": json.loads(dec_mod.missing_skills) if dec_mod.missing_skills else []
                })
    except Exception as e:
        logger.error(f"Failed to query decisions for analytics HTML: {e}", exc_info=True)

    return templates.TemplateResponse(
        request=request,
        name="analytics.html",
        context={
            "preferences": preferences,
            "companies": companies,
            "learning_logs": learning_logs,
            "latest_metric": latest_metric,
            "decisions": decisions
        }
    )

@app.get("/jobs/{job_id}", response_class=HTMLResponse)
def get_job_detail_html(
    job_id: int,
    request: Request,
    repo: JobRepository = Depends(JobRepository)
):
    """
    Renders job matching details and covers human approval document actions.
    """
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url="/login", status_code=303)
        
    from app.auth.authentication import verify_access_token
    username = verify_access_token(token)
    if not username:
        return RedirectResponse(url="/login", status_code=303)

    try:
        # 1. Query job by ID
        from app.api.routes.jobs import get_job_by_id
        job = get_job_by_id(job_id=job_id, repo=repo, username=username)
        
        # 2. Query application record
        app_record = repo.get_application_by_job_id(job_id)
        
        # 3. Parse JSON strings back to lists
        strengths = job.strengths or []
        missing_skills = job.missing_skills or []
        
        # 4. Fetch document text contents for previewing
        resume_preview = ""
        cover_letter_preview = ""
        if app_record and app_record.status != "Pending Approval":
            # Resume markdown preview
            if app_record.resume_path:
                md_path = os.path.splitext(app_record.resume_path)[0] + ".md"
                if os.path.exists(md_path):
                    with open(md_path, "r", encoding="utf-8") as f:
                        resume_preview = f.read()
            # Cover Letter markdown preview
            if app_record.cover_letter_path:
                md_path = os.path.splitext(app_record.cover_letter_path)[0] + ".md"
                if os.path.exists(md_path):
                    with open(md_path, "r", encoding="utf-8") as f:
                        cover_letter_preview = f.read()

        return templates.TemplateResponse(request=request, name="job_detail.html", context={
            "job": job,
            "app": app_record,
            "strengths": strengths,
            "missing_skills": missing_skills,
            "resume_preview": resume_preview,
            "cover_letter_preview": cover_letter_preview
        })
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch job details page: {e}"
        )

@app.get("/settings", response_class=HTMLResponse)
def get_settings_html(
    request: Request,
    repo: JobRepository = Depends(JobRepository)
):
    """
    Renders configuration settings edit page. Enforces authentication.
    """
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url="/login", status_code=303)
        
    from app.auth.authentication import verify_access_token
    username = verify_access_token(token)
    if not username:
        return RedirectResponse(url="/login", status_code=303)

    from app.api.routes.settings import get_current_settings
    from app.api.routes.resume import get_resume_status
    from app.scheduler.scheduler_manager import scheduler_manager

    current = get_current_settings(repo=repo, username=username)
    resume_status = get_resume_status(repo=repo, username=username)
    scheduler_status = scheduler_manager.get_status_dict()

    context = {**current, "resume_status": resume_status, "scheduler_status": scheduler_status}
    return templates.TemplateResponse(request=request, name="settings.html", context=context)

@app.get("/system-status", response_class=HTMLResponse)
def get_system_status_html(
    request: Request,
    repo: JobRepository = Depends(JobRepository)
):
    """
    Renders live system status & component health monitoring dashboard. Enforces authentication.
    """
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url="/login", status_code=303)
        
    from app.auth.authentication import verify_access_token
    username = verify_access_token(token)
    if not username:
        return RedirectResponse(url="/login", status_code=303)

    from app.api.routes.health import health_check
    health_data = health_check(repo=repo)

    return templates.TemplateResponse(
        request=request,
        name="system_status.html",
        context={"health_data": health_data}
    )

# --- 3. Startup & Shutdown Events ---

@app.on_event("startup")
def app_startup():
    """
    FastAPI startup routine:
    - Runs DB schema creations.
    - Initializes the APScheduler BackgroundScheduler daemon to sync jobs.
    """
    # 1. Setup repository and migrate tables
    repo = JobRepository()
    repo.create_database()
    
    # 2. Register Background Scraper Task
    from app.collectors.wellfound import WellfoundCollector
    from app.collectors.indeed import IndeedCollector
    from app.collectors.naukri import NaukriCollector
    from app.collectors.remoteok import RemoteOKCollector
    from app.collectors.arbeitnow import ArbeitnowCollector
    from app.collectors.remotive import RemotiveCollector
    from app.collectors.collector_manager import CollectorManager
    from app.services.filtering import FilteringService
    from app.services.rag_matching_service import RAGMatchingService
    from app.services.collection_service import CollectionService
    
    manager = CollectorManager()
    manager.register_collector(RemoteOKCollector())
    manager.register_collector(ArbeitnowCollector())
    manager.register_collector(RemotiveCollector())
    manager.register_collector(WellfoundCollector())
    manager.register_collector(IndeedCollector())
    manager.register_collector(NaukriCollector())
    
    filtering_service = FilteringService()
    ai_matching_service = RAGMatchingService(repository=repo)
    
    collection_service = CollectionService(
        repository=repo, 
        collector_manager=manager, 
        filtering_service=filtering_service,
        ai_matching_service=ai_matching_service
    )
    
    def scheduled_sync_task():
        logger.info("Background Job Sync: Commencing periodic execution.")
        try:
            if settings.USE_CELERY:
                from app.workers.tasks import run_job_collection_pipeline
                run_job_collection_pipeline.delay()
                logger.info("Background Job Sync: Dispatched job to Celery worker queue.")
                return {"collected": 0, "status": "dispatched_celery"}
            else:
                stats = collection_service.run_sync()
                logger.info(f"Background Job Sync: Success. Stats: {stats}")
                return stats
        except Exception as e:
            logger.error(f"Background Job Sync: Failed with exception: {e}", exc_info=True)
            return {"collected": 0, "error": str(e)}
            
    # 3. Setup SchedulerManager Singleton
    from app.scheduler.scheduler_manager import scheduler_manager
    scheduler_manager.initialize(
        sync_callback=scheduled_sync_task,
        interval_hours=settings.COLLECTION_INTERVAL_HOURS
    )
    logger.info(f"SchedulerManager daemon initialized. Interval: every {settings.COLLECTION_INTERVAL_HOURS} hour(s).")

@app.on_event("shutdown")
def app_shutdown():
    from app.scheduler.scheduler_manager import scheduler_manager
    if scheduler_manager.scheduler:
        logger.info("Shutting down background scheduler daemon...")
        scheduler_manager.scheduler.shutdown()

if __name__ == "__main__":
    import uvicorn
    # Start ASGI server on port 8000
    uvicorn.run("app.api.app:app", host="127.0.0.1", port=8000, reload=True)
