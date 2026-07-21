from app.workers.celery_app import celery_app
from app.logger import logger
from app.database.repository import JobRepository
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

@celery_app.task(name="tasks.run_job_collection_pipeline", bind=True, max_retries=3)
def run_job_collection_pipeline(self):
    """
    Celery task that executes the end-to-end multi-agent job collection, matching,
    and persist pipeline asynchronously.
    """
    logger.info("Celery Worker: Starting background job collection pipeline task...")
    try:
        repo = JobRepository()
        repo.create_database()
        
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
        
        stats = collection_service.run_sync()
        logger.info(f"Celery Worker: Task completed successfully. Stats: {stats}")
        return stats
    except Exception as exc:
        logger.error(f"Celery Worker: Task failed with exception: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=60)

@celery_app.task(name="tasks.trigger_preference_learning", bind=True)
def trigger_preference_learning(self):
    """
    Celery task that triggers the self-improving LearningAgent.
    """
    logger.info("Celery Worker: Running preference learning cycle...")
    try:
        from app.agents.learning_agent import LearningAgent
        repo = JobRepository()
        agent = LearningAgent(repository=repo)
        result = agent.learn_from_feedback()
        logger.info(f"Celery Worker: Learning cycle completed. Result: {result}")
        return result
    except Exception as exc:
        logger.error(f"Celery Worker: Learning task failed: {exc}", exc_info=True)
        return {"status": "error", "error": str(exc)}
