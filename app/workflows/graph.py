from langgraph.graph import StateGraph, START, END
from app.workflows.state import GraphState
from app.workflows.nodes import GraphNodeOrchestrator
from app.workflows.edges import check_collection_count, check_matching_confidence
from app.memory.checkpoint import get_checkpointer

def compile_workflow(orchestrator: GraphNodeOrchestrator):
    """
    Constructs, connects, and compiles the multi-agent LangGraph workflow.
    Configures standard transitions, conditional routing boundaries,
    and binds the MemorySaver checkpointer.
    """
    # 1. Initialize StateGraph with GraphState
    workflow = StateGraph(GraphState)
    
    # 2. Register nodes
    workflow.add_node("collect_jobs_node", orchestrator.collect_jobs_node)
    workflow.add_node("filter_jobs_node", orchestrator.filter_jobs_node)
    workflow.add_node("retrieve_context_node", orchestrator.retrieve_context_node)
    workflow.add_node("match_jobs_node", orchestrator.match_jobs_node)
    workflow.add_node("rank_jobs_node", orchestrator.rank_jobs_node)
    workflow.add_node("feedback_node", orchestrator.feedback_node)
    workflow.add_node("learning_node", orchestrator.learning_node)
    workflow.add_node("career_strategy_node", orchestrator.career_strategy_node)
    workflow.add_node("notification_jobs_node", orchestrator.notification_jobs_node)
    workflow.add_node("digest_jobs_node", orchestrator.digest_jobs_node)
    workflow.add_node("application_jobs_node", orchestrator.application_jobs_node)
    workflow.add_node("persist_jobs_node", orchestrator.persist_jobs_node)
    
    # 3. Add edges
    # START -> collect -> filter
    workflow.add_edge(START, "collect_jobs_node")
    workflow.add_edge("collect_jobs_node", "filter_jobs_node")
    
    # filter_jobs_node -> Conditional Edge (check if jobs exist)
    workflow.add_conditional_edges(
        "filter_jobs_node",
        check_collection_count,
        {
            END: END,
            "retrieve_context_node": "retrieve_context_node"
        }
    )
    
    # retrieve -> match
    workflow.add_edge("retrieve_context_node", "match_jobs_node")
    
    # match_jobs_node -> Conditional Edge (retry match on low confidence)
    workflow.add_conditional_edges(
        "match_jobs_node",
        check_matching_confidence,
        {
            "match_jobs_node": "match_jobs_node",
            "rank_jobs_node": "rank_jobs_node"
        }
    )
    
    # rank -> feedback -> learning -> career_strategy -> notification -> digest -> application -> persist -> END
    workflow.add_edge("rank_jobs_node", "feedback_node")
    workflow.add_edge("feedback_node", "learning_node")
    workflow.add_edge("learning_node", "career_strategy_node")
    workflow.add_edge("career_strategy_node", "notification_jobs_node")
    workflow.add_edge("notification_jobs_node", "digest_jobs_node")
    workflow.add_edge("digest_jobs_node", "application_jobs_node")
    workflow.add_edge("application_jobs_node", "persist_jobs_node")
    workflow.add_edge("persist_jobs_node", END)
    
    # 4. Bind checkpointer and compile
    checkpointer = get_checkpointer()
    compiled_graph = workflow.compile(checkpointer=checkpointer)
    
    return compiled_graph
