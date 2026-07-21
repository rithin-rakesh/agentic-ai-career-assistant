import pytest
from unittest.mock import MagicMock
from langgraph.graph import END

from app.workflows.state import GraphState
from app.workflows.nodes import GraphNodeOrchestrator
from app.workflows.edges import check_collection_count, check_matching_confidence
from app.workflows.graph import compile_workflow
from app.agents.collector_agent import CollectorAgent
from app.agents.filtering_agent import FilteringAgent
from app.agents.retrieval_agent import RetrievalAgent
from app.agents.matching_agent import MatchingAgent
from app.agents.ranking_agent import RankingAgent
from app.agents.persistence_agent import PersistenceAgent
from app.agents.notification_agent import NotificationAgent
from app.agents.application_agent import ApplicationAgent

def test_graph_state_dict_structure():
    """
    Asserts that GraphState holds the expected strongly-typed TypedDict fields.
    """
    # Simply declare a matching dictionary
    state: GraphState = {
        "jobs": [{"title": "Job A"}],
        "filtered_jobs": [],
        "retrieved_context": {},
        "match_results": {},
        "ranked_jobs": [],
        "errors": [],
        "statistics": {"collected": 1, "filtered": 0, "duplicates": 0, "inserted": 0, "failed": 0},
        "execution_metadata": {},
        "current_step": "START"
    }
    assert len(state["jobs"]) == 1
    assert state["statistics"]["collected"] == 1

def test_collector_node_exception_handling():
    """
    Checks that collector node catches exceptions and returns state with errors list.
    """
    # Create agent mocks
    collector = MagicMock(spec=CollectorAgent)
    collector.collect.side_effect = Exception("Scraping timeout failure")
    
    orchestrator = GraphNodeOrchestrator(
        collector=collector,
        filtering=MagicMock(spec=FilteringAgent),
        retrieval=MagicMock(spec=RetrievalAgent),
        matching=MagicMock(spec=MatchingAgent),
        ranking=MagicMock(spec=RankingAgent),
        persistence=MagicMock(spec=PersistenceAgent)
    )
    
    state = {"jobs": [], "errors": [], "current_step": "START"}
    new_state = orchestrator.collect_jobs_node(state)
    
    assert new_state["jobs"] == []
    assert len(new_state["errors"]) == 1
    assert "Scraping timeout failure" in new_state["errors"][0]
    assert new_state["current_step"] == "collect_jobs_node"

def test_conditional_routing_no_jobs():
    """
    Verifies routing checks route directly to END if no jobs passed filter rules.
    """
    state: GraphState = {
        "jobs": [],
        "filtered_jobs": [],  # Empty
        "retrieved_context": {},
        "match_results": {},
        "ranked_jobs": [],
        "errors": [],
        "statistics": {},
        "execution_metadata": {},
        "current_step": "filter_jobs_node"
    }
    # Should route to END
    route = check_collection_count(state)
    assert route == END

def test_conditional_routing_with_jobs():
    """
    Verifies routing checks route to retrieve_context_node if jobs passed filters.
    """
    state: GraphState = {
        "jobs": [],
        "filtered_jobs": [{"title": "Python Developer", "job_url": "url-1"}],
        "retrieved_context": {},
        "match_results": {},
        "ranked_jobs": [],
        "errors": [],
        "statistics": {},
        "execution_metadata": {},
        "current_step": "filter_jobs_node"
    }
    route = check_collection_count(state)
    assert route == "retrieve_context_node"

def test_conditional_routing_matching_retry():
    """
    Checks that matching confidence edge triggers retry loop if confidence is low.
    """
    state: GraphState = {
        "jobs": [],
        "filtered_jobs": [{"title": "AI Engineer", "job_url": "url-1"}],
        "retrieved_context": {},
        "match_results": {
            "url-1": {"match_score": 40, "should_apply": False, "confidence": 0.3}  # Low confidence
        },
        "ranked_jobs": [],
        "errors": [],
        "statistics": {},
        "execution_metadata": {
            "attempts": {"url-1": 0}  # Retry is under settings.MAX_RETRIES (2)
        },
        "current_step": "match_jobs_node"
    }
    
    route = check_matching_confidence(state)
    assert route == "match_jobs_node"

