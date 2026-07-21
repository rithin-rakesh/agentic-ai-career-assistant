import os
import sys
import argparse
from dotenv import load_dotenv

# Ensure the root of the project is added to sys.path for direct executions
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import settings
from app.logger import setup_logging
from app.database.repository import JobRepository
from app.collectors.wellfound import WellfoundCollector
from app.collectors.indeed import IndeedCollector
from app.collectors.naukri import NaukriCollector
from app.collectors.remoteok import RemoteOKCollector
from app.collectors.arbeitnow import ArbeitnowCollector
from app.collectors.remotive import RemotiveCollector
from app.collectors.collector_manager import CollectorManager
from app.services.filtering import FilteringService
from app.services.collection_service import CollectionService
from app.services.rag_matching_service import RAGMatchingService
from app.scheduler.scheduler import JobScheduler

def main() -> None:
    """
    Main entry point for the Job Search Assistant.
    Supports running a one-off sync, starting a daemon scheduler, or running the AI Matcher standalone.
    """
    load_dotenv()
    
    # Setup structured JSON/text logging
    use_json_logs = os.getenv("LOG_FORMAT", "").lower() == "json"
    logger = setup_logging(level=settings.LOG_LEVEL, use_json=use_json_logs)

    parser = argparse.ArgumentParser(description="Agentic AI Job Search Assistant - Day 3")
    parser.add_argument(
        "--scheduler", 
        action="store_true", 
        help="Start the background scheduler to run collections periodically."
    )
    parser.add_argument(
        "--run-ai", 
        action="store_true", 
        help="Start the AI Matching Agent standalone to analyze pending job listings in the database."
    )
    args = parser.parse_args()

    logger.info("Initializing Agentic AI Job Search Assistant...")

    try:
        # 1. Setup repository and initialize SQLite database schema (includes Day 3 column migrations)
        repository = JobRepository()
        repository.create_database()

        # 2. Setup collectors and CollectorManager
        manager = CollectorManager()
        manager.register_collector(RemoteOKCollector())
        manager.register_collector(ArbeitnowCollector())
        manager.register_collector(RemotiveCollector())
        manager.register_collector(WellfoundCollector())
        manager.register_collector(IndeedCollector())
        manager.register_collector(NaukriCollector())

        # 3. Setup filtering, AI matching, and Collection services
        filtering_service = FilteringService()
        ai_matching_service = RAGMatchingService(repository=repository)
        
        collection_service = CollectionService(
            repository=repository, 
            collector_manager=manager, 
            filtering_service=filtering_service,
            ai_matching_service=ai_matching_service
        )

        if args.scheduler:
            # Run in persistent scheduled mode
            scheduler = JobScheduler(collection_service=collection_service)
            scheduler.start()
        elif args.run_ai:
            # Run matching evaluation standalone
            logger.info("Executing standalone AI job matching evaluation.")
            stats = ai_matching_service.evaluate_pending_jobs()
            logger.info(f"AI matching evaluation completed. Statistics: {stats}")
        else:
            # Run in one-off collection and matching mode
            logger.info("Starting one-off collection and evaluation pipeline.")
            stats = collection_service.run_sync()
            logger.info(f"Execution finished successfully. Final Run Stats: {stats}")

    except Exception as e:
        logger.critical(f"Critical system failure, shutting down: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
