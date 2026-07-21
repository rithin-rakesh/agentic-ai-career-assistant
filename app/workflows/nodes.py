import os
import time
import json
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy import select

from app.config import settings
from app.workflows.state import GraphState
from app.agents.collector_agent import CollectorAgent
from app.agents.filtering_agent import FilteringAgent
from app.agents.retrieval_agent import RetrievalAgent
from app.agents.matching_agent import MatchingAgent
from app.agents.ranking_agent import RankingAgent
from app.agents.persistence_agent import PersistenceAgent
from app.agents.notification_agent import NotificationAgent
from app.agents.application_agent import ApplicationAgent
from app.agents.feedback_agent import FeedbackAgent
from app.agents.learning_agent import LearningAgent
from app.agents.preference_agent import PreferenceAgent
from app.agents.career_strategy_agent import CareerStrategyAgent
from app.agents.recommendation_agent import RecommendationAgent
from app.logger import logger

class GraphNodeOrchestrator:
    """
    Orchestrator wrapping agent executions as LangGraph nodes.
    Maintains clean state mapping, captures errors inside nodes, and
    supplies performance timing and token usage logs to database execution logs.
    """
    def __init__(self, collector: CollectorAgent, filtering: FilteringAgent, retrieval: RetrievalAgent, matching: MatchingAgent, ranking: RankingAgent, persistence: PersistenceAgent, notification: NotificationAgent = None, application: ApplicationAgent = None, feedback_agent: FeedbackAgent = None, learning_agent: LearningAgent = None, strategy_agent: CareerStrategyAgent = None, recommendation_agent: RecommendationAgent = None):
        self.collector = collector
        self.filtering = filtering
        self.retrieval = retrieval
        self.matching = matching
        self.ranking = ranking
        self.persistence = persistence
        self.notification = notification
        self.application = application
        repo = getattr(persistence, "repository", None)
        self.feedback_agent = feedback_agent or FeedbackAgent(repo)
        self.learning_agent = learning_agent or LearningAgent(repo)
        self.strategy_agent = strategy_agent or CareerStrategyAgent(repository=repo)
        self.recommendation_agent = recommendation_agent or RecommendationAgent(repo)

    def _log_execution(self, node_name: str, start_time: datetime, end_time: datetime, status: str, error_message: str = None) -> None:
        """
        Safely logs performance execution metrics. Checks for mocked repository instances.
        """
        repo = getattr(self.persistence, "repository", None)
        if repo and hasattr(repo, "log_node_execution"):
            try:
                repo.log_node_execution(node_name, start_time, end_time, status, error_message)
            except Exception as e:
                logger.debug(f"Failed to log node performance metrics for {node_name}: {e}")

    def collect_jobs_node(self, state: GraphState) -> Dict[str, Any]:
        node_name = "collect_jobs_node"
        logger.info(f"Node execution started: {node_name}")
        start_time = datetime.now(timezone.utc)
        
        errors = list(state.get("errors", []))
        stats = dict(state.get("statistics", {}))
        
        try:
            raw_jobs, failed_count = self.collector.collect()
            stats["failed_collectors"] = failed_count
            
            end_time = datetime.now(timezone.utc)
            self._log_execution(node_name, start_time, end_time, "success")
            
            return {
                "jobs": raw_jobs,
                "statistics": stats,
                "current_step": node_name
            }
        except Exception as e:
            err_msg = f"collect_jobs_node failed: {e}"
            logger.error(err_msg, exc_info=True)
            errors.append(err_msg)
            stats["failed_collectors"] = 0
            
            end_time = datetime.now(timezone.utc)
            self._log_execution(node_name, start_time, end_time, "failure", error_message=str(e))
            
            return {
                "jobs": [],
                "errors": errors,
                "statistics": stats,
                "current_step": node_name
            }

    def filter_jobs_node(self, state: GraphState) -> Dict[str, Any]:
        node_name = "filter_jobs_node"
        logger.info(f"Node execution started: {node_name}")
        start_time = datetime.now(timezone.utc)
        
        errors = list(state.get("errors", []))
        stats = dict(state.get("statistics", {}))
        
        raw_jobs = state.get("jobs", [])
        if not raw_jobs:
            logger.info("filter_jobs_node: No jobs collected to filter.")
            end_time = datetime.now(timezone.utc)
            self._log_execution(node_name, start_time, end_time, "success")
            return {
                "filtered_jobs": [],
                "current_step": node_name
            }
            
        try:
            filtered_jobs, rule_filtered, duplicate_count = self.filtering.filter_jobs(raw_jobs)
            stats["collected"] = len(raw_jobs)
            stats["filtered"] = rule_filtered
            stats["duplicates"] = duplicate_count
            
            end_time = datetime.now(timezone.utc)
            self._log_execution(node_name, start_time, end_time, "success")
            
            return {
                "filtered_jobs": filtered_jobs,
                "statistics": stats,
                "current_step": node_name
            }
        except Exception as e:
            err_msg = f"filter_jobs_node failed: {e}"
            logger.error(err_msg, exc_info=True)
            errors.append(err_msg)
            
            end_time = datetime.now(timezone.utc)
            self._log_execution(node_name, start_time, end_time, "failure", error_message=str(e))
            
            return {
                "filtered_jobs": [],
                "errors": errors,
                "current_step": node_name
            }

    def retrieve_context_node(self, state: GraphState) -> Dict[str, Any]:
        node_name = "retrieve_context_node"
        logger.info(f"Node execution started: {node_name}")
        start_time = datetime.now(timezone.utc)
        
        errors = list(state.get("errors", []))
        metadata = dict(state.get("execution_metadata", {}))
        
        filtered = state.get("filtered_jobs", [])
        if not filtered:
            logger.info("retrieve_context_node: No jobs passed filtering. Skipping retrieval.")
            end_time = datetime.now(timezone.utc)
            self._log_execution(node_name, start_time, end_time, "success")
            return {
                "retrieved_context": {},
                "current_step": node_name
            }
            
        try:
            contexts, metrics = self.retretrieval_agent_run(filtered)
            metadata["retrieval_metrics"] = metrics
            
            end_time = datetime.now(timezone.utc)
            self._log_execution(node_name, start_time, end_time, "success")
            
            return {
                "retrieved_context": contexts,
                "execution_metadata": metadata,
                "current_step": node_name
            }
        except Exception as e:
            err_msg = f"retrieve_context_node failed: {e}"
            logger.error(err_msg, exc_info=True)
            errors.append(err_msg)
            
            end_time = datetime.now(timezone.utc)
            self._log_execution(node_name, start_time, end_time, "failure", error_message=str(e))
            
            return {
                "retrieved_context": {},
                "errors": errors,
                "current_step": node_name
            }

    def retretrieval_agent_run(self, jobs: List[Dict[str, Any]]) -> tuple:
        return self.retrieval.retrieve(jobs)

    def match_jobs_node(self, state: GraphState) -> Dict[str, Any]:
        node_name = "match_jobs_node"
        logger.info(f"Node execution started: {node_name}")
        start_time = datetime.now(timezone.utc)
        
        errors = list(state.get("errors", []))
        metadata = dict(state.get("execution_metadata", {}))
        
        attempts = dict(metadata.get("attempts", {}))
        current_results = dict(state.get("match_results", {}))
        filtered = state.get("filtered_jobs", [])
        contexts = state.get("retrieved_context", {})
        
        if not filtered:
            end_time = datetime.now(timezone.utc)
            self._log_execution(node_name, start_time, end_time, "success")
            return {
                "match_results": {},
                "current_step": node_name
            }
            
        try:
            for job in filtered:
                url = job.get("job_url", "")
                if url:
                    if url in current_results:
                        attempts[url] = attempts.get(url, 0) + 1
                    else:
                        attempts[url] = attempts.get(url, 0)
            
            metadata["attempts"] = attempts
            
            updated_results = self.matching.match_jobs(
                filtered_jobs=filtered,
                retrieved_contexts=contexts,
                current_results=current_results,
                attempts=attempts
            )
            
            end_time = datetime.now(timezone.utc)
            self._log_execution(node_name, start_time, end_time, "success")
            
            return {
                "match_results": updated_results,
                "execution_metadata": metadata,
                "current_step": node_name
            }
        except Exception as e:
            err_msg = f"match_jobs_node failed: {e}"
            logger.error(err_msg, exc_info=True)
            errors.append(err_msg)
            
            end_time = datetime.now(timezone.utc)
            self._log_execution(node_name, start_time, end_time, "failure", error_message=str(e))
            
            return {
                "errors": errors,
                "current_step": node_name
            }

    def rank_jobs_node(self, state: GraphState) -> Dict[str, Any]:
        node_name = "rank_jobs_node"
        logger.info(f"Node execution started: {node_name}")
        start_time = datetime.now(timezone.utc)
        
        errors = list(state.get("errors", []))
        filtered = state.get("filtered_jobs", [])
        results = state.get("match_results", {})
        
        if not filtered:
            end_time = datetime.now(timezone.utc)
            self._log_execution(node_name, start_time, end_time, "success")
            return {
                "ranked_jobs": [],
                "current_step": node_name
            }
            
        try:
            ranked_jobs = self.ranking.rank_jobs(filtered, results)
            
            end_time = datetime.now(timezone.utc)
            self._log_execution(node_name, start_time, end_time, "success")
            
            return {
                "ranked_jobs": ranked_jobs,
                "current_step": node_name
            }
        except Exception as e:
            err_msg = f"rank_jobs_node failed: {e}"
            logger.error(err_msg, exc_info=True)
            errors.append(err_msg)
            
            end_time = datetime.now(timezone.utc)
            self._log_execution(node_name, start_time, end_time, "failure", error_message=str(e))
            
            return {
                "ranked_jobs": [],
                "errors": errors,
                "current_step": node_name
            }

    def persist_jobs_node(self, state: GraphState) -> Dict[str, Any]:
        node_name = "persist_jobs_node"
        logger.info(f"Node execution started: {node_name}")
        start_time = datetime.now(timezone.utc)
        
        errors = list(state.get("errors", []))
        stats = dict(state.get("statistics", {}))
        metadata = state.get("execution_metadata", {})
        retrieval_metrics = metadata.get("retrieval_metrics", {})
        notification_records = state.get("notification_records", [])
        application_packages = state.get("application_packages", [])
        
        ranked = state.get("ranked_jobs", [])
        if not ranked:
            logger.info("persist_jobs_node: No evaluated jobs to save to SQLite database.")
            end_time = datetime.now(timezone.utc)
            self._log_execution(node_name, start_time, end_time, "success")
            return {
                "current_step": node_name
            }
            
        try:
            inserted, duplicates = self.persistence.persist_jobs(
                ranked, 
                retrieval_metrics, 
                notification_records, 
                application_packages
            )
            stats["inserted"] = inserted
            stats["duplicates"] = stats.get("duplicates", 0) + duplicates
            
            end_time = datetime.now(timezone.utc)
            self._log_execution(node_name, start_time, end_time, "success")
            
            return {
                "statistics": stats,
                "current_step": node_name
            }
        except Exception as e:
            err_msg = f"persist_jobs_node failed: {e}"
            logger.error(err_msg, exc_info=True)
            errors.append(err_msg)
            
            end_time = datetime.now(timezone.utc)
            self._log_execution(node_name, start_time, end_time, "failure", error_message=str(e))
            
            return {
                "errors": errors,
                "current_step": node_name
            }

    def notification_jobs_node(self, state: GraphState) -> Dict[str, Any]:
        node_name = "notification_jobs_node"
        logger.info(f"Node execution started: {node_name}")
        start_time = datetime.now(timezone.utc)
        
        errors = list(state.get("errors", []))
        ranked = state.get("ranked_jobs", [])
        
        if not ranked:
            logger.info("notification_jobs_node: No ranked jobs to process alerts for.")
            end_time = datetime.now(timezone.utc)
            self._log_execution(node_name, start_time, end_time, "success")
            return {
                "notification_records": [],
                "current_step": node_name
            }
            
        try:
            records = self.notification.evaluate_and_notify(ranked)
            
            end_time = datetime.now(timezone.utc)
            self._log_execution(node_name, start_time, end_time, "success")
            
            return {
                "notification_records": records,
                "current_step": node_name
            }
        except Exception as e:
            err_msg = f"notification_jobs_node failed: {e}"
            logger.error(err_msg, exc_info=True)
            errors.append(err_msg)
            
            end_time = datetime.now(timezone.utc)
            self._log_execution(node_name, start_time, end_time, "failure", error_message=str(e))
            
            return {
                "notification_records": [],
                "errors": errors,
                "current_step": node_name
            }

    def application_jobs_node(self, state: GraphState) -> Dict[str, Any]:
        node_name = "application_jobs_node"
        logger.info(f"Node execution started: {node_name}")
        start_time = datetime.now(timezone.utc)
        
        errors = list(state.get("errors", []))
        ranked = state.get("ranked_jobs", [])
        retrieved_context = state.get("retrieved_context", {})
        
        if not ranked:
            logger.info("application_jobs_node: No ranked jobs to compile packages for.")
            end_time = datetime.now(timezone.utc)
            self._log_execution(node_name, start_time, end_time, "success")
            return {
                "application_packages": [],
                "current_step": node_name
            }
            
        repo = getattr(self.persistence, "repository", None)
        
        try:
            packages = []
            
            # If repo is missing (e.g. mock test environment), fall back to immediate generation
            if not repo or not hasattr(repo, "get_job_by_url"):
                logger.info("application_jobs_node: Repository missing/mocked. Processing immediate compilation.")
                packages = self.application.prepare_applications(ranked, retrieved_context)
                
                end_time = datetime.now(timezone.utc)
                self._log_execution(node_name, start_time, end_time, "success")
                return {
                    "application_packages": packages,
                    "current_step": node_name
                }

            # Read original resume
            original_resume = ""
            try:
                if os.path.exists(settings.RESUME_TEMPLATE):
                    with open(settings.RESUME_TEMPLATE, "r", encoding="utf-8") as f:
                        original_resume = f.read()
                else:
                    original_resume = "# Candidate Profile\n\n- Experience: Junior ML Engineer (1.5 years)\n- Skills: Python, SQL"
            except Exception:
                original_resume = "# Candidate Profile\n\n- Experience: Junior ML Engineer\n- Skills: Python, SQL"

            for job_dict in ranked:
                priority = job_dict.get("priority", "Low")
                score = job_dict.get("match_score", 0)
                
                is_high_priority = (priority == "High") or (score >= settings.INSTANT_THRESHOLD)
                if not is_high_priority:
                    continue

                job_url = job_dict.get("job_url", "")
                company = job_dict.get("company", "Unknown Company")
                title = job_dict.get("title", "Unknown Title")

                # Fetch/Insert DB Job record first
                db_job = repo.get_job_by_url(job_url)
                if not db_job:
                    from app.schemas.job import JobCreate
                    job_create = JobCreate(
                        title=title,
                        company=company,
                        location=job_dict.get("location", "Remote"),
                        job_url=job_url,
                        description=job_dict.get("description", "No description provided"),
                        source=job_dict.get("source", "Unknown"),
                        date_posted=datetime.now(timezone.utc)
                    )
                    db_job = repo.insert_job(job_create)

                # Fetch Application tracking record
                db_app = repo.get_application_by_job_id(db_job.id)

                if not db_app:
                    # HUMAN APPROVAL STEP: Initialize status as "Pending Approval"
                    db_app = repo.create_application(
                        job_id=db_job.id,
                        company=company,
                        position=title,
                        status="Pending Approval"
                    )
                    logger.info(f"Human Approval: Initialized pending review record for '{title}' at '{company}'")
                
                # Check status
                if db_app.status in ["Approved", "Regenerate"]:
                    logger.info(f"Human Approval: Processing approved compilation for '{title}' at '{company}'...")
                    context = retrieved_context.get(job_url, "Skills: Python")
                    
                    # Tailor Resume
                    tailored_resume_md = self.application.resume_agent.tailor_resume(original_resume, job_dict)
                    
                    url_hash = hashlib.md5(job_url.encode("utf-8")).hexdigest()[:8]
                    clean_company = "".join(c for c in company.replace(" ", "_") if c.isalnum() or c == "_")
                    clean_title = "".join(c for c in title.replace(" ", "_") if c.isalnum() or c == "_")
                    folder_name = f"{clean_company}_{clean_title}_{url_hash}"
                    
                    out_dir = os.path.join(settings.OUTPUT_DIRECTORY, folder_name)
                    os.makedirs(out_dir, exist_ok=True)

                    resume_base_path = os.path.join(out_dir, "resume_tailored")
                    resume_files = self.application.resume_doc_gen.generate(tailored_resume_md, resume_base_path)
                    res_path = resume_files.get("pdf") or resume_files.get("docx") or resume_files.get("markdown")
                    
                    # Tailor Cover Letter
                    cover_letter_md = self.application.cl_agent.generate_cover_letter(context, job_dict)
                    cl_base_path = os.path.join(out_dir, "cover_letter")
                    cl_files = self.application.cl_doc_gen.generate(cover_letter_md, cl_base_path)
                    cov_path = cl_files.get("pdf") or cl_files.get("docx") or cl_files.get("markdown")

                    # Generate Learning Roadmap
                    learning_plan = self.application.skills_agent.generate_learning_plan(context, job_dict)
                    lp_path = os.path.join(out_dir, "learning_plan.json")
                    with open(lp_path, "w", encoding="utf-8") as f:
                        json.dump(learning_plan, f, indent=4)

                    # Update Database Status to Draft and update path columns
                    with repo.session_provider() as session:
                        from app.database.models import ApplicationModel
                        active_app = session.get(ApplicationModel, db_app.id)
                        active_app.status = "Draft"
                        active_app.resume_path = res_path
                        active_app.cover_letter_path = cov_path
                    
                    # Update memory cache
                    self.application.memory.add_applied_job(job_url, company, title, "Draft", res_path, cov_path)

                    packages.append({
                        "job_url": job_url,
                        "company": company,
                        "position": title,
                        "status": "Draft",
                        "resume_path": res_path,
                        "cover_letter_path": cov_path,
                        "learning_plan_path": lp_path
                    })
                elif db_app.status not in ["Pending Approval"]:
                    # Return cached records
                    packages.append({
                        "job_url": job_url,
                        "company": company,
                        "position": title,
                        "status": db_app.status,
                        "resume_path": db_app.resume_path,
                        "cover_letter_path": db_app.cover_letter_path,
                        "learning_plan_path": os.path.join(os.path.dirname(db_app.resume_path), "learning_plan.json") if db_app.resume_path else None
                    })

            end_time = datetime.now(timezone.utc)
            self._log_execution(node_name, start_time, end_time, "success")
            
            return {
                "application_packages": packages,
                "current_step": node_name
            }
            
        except Exception as e:
            err_msg = f"application_jobs_node failed: {e}"
            logger.error(err_msg, exc_info=True)
            errors.append(err_msg)
            
            end_time = datetime.now(timezone.utc)
            self._log_execution(node_name, start_time, end_time, "failure", error_message=str(e))
            
            return {
                "application_packages": [],
                "errors": errors,
                "current_step": node_name
            }

    def feedback_node(self, state: GraphState) -> Dict[str, Any]:
        node_name = "feedback_node"
        logger.info(f"Node execution started: {node_name}")
        start_time = datetime.now(timezone.utc)
        
        errors = list(state.get("errors", []))
        ranked_jobs = state.get("ranked_jobs", [])
        
        try:
            # Automatically record a "Viewed Job" event for all jobs entering evaluation ranking
            for job in ranked_jobs:
                url = job.get("job_url")
                if url:
                    self.feedback_agent.log_event(
                        event_type="Viewed Job",
                        job_url=url,
                        payload={"source": "automated_pipeline"}
                    )
            
            end_time = datetime.now(timezone.utc)
            self._log_execution(node_name, start_time, end_time, "success")
            
            return {
                "current_step": node_name
            }
        except Exception as e:
            err_msg = f"feedback_node failed: {e}"
            logger.error(err_msg, exc_info=True)
            errors.append(err_msg)
            
            end_time = datetime.now(timezone.utc)
            self._log_execution(node_name, start_time, end_time, "failure", error_message=str(e))
            
            return {
                "errors": errors,
                "current_step": node_name
            }

    def learning_node(self, state: GraphState) -> Dict[str, Any]:
        node_name = "learning_node"
        logger.info(f"Node execution started: {node_name}")
        start_time = datetime.now(timezone.utc)
        
        errors = list(state.get("errors", []))
        
        try:
            if settings.LEARNING_ENABLED:
                logger.info("LearningAgent: Running feedback learning cycle inside workflow node.")
                self.learning_agent.learn_from_feedback()
                
            end_time = datetime.now(timezone.utc)
            self._log_execution(node_name, start_time, end_time, "success")
            
            return {
                "current_step": node_name
            }
        except Exception as e:
            err_msg = f"learning_node failed: {e}"
            logger.error(err_msg, exc_info=True)
            errors.append(err_msg)
            
            end_time = datetime.now(timezone.utc)
            self._log_execution(node_name, start_time, end_time, "failure", error_message=str(e))
            
            return {
                "errors": errors,
                "current_step": node_name
            }

    def career_strategy_node(self, state: GraphState) -> Dict[str, Any]:
        node_name = "career_strategy_node"
        logger.info(f"Node execution started: {node_name}")
        start_time = datetime.now(timezone.utc)
        
        errors = list(state.get("errors", []))
        ranked_jobs = [dict(job) for job in state.get("ranked_jobs", [])]
        match_results = state.get("match_results", {})
        
        career_decisions = {}
        recommendation_scores = {}
        
        try:
            # 1. Read base candidate resume
            resume_path = os.path.abspath(settings.RESUME_PATH)
            resume_content = "Python, SQL Developer with AI experience"
            if os.path.exists(resume_path):
                with open(resume_path, "r", encoding="utf-8") as f:
                    resume_content = f.read()

            # 2. Evaluate strategy & personalized recommendation scores for each ranked job
            for job in ranked_jobs:
                url = job.get("job_url", "")
                if not url:
                    continue
                    
                match_result = match_results.get(url, {})
                
                # Run strategic evaluation
                strategy_result = self.strategy_agent.evaluate_strategy(job, resume_content)
                career_decisions[url] = strategy_result
                
                # Compute multi-criteria personalized scoring
                scores = self.recommendation_agent.calculate_scores(job, match_result, strategy_result)
                recommendation_scores[url] = scores
                
                # Apply personalized ranking updates
                job["recommendation_score"] = scores["final_score"]
                job["match_score"] = int(scores["final_score"]) # Keep match_score in sync for sorting/compatibility
                job["priority"] = strategy_result["priority"]
                job["should_apply"] = (strategy_result["recommendation"] == "Apply Immediately")
            
            # 3. Re-sort the ranked_jobs array by personalized final recommendation score
            re_ranked_jobs = sorted(ranked_jobs, key=lambda x: x.get("recommendation_score", 0.0), reverse=True)

            end_time = datetime.now(timezone.utc)
            self._log_execution(node_name, start_time, end_time, "success")
            
            return {
                "ranked_jobs": re_ranked_jobs,
                "career_decisions": career_decisions,
                "recommendation_scores": recommendation_scores,
                "current_step": node_name
            }
            
        except Exception as e:
            err_msg = f"career_strategy_node failed: {e}"
            logger.error(err_msg, exc_info=True)
            errors.append(err_msg)
            
            end_time = datetime.now(timezone.utc)
            self._log_execution(node_name, start_time, end_time, "failure", error_message=str(e))
            
            return {
                "errors": errors,
                "current_step": node_name
            }
