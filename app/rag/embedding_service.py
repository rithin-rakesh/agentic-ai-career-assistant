import time
import hashlib
import math
import random
from typing import List, Dict, Optional
from app.config import settings
from app.logger import logger

class BaseEmbeddingService:
    """
    Abstract interface for generating semantic text embeddings.
    """
    def get_embedding(self, text: str) -> List[float]:
        pass

    def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        pass

class EmbeddingService(BaseEmbeddingService):
    """
    Embedding service utilizing local SentenceTransformers models
    with a robust pure-python mock simulation state for offline tests.
    Equipped with a local memory cache to avoid redundant recalculations.
    """
    def __init__(self, mock_mode: Optional[bool] = None):
        self.mock_mode = settings.MOCK_LLM if mock_mode is None else mock_mode
        self.model_name = settings.EMBEDDING_MODEL
        self.dimension = 384  # Dimension for all-MiniLM-L6-v2
        
        # Local memory cache to save token computations
        # Map: text_sha256 -> List[float]
        self._cache: Dict[str, List[float]] = {}
        self.model = None

        if self.mock_mode:
            logger.info("EmbeddingService initialized in MOCK mode. Will simulate vectors locally.")
        else:
            try:
                logger.info(f"Loading local SentenceTransformer model: {self.model_name}...")
                from sentence_transformers import SentenceTransformer
                self.model = SentenceTransformer(self.model_name)
                logger.info("SentenceTransformer model loaded successfully.")
            except Exception as e:
                logger.error(f"Failed to load sentence-transformers: {e}. Falling back to MOCK vector engine.", exc_info=True)
                self.mock_mode = True

    def _get_hash(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def get_embedding(self, text: str) -> List[float]:
        """
        Retrieves the float vector representation of a text string.
        Utilizes local caching for instant retrieves on repeated text strings.
        """
        if not text:
            return [0.0] * self.dimension
            
        text_hash = self._get_hash(text)
        if text_hash in self._cache:
            return self._cache[text_hash]
            
        if self.mock_mode:
            vector = self._simulate_embedding(text)
        else:
            logger.debug(f"Computing local SentenceTransformer embedding for text (length: {len(text)})")
            vector = self.model.encode(text).tolist()
            
        self._cache[text_hash] = vector
        return vector

    def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Encodes a list of text strings in a single batch operation.
        Loads from cache where available.
        """
        results = []
        uncached_texts = []
        uncached_indices = []
        
        for idx, text in enumerate(texts):
            text_hash = self._get_hash(text)
            if text_hash in self._cache:
                results.append((idx, self._cache[text_hash]))
            else:
                uncached_texts.append(text)
                uncached_indices.append(idx)
                
        if uncached_texts:
            if self.mock_mode:
                uncached_vectors = [self._simulate_embedding(t) for t in uncached_texts]
            else:
                logger.info(f"Computing batch of {len(uncached_texts)} embeddings via SentenceTransformers.")
                start_time = time.perf_counter()
                embeddings_array = self.model.encode(uncached_texts)
                uncached_vectors = embeddings_array.tolist()
                logger.info(f"Batch embedding took {time.perf_counter() - start_time:.2f} seconds.")
                
            for idx, text, vector in zip(uncached_indices, uncached_texts, uncached_vectors):
                self._cache[self._get_hash(text)] = vector
                results.append((idx, vector))
                
        # Re-sort results to match the original index sequence
        results.sort(key=lambda x: x[0])
        return [r[1] for r in results]

    def _simulate_embedding(self, text: str) -> List[float]:
        """
        Generates a deterministic normalized unit vector of dimension 384
        based on the text hash. Ensures dot products match semantic similarity expectations.
        """
        text_hash = self._get_hash(text)
        # Seed python's random with hash to get deterministic vectors for identical strings
        rng = random.Random(text_hash.encode("utf-8"))
        
        # Populate raw values from Gaussian distribution with small base noise
        vector = [rng.gauss(0.0, 0.1) for _ in range(self.dimension)]
        
        # In a real RAG environment, we want mock search queries containing identical keywords
        # to have higher cosine similarity. Map keywords to wide overlapping bands.
        keywords_shift = {
            "python": (0, 40, 2.0),
            "sql": (40, 80, 2.0),
            "pytorch": (80, 120, 2.0),
            "tensorflow": (80, 120, 1.8), # Overlaps with PyTorch!
            "remote": (120, 160, 2.0),
            "bangalore": (160, 200, 2.0),
            "generative ai": (200, 240, 2.0),
            "llm": (200, 240, 2.2),
            "staff": (240, 280, 2.0),
            "junior": (280, 320, 2.0)
        }
        
        for kw, (start, end, weight) in keywords_shift.items():
            if kw in text.lower():
                for d in range(start, end):
                    vector[d] += weight
                    
        # Normalize to unit length (length = 1.0) so dot product equals cosine similarity
        magnitude = math.sqrt(sum(x * x for x in vector))
        if magnitude > 0.0:
            vector = [x / magnitude for x in vector]
            
        return vector
