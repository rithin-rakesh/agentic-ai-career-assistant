import os
import time
from typing import Dict, Any, List
from app.collectors.collector_manager import CollectorManager
from app.services.filtering import FilteringService
from app.database.repository import JobRepository
from app.agents.collector_agent import CollectorAgent
from app.agents.filtering_agent import FilteringAgent
from app.agents.retrieval_agent import RetrievalAgent
from app.agents.matching_agent import MatchingAgent
from app.agents.ranking_agent import RankingAgent
from app.agents.persistence_agent import PersistenceAgent
from app.workflows.nodes import GraphNodeOrchestrator
from app.workflows.graph import compile_workflow
from app.logger import logger

class CollectionService:
    """
    Coordinates job search execution flows.
    Day 5: Delegates sequential service pipelines to LangGraph Multi-Agent Orchestration,
    allowing thread check-pointing, node attempts, and conditional routing.
    """
    def __init__(self, repository: JobRepository, collector_manager: CollectorManager, filtering_service: FilteringService, ai_matching_service: Any = None):
        self.repository = repository
        self.collector_manager = collector_manager
        self.filtering_service = filtering_service
        self.ai_matching_service = ai_matching_service

    def run_sync(self) -> Dict[str, int]:
        """
        Builds, compiles, and executes the LangGraph state machine.
        Returns unified execution statistics dictionary.
        """
        logger.info("CollectionService: Initializing LangGraph multi-agent orchestrator.")
        start_time = time.perf_counter()

        # 1. Resolve RAG matching pipeline references
        if self.ai_matching_service:
            llm_client = self.ai_matching_service.llm_client
            embedding_service = self.ai_matching_service.embedding_service
            vector_store = self.ai_matching_service.vector_store
            retriever = self.ai_matching_service.retriever
            indexing_pipeline = self.ai_matching_service.indexing_pipeline
            resume_path = self.ai_matching_service.resume_path
            
            # Ensure candidate profile template is generated
            self.ai_matching_service._ensure_default_resume()
        else:
            from app.ai.llm_client import OpenAIClient
            from app.rag.embedding_service import EmbeddingService
            from app.rag.vector_store import VectorStore
            from app.rag.retriever import Retriever
            from app.rag.indexing import ResumeIndexingPipeline
            llm_client = OpenAIClient()
            embedding_service = EmbeddingService()
            vector_store = VectorStore()
            retriever = Retriever(embedding_service, vector_store)
            indexing_pipeline = ResumeIndexingPipeline(embedding_service, vector_store)
            resume_path = "data/resume.md"

        # 2. Build resume indexes (runs change detection checks internally)
        try:
            from app.resume.resume_loader import ResumeLoader
            if os.path.exists(resume_path):
                raw_resume = ResumeLoader.load_resume(resume_path)
                indexing_pipeline.run(raw_resume)
        except Exception as e:
            logger.error(f"CollectionService: Resume preprocessing failed: {e}", exc_info=True)

        # 3. Instantiate Agents
        collector_agent = CollectorAgent(self.collector_manager)
        filtering_agent = FilteringAgent(self.filtering_service, self.repository)
        retrieval_agent = RetrievalAgent(retriever)
        matching_agent = MatchingAgent(llm_client)
        ranking_agent = RankingAgent()
        persistence_agent = PersistenceAgent(self.repository)
        
        from app.notifications.notification_repository import NotificationRepository
        from app.agents.notification_agent import NotificationAgent
        noti_repo = NotificationRepository(session_provider=self.repository.session_provider)
        notification_agent = NotificationAgent(repository=noti_repo)

        from app.agents.resume_agent import ResumeAgent
        from app.agents.cover_letter_agent import CoverLetterAgent
        from app.agents.skills_agent import SkillsAgent
        from app.memory.application_memory import ApplicationMemoryManager
        from app.agents.application_agent import ApplicationAgent
        
        res_agent = ResumeAgent(llm_client=llm_client)
        cov_agent = CoverLetterAgent(llm_client=llm_client)
        skl_agent = SkillsAgent(llm_client=llm_client)
        mem_mgr = ApplicationMemoryManager()
        application_agent = ApplicationAgent(
            resume_agent=res_agent,
            cl_agent=cov_agent,
            skills_agent=skl_agent,
            memory_manager=mem_mgr
        )

        # 4. Construct GraphNodeOrchestrator
        orchestrator = GraphNodeOrchestrator(
            collector=collector_agent,
            filtering=filtering_agent,
            retrieval=retrieval_agent,
            matching=matching_agent,
            ranking=ranking_agent,
            persistence=persistence_agent,
            notification=notification_agent,
            application=application_agent
        )

        # 5. Compile StateGraph
        logger.info("CollectionService: Compiling StateGraph.")
        workflow_graph = compile_workflow(orchestrator)

        # 6. Execute LangGraph workflow
        initial_state = {
            "jobs": [],
            "filtered_jobs": [],
            "retrieved_context": {},
            "match_results": {},
            "ranked_jobs": [],
            "errors": [],
            "notification_records": [],
            "application_packages": [],
            "statistics": {
                "collected": 0,
                "filtered": 0,
                "duplicates": 0,
                "inserted": 0,
                "failed": 0
            },
            "execution_metadata": {
                "attempts": {},
                "retrieval_metrics": {},
                "start_time": start_time
            },
            "current_step": "START"
        }
        
        # Thread config parameter enables checkpoint save loops
        config = {"configurable": {"thread_id": "job_sync_thread_run"}}
        
        logger.info("CollectionService: Executing StateGraph workflow.")
        final_state = workflow_graph.invoke(initial_state, config=config)
        
        execution_duration = time.perf_counter() - start_time
        logger.info(f"CollectionService: StateGraph finished execution in {execution_duration:.2f} seconds.")
        
        if final_state.get("errors"):
            logger.warning(f"CollectionService: Node recoverable errors caught: {final_state.get('errors')}")

        return final_state.get("statistics", {})
