from typing import List, Dict, Any
from langgraph.graph import END
from app.workflows.state import GraphState
from app.config import settings
from app.logger import logger

def check_collection_count(state: GraphState) -> str:
    """
    Conditional routing edge checking if any jobs passed the filtering agent.
    If filtered_jobs list is empty, routes directly to END.
    Otherwise, routes to retrieve_context_node.
    """
    logger.info("Transition edge routing: check_collection_count")
    filtered = state.get("filtered_jobs", [])
    
    if not filtered:
        logger.info("Transition Edge: No jobs passed rules filters. Direct routing to END.")
        return END
        
    logger.info(f"Transition Edge: {len(filtered)} jobs passed filters. Routing to 'retrieve_context_node'.")
    return "retrieve_context_node"

def check_matching_confidence(state: GraphState) -> str:
    """
    Conditional routing edge checking the confidence score of matching evaluations.
    If any job was evaluated with confidence < 0.5, and the retry attempt count is
    under settings.MAX_RETRIES, routes back to match_jobs_node for a retry evaluation.
    Otherwise, routes to rank_jobs_node.
    """
    logger.info("Transition edge routing: check_matching_confidence")
    filtered = state.get("filtered_jobs", [])
    results = state.get("match_results", {})
    metadata = state.get("execution_metadata", {})
    attempts = metadata.get("attempts", {})
    
    max_retries = settings.MAX_RETRIES
    trigger_retry = False
    
    for job in filtered:
        url = job.get("job_url", "")
        if not url:
            continue
            
        evaluation = results.get(url, {})
        confidence = evaluation.get("confidence", 1.0)
        attempt = attempts.get(url, 0)
        
        # If low confidence and under retry threshold limit, flag for matching retry
        if confidence < 0.5 and attempt < max_retries:
            logger.info(
                f"Transition Edge: Low confidence ({confidence}) detected on '{job.get('title')}' "
                f"at '{job.get('company')}' (Attempt: {attempt} / Max: {max_retries}). Triggering retry node."
            )
            trigger_retry = True
            break
            
    if trigger_retry:
        return "match_jobs_node"
        
    logger.info("Transition Edge: All evaluations passed confidence or retry limits. Routing to 'rank_jobs_node'.")
    return "rank_jobs_node"
