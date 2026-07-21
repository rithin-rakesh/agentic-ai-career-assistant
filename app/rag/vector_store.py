import uuid
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from app.config import settings
from app.logger import logger

class VectorStore:
    """
    Wrapper interface encapsulating Qdrant vector database operations.
    Supports in-memory operations, local file persistence, or remote cluster instances.
    """
    def __init__(self, collection_name: Optional[str] = None):
        self.collection_name = collection_name or settings.COLLECTION_NAME
        self.db_url = settings.qdrant_path_absolute
        self.dimension = 384  # Matches dimension of the embedding service (all-MiniLM-L6-v2)
        
        logger.info(f"Initializing Qdrant client connection. Target: {self.db_url}")
        
        # Select client type based on settings
        if self.db_url == ":memory:":
            self.client = QdrantClient(location=":memory:")
        elif self.db_url.startswith("http://") or self.db_url.startswith("https://"):
            self.client = QdrantClient(url=self.db_url)
        else:
            # File system persistence
            self.client = QdrantClient(path=self.db_url)

    def create_collection(self) -> None:
        """
        Creates a new collection in Qdrant if it does not already exist.
        Uses Cosine distance for semantic similarity vector search.
        """
        try:
            collections = self.client.get_collections().collections
            existing_names = [col.name for col in collections]
            
            if self.collection_name not in existing_names:
                logger.info(f"Creating new Qdrant collection: '{self.collection_name}' (dim: {self.dimension})")
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=self.dimension, distance=Distance.COSINE)
                )
                logger.info(f"Qdrant collection '{self.collection_name}' created successfully.")
            else:
                logger.debug(f"Qdrant collection '{self.collection_name}' already exists. Skipping creation.")
        except Exception as e:
            logger.error(f"Failed to create Qdrant collection '{self.collection_name}': {e}", exc_info=True)
            raise

    def insert_chunk(self, chunk_id: str, embedding: List[float], metadata: Dict[str, Any], content: str) -> None:
        """
        Inserts/upserts a single resume chunk vector and metadata payload.
        Maps the string chunk_id to a deterministic UUID to avoid duplicates.
        """
        # Map string chunk_id to standard UUID (Qdrant Point ID must be UUID or integer)
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk_id))
        
        try:
            self.client.upsert(
                collection_name=self.collection_name,
                points=[
                    PointStruct(
                        id=point_id,
                        vector=embedding,
                        payload={
                            "chunk_id": chunk_id,
                            "content": content,
                            "metadata": metadata
                        }
                    )
                ]
            )
            logger.debug(f"Chunk '{chunk_id}' upserted into Qdrant vector store.")
        except Exception as e:
            logger.error(f"Failed to upsert chunk '{chunk_id}' into Qdrant: {e}", exc_info=True)
            raise

    def search(self, query_embedding: List[float], top_k: int = 3, threshold: float = 0.3) -> List[Dict[str, Any]]:
        """
        Queries Qdrant vector space for top_k nearest neighbors matching query_embedding.
        Returns a list of payloads matching the similarity score threshold.
        """
        try:
            response = self.client.query_points(
                collection_name=self.collection_name,
                query=query_embedding,
                limit=top_k,
                score_threshold=threshold
            )
            
            search_results = []
            for pt in response.points:
                payload = pt.payload or {}
                search_results.append({
                    "chunk_id": payload.get("chunk_id"),
                    "content": payload.get("content"),
                    "metadata": payload.get("metadata"),
                    "score": float(pt.score)
                })
            return search_results
        except Exception as e:
            logger.error(f"Qdrant vector search failed: {e}", exc_info=True)
            raise

    def delete_collection(self) -> None:
        """
        Drops the collection and vector indexes completely.
        """
        try:
            collections = self.client.get_collections().collections
            if any(col.name == self.collection_name for col in collections):
                self.client.delete_collection(collection_name=self.collection_name)
                logger.info(f"Qdrant collection '{self.collection_name}' deleted successfully.")
        except Exception as e:
            logger.error(f"Failed to delete Qdrant collection '{self.collection_name}': {e}", exc_info=True)
            raise

    def rebuild_index(self) -> None:
        """
        Wipes current collections and initializes a fresh vector schema.
        """
        logger.info(f"Rebuilding Qdrant vector index for '{self.collection_name}'")
        self.delete_collection()
        self.create_collection()
