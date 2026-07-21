import time
from typing import List, Dict, Any, Tuple
from app.config import settings
from app.rag.embedding_service import EmbeddingService
from app.rag.vector_store import VectorStore
from app.logger import logger

class Retriever:
    """
    Retriever class that embeds search queries (job descriptions)
    and fetches the most semantically relevant resume chunks from Qdrant.
    """
    def __init__(self, embedding_service: EmbeddingService, vector_store: VectorStore):
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.top_k = settings.TOP_K
        self.threshold = settings.SIMILARITY_THRESHOLD

    def retrieve_relevant_context(self, query_text: str) -> Tuple[List[Dict[str, Any]], float, float]:
        """
        Embeds the query text and retrieves the top-K chunks from the vector store.
        Returns a tuple of:
          - list of retrieved chunk dictionaries (having chunk_id, content, score)
          - max similarity score (or 0.0 if empty)
          - retrieval latency in seconds
        """
        if not query_text or not query_text.strip():
            logger.warning("Empty search query provided. Returning empty context.")
            return [], 0.0, 0.0
            
        logger.info(f"RAG Retrieval started. Query length: {len(query_text)}. Limit Top-K: {self.top_k}")
        
        start_time = time.perf_counter()
        
        try:
            # 1. Embed query
            query_embedding = self.embedding_service.get_embedding(query_text)
            
            # 2. Query Qdrant
            results = self.vector_store.search(
                query_embedding=query_embedding,
                top_k=self.top_k,
                threshold=self.threshold
            )
            
            latency = time.perf_counter() - start_time
            
            # 3. Calculate max similarity score
            max_score = max([r["score"] for r in results]) if results else 0.0
            
            logger.info(
                f"RAG Retrieval complete in {latency:.4f}s. "
                f"Retrieved {len(results)} relevant resume sections. Max similarity score: {max_score:.4f}"
            )
            
            # Log retrieved section chunk IDs for traceability
            retrieved_ids = [r["chunk_id"] for r in results]
            logger.info(f"Retrieved Section IDs: {retrieved_ids}")
            
            return results, max_score, latency
            
        except Exception as e:
            logger.error(f"Error during RAG context retrieval: {e}", exc_info=True)
            # Fail-safe return
            return [], 0.0, 0.0