def test_conditional_routing_matching_no_retry_on_max_attempts():
    """
    Checks that matching confidence edge routes to rank_jobs_node if attempts exceed max limit.
    """
    state: GraphState = {
        "jobs": [],
        "filtered_jobs": [{"title": "AI Engineer", "job_url": "url-1"}],
        "retrieved_context": {},
        "match_results": {
            "url-1": {"match_score": 40, "should_apply": False, "confidence": 0.3}  # Low confidence
        },
        "ranked_jobs": [],
        "errors": [],
        "statistics": {},
        "execution_metadata": {
            "attempts": {"url-1": 2}  # Retry is AT settings.MAX_RETRIES (2)
        },
        "current_step": "match_jobs_node"
    }
    
    route = check_matching_confidence(state)
    assert route == "rank_jobs_node"

def test_graph_compilation_and_checkpoint_recovery():
    """
    Compiles workflow and verifies that the thread state checkpoints are correctly
    persisted and recovered across subsequent runs.
    """
    # 1. Setup mock agents
    collector = MagicMock(spec=CollectorAgent)
    collector.collect.return_value = ([{"title": "Analyst", "company": "Co", "location": "Remote", "job_url": "http://job", "description": "skills", "source": "Wellfound", "date_posted": "2026-07-19"}], 0)
    
    filtering = MagicMock(spec=FilteringAgent)
    filtering.filter_jobs.return_value = ([{"title": "Analyst", "company": "Co", "location": "Remote", "job_url": "http://job", "description": "skills", "source": "Wellfound", "date_posted": "2026-07-19"}], 0, 0)
    
    retrieval = MagicMock(spec=RetrievalAgent)
    retrieval.retrieve.return_value = ({"http://job": "resume skills"}, {"http://job": {"retrieved_chunk_ids": ["c1"], "retrieval_time": 0.1, "retrieval_score": 0.8}})
    
    matching = MagicMock(spec=MatchingAgent)
    matching.match_jobs.return_value = {"http://job": {"match_score": 90, "should_apply": True, "priority": "High", "confidence": 0.9}}
    
    ranking = MagicMock(spec=RankingAgent)
    ranking.rank_jobs.return_value = [{"title": "Analyst", "company": "Co", "location": "Remote", "job_url": "http://job", "match_score": 90, "should_apply": True}]
    
    persistence = MagicMock(spec=PersistenceAgent)
    persistence.persist_jobs.return_value = (1, 0)
    
    notification = MagicMock(spec=NotificationAgent)
    notification.evaluate_and_notify.return_value = [{"job_url": "http://job", "status": "sent"}]
    
    application = MagicMock(spec=ApplicationAgent)
    application.prepare_applications.return_value = [{"job_url": "http://job", "company": "Co", "position": "Analyst", "status": "Draft", "resume_path": "path", "cover_letter_path": "path"}]
    
    orchestrator = GraphNodeOrchestrator(
        collector=collector, filtering=filtering, retrieval=retrieval,
        matching=matching, ranking=ranking, persistence=persistence,
        notification=notification, application=application
    )
    
    # 2. Compile StateGraph
    graph = compile_workflow(orchestrator)
    
    initial_state = {
        "jobs": [],
        "filtered_jobs": [],
        "retrieved_context": {},
        "match_results": {},
        "ranked_jobs": [],
        "errors": [],
        "notification_records": [],
        "application_packages": [],
        "statistics": {"collected": 0, "filtered": 0, "duplicates": 0, "inserted": 0, "failed": 0},
        "execution_metadata": {"attempts": {}, "retrieval_metrics": {}},
        "current_step": "START"
    }
    
    config = {"configurable": {"thread_id": "test_checkpoint_thread"}}
    
    # 3. Run first invoke
    final_state = graph.invoke(initial_state, config=config)
    
    assert final_state["current_step"] == "persist_jobs_node"
    assert final_state["statistics"]["inserted"] == 1
    
    # 4. Checkpoint check: retrieve state from memory saver checkpointer
    state_history = list(graph.get_state_history(config))
    assert len(state_history) > 1
    
    latest_checkpoint = graph.get_state(config)
    assert latest_checkpoint.values["current_step"] == "persist_jobs_node"
