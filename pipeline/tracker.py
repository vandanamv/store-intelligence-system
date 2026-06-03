import numpy as np
import uuid
import time
from typing import Dict, List, Optional

class ReEntryTracker:
    def __init__(self, similarity_threshold: float = 0.85, cache_expiry_sec: float = 1200):
        # Gallery: visitor_id -> { "embeddings": List[np.ndarray], "last_seen": float }
        self.gallery: Dict[str, dict] = {}
        self.similarity_threshold = similarity_threshold
        self.cache_expiry_sec = cache_expiry_sec

    def generate_visitor_token(self) -> str:
        """Generates a random unique visitor token in the format VIS_xxxxxx"""
        val = uuid.uuid4().hex[:6]
        return f"VIS_{val}"

    def clean_expired_cache(self):
        """Cleans up visitor profiles that haven't been seen in the store for over 20 minutes"""
        now = time.time()
        expired_ids = []
        for visitor_id, profile in self.gallery.items():
            if now - profile["last_seen"] > self.cache_expiry_sec:
                expired_ids.append(visitor_id)
        for val in expired_ids:
            del self.gallery[val]

    def compute_cosine_similarity(self, v1: np.ndarray, v2: np.ndarray) -> float:
        dot_product = np.dot(v1, v2)
        norm_v1 = np.linalg.norm(v1)
        norm_v2 = np.linalg.norm(v2)
        if norm_v1 == 0 or norm_v2 == 0:
            return 0.0
        return float(dot_product / (norm_v1 * norm_v2))

    def update_and_match(self, embedding: np.ndarray) -> tuple[str, bool]:
        """
        Matches a new appearance embedding vector against the gallery.
        Returns: (visitor_id, is_reentry)
        """
        self.clean_expired_cache()
        best_similarity = 0.0
        matched_id = None
        
        # Compare with all active and cached visitor profiles
        for visitor_id, profile in self.gallery.items():
            # Calculate max similarity against all stored embeddings of this visitor
            for stored_emb in profile["embeddings"]:
                sim = self.compute_cosine_similarity(embedding, stored_emb)
                if sim > best_similarity:
                    best_similarity = sim
                    matched_id = visitor_id

        now = time.time()
        
        # Match threshold validation
        if best_similarity >= self.similarity_threshold and matched_id:
            # Matched existing visitor - update gallery profile
            profile = self.gallery[matched_id]
            profile["last_seen"] = now
            # Cap stored embeddings history to avoid memory growth
            if len(profile["embeddings"]) < 10:
                profile["embeddings"].append(embedding)
            else:
                profile["embeddings"].pop(0)
                profile["embeddings"].append(embedding)
                
            return matched_id, True
        else:
            # New visitor detected
            new_id = self.generate_visitor_token()
            self.gallery[new_id] = {
                "embeddings": [embedding],
                "last_seen": now
            }
            return new_id, False
            
    def simulate_mock_embedding(self, visitor_id: Optional[str] = None) -> np.ndarray:
        """
        Generates a stable 128-dimensional embedding vector for testing/simulation.
        If visitor_id is provided, generates a vector with slight noise around the visitor's core signature.
        """
        # Seed generator based on visitor_id string to guarantee stability
        if visitor_id:
            seed = sum(ord(c) for c in visitor_id)
            rng = np.random.default_rng(seed)
            base_vec = rng.standard_normal(128)
            # Add small Gaussian noise to simulate camera lens fluctuations
            noise = np.random.default_rng().normal(0, 0.05, 128)
            vec = base_vec + noise
        else:
            vec = np.random.default_rng().standard_normal(128)
            
        # Normalise vector to unit length
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec
