import time
from typing import List, Dict, Any, Tuple
from app.rag.retriever import Retriever
from app.logger import logger

class RetrievalAgent:
    """
    RetrievalAgent performs semantic context searches:
    - Embeds individual job descriptions.
    - Searches Qdrant collection for nearest resume section chunks.
    - Resolves semantic text strings to feed directly into the matching prompt.
    - Logs retrieval metrics (ids, times, scores) in metadata for persistence.
    """
    def __init__(self, retriever: Retriever):
        self.retriever = retriever

    def retrieve(self, filtered_jobs: List[Dict[str, Any]]) -> Tuple[Dict[str, str], Dict[str, Dict[str, Any]]]:
        """
        Retrieves matching resume contexts for each job description.
        Returns:
          - Dict[job_url -> text_context_string]
          - Dict[job_url -> dict_of_retrieval_metrics]
        """
        logger.info(f"RetrievalAgent: Starting context extraction for {len(filtered_jobs)} jobs.")
        
        contexts = {}
        metrics = {}
        
        for job_dict in filtered_jobs:
            url = job_dict.get("job_url", "")
            desc = job_dict.get("description", "")
            
            if not url or not desc:
                continue
                
            try:
                # Query vector database
                chunks, max_score, latency = self.retriever.retrieve_relevant_context(desc)
                
                if not chunks:
                    logger.warning(f"RetrievalAgent: 0 matches found for '{job_dict.get('title')}' at '{job_dict.get('company')}'. Falling back.")
                    retrieved_context = "No relevant resume sections could be semantically retrieved matching this job description."
                    chunk_ids = []
                else:
                    parts = []
                    for chunk in chunks:
                        sect = chunk.get("metadata", {}).get("section", "General")
                        parts.append(f"Section: {sect}\nContent:\n{chunk['content']}")
                    retrieved_context = "\n\n---\n\n".join(parts)
                    chunk_ids = [chunk["chunk_id"] for chunk in chunks]
                    
                contexts[url] = retrieved_context
                metrics[url] = {
                    "retrieved_chunk_ids": chunk_ids,
                    "retrieval_time": latency,
                    "retrieval_score": max_score
                }
                
            except Exception as e:
                logger.error(f"RetrievalAgent: Context extraction failed for job URL {url}: {e}", exc_info=True)
                contexts[url] = "Error retrieving resume context."
                metrics[url] = {
                    "retrieved_chunk_ids": [],
                    "retrieval_time": 0.0,
                    "retrieval_score": 0.0
                }
                
        logger.info("RetrievalAgent: Context extraction complete.")
        return contexts, metrics
