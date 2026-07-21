from langgraph.checkpoint.memory import MemorySaver

def get_checkpointer() -> MemorySaver:
    """
    Instantiates and returns a MemorySaver checkpointer.
    Provides thread-level checkpoint serialization to support:
    - Step-level recovery on crash
    - Execution checkpoints persistence
    - Interactive human-in-the-loop interventions (in future days)
    """
    return MemorySaver()
