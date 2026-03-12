"""Embedding generation and vector similarity search."""
from __future__ import annotations

import numpy as np


class EmbeddingEngine:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self._model_name = model_name
        self._model = None

    @property
    def model(self):
        """Lazy-load the model to avoid import overhead when not needed."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)
        return self._model

    def embed(self, text: str) -> np.ndarray:
        """Embed a single text string."""
        return self.model.encode(text, normalize_embeddings=True)

    def embed_batch(self, texts: list[str], show_progress: bool = True) -> np.ndarray:
        """Embed a batch of texts."""
        if not texts:
            return np.array([])
        return self.model.encode(
            texts, normalize_embeddings=True,
            batch_size=64, show_progress_bar=show_progress,
        )

    @staticmethod
    def search(
        query_vec: np.ndarray,
        corpus_vecs: np.ndarray,
        expert_mask: np.ndarray | None = None,
        expert_boost: float = 1.5,
        top_k: int = 10,
    ) -> list[tuple[int, float]]:
        """Find top-k most similar vectors using cosine similarity.

        Returns list of (index, score) tuples, highest first.
        """
        scores = corpus_vecs @ query_vec
        if expert_mask is not None and expert_boost > 1.0:
            scores = scores.copy()
            scores[expert_mask] *= expert_boost

        k = min(top_k, len(scores))
        top_indices = np.argpartition(scores, -k)[-k:]
        top_indices = top_indices[np.argsort(scores[top_indices])[::-1]]
        return [(int(i), float(scores[i])) for i in top_indices]
