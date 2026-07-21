import os
import hashlib
from typing import Optional
from app.config import settings
from app.resume.chunk_generator import ResumeChunkGenerator
from app.rag.embedding_service import EmbeddingService
from app.rag.vector_store import VectorStore
from app.logger import logger

class ResumeIndexingPipeline:
    """
    Pipeline responsible for chunking the candidate's resume, embedding
    the sections, and indexing them in Qdrant.
    Features incremental indexing: only rebuilds the index if the resume file changes.
    """
    def __init__(self, embedding_service: EmbeddingService, vector_store: VectorStore):
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        # Paths relative to the project root
        self.hash_path = os.path.join(settings.BASE_DIR, "data", "resume_hash.txt")

    def _compute_hash(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _read_stored_hash(self) -> Optional[str]:
        if os.path.exists(self.hash_path):
            try:
                with open(self.hash_path, "r", encoding="utf-8") as f:
                    return f.read().strip()
            except Exception as e:
                logger.warning(f"Failed to read stored resume hash: {e}")
        return None

    def _write_stored_hash(self, new_hash: str) -> None:
        try:
            os.makedirs(os.path.dirname(self.hash_path), exist_ok=True)
            with open(self.hash_path, "w", encoding="utf-8") as f:
                f.write(new_hash)
            logger.info("New resume hash persisted to data cache.")
        except Exception as e:
            logger.error(f"Failed to save resume hash: {e}")

    def run(self, resume_text: str) -> bool:
        """
        Runs the indexing pipeline.
        Returns True if indexing occurred, and False if it was skipped due to hash match.
        """
        if not resume_text or not resume_text.strip():
            logger.warning("Empty resume content provided. Skipping indexing pipeline.")
            return False

        # 1. Check change hashes to see if indexing is required
        current_hash = self._compute_hash(resume_text)
        stored_hash = self._read_stored_hash()
        
        # If Qdrant is running in memory, we must index every time since the DB is volatile!
        is_volatile_db = settings.VECTOR_DB_URL == ":memory:"
        
        if stored_hash == current_hash and not is_volatile_db:
            logger.info("Resume file hash matches database state. Skipping vector indexing (Cached).")
            return False
            
        logger.info("Resume modifications detected or fresh database. Initiating vector index build...")
        
        # 2. Rebuild the Qdrant index structure (drops and recreates the collection)
        self.vector_store.rebuild_index()
        
        # 3. Generate section chunks
        chunks = ResumeChunkGenerator.generate_chunks(resume_text)
        if not chunks:
            logger.warning("No chunks generated from resume text. Vector index is empty.")
            return False
            
        # 4. Generate embeddings in batch for optimal performance
        contents = [chunk.content for chunk in chunks]
        embeddings = self.embedding_service.get_embeddings_batch(contents)
        
        # 5. Load chunks into Qdrant
        logger.info(f"Ingesting {len(chunks)} resume chunks into Qdrant collection...")
        for chunk, embedding in zip(chunks, embeddings):
            metadata = {
                "section": chunk.section
            }
            self.vector_store.insert_chunk(
                chunk_id=chunk.chunk_id,
                embedding=embedding,
                metadata=metadata,
                content=chunk.content
            )
            
        # 6. Cache the new hash to avoid rebuilding next run
        if not is_volatile_db:
            self._write_stored_hash(current_hash)
            
        logger.info("Resume vector indexing pipeline finished successfully.")
        return True
