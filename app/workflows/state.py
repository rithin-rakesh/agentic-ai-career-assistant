from typing import TypedDict, List, Dict, Any

class GraphState(TypedDict):
    """
    State definition for the LangGraph multi-agent system.
    Propagates data, stats, and metadata between autonomous agent nodes.
    """
    # Raw job listings collected during execution
    jobs: List[Dict[str, Any]]
    
    # Job listings that passed rule-based location/skill/experience filtering
    filtered_jobs: List[Dict[str, Any]]
    
    # Map of job URL to retrieved resume context text (RAG context)
    retrieved_context: Dict[str, str]
    
    # Map of job URL to Pydantic JobMatchResult serialized evaluation results
    match_results: Dict[str, Dict[str, Any]]
    
    # Sorted list of jobs grouped by priority and suitability score
    ranked_jobs: List[Dict[str, Any]]
    
    # Track any exceptions/errors encountered in nodes for retry loops
    errors: List[str]
    
    # Operational execution counters: "collected", "filtered", "duplicates", "inserted", "failed"
    statistics: Dict[str, int]
    
    # Timing and operational parameters: "start_time", "attempt_count", "embedding_model", etc.
    execution_metadata: Dict[str, Any]
    
    # List of notification delivery transaction logs to persist in SQLite
    notification_records: List[Dict[str, Any]]

    # List of prepared application package records to persist in SQLite
    application_packages: List[Dict[str, Any]]

    # Map of job URL to Career Strategy JSON evaluation output
    career_decisions: Dict[str, Dict[str, Any]]

    # Map of job URL to component and final recommendation scores
    recommendation_scores: Dict[str, Dict[str, float]]
    
    # Name of the active step/node (e.g. "collector_node")
    current_step: str
