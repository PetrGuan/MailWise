"""Tests for embedding generation and vector search."""
from __future__ import annotations

import numpy as np

from email_issue_indexer.embeddings import EmbeddingEngine


class TestEmbed:
    def test_returns_normalized_vector(self, embedding_engine):
        vec = embedding_engine.embed("test query about database errors")
        assert vec.ndim == 1
        assert vec.shape[0] > 0
        # Normalized vectors have L2 norm ≈ 1.0
        assert abs(np.linalg.norm(vec) - 1.0) < 0.01

    def test_similar_texts_have_high_similarity(self, embedding_engine):
        v1 = embedding_engine.embed("database connection timeout")
        v2 = embedding_engine.embed("database connection error")
        v3 = embedding_engine.embed("recipe for chocolate cake")
        # Similar texts should score higher than unrelated
        sim_related = float(v1 @ v2)
        sim_unrelated = float(v1 @ v3)
        assert sim_related > sim_unrelated


class TestEmbedBatch:
    def test_returns_correct_shape(self, embedding_engine):
        texts = ["first text", "second text", "third text"]
        result = embedding_engine.embed_batch(texts, show_progress=False)
        assert result.shape[0] == 3
        assert result.shape[1] > 0

    def test_empty_list(self, embedding_engine):
        result = embedding_engine.embed_batch([], show_progress=False)
        assert len(result) == 0


class TestSearch:
    def test_ranking_order(self):
        """Search should return highest similarity first."""
        query = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        corpus = np.array([
            [0.1, 0.9, 0.0],   # low similarity
            [0.9, 0.1, 0.0],   # high similarity
            [0.5, 0.5, 0.0],   # medium similarity
        ], dtype=np.float32)
        # Normalize
        corpus = corpus / np.linalg.norm(corpus, axis=1, keepdims=True)

        results = EmbeddingEngine.search(query, corpus, top_k=3)
        indices = [idx for idx, _ in results]
        assert indices[0] == 1  # highest similarity first

    def test_expert_boost(self):
        """Expert boost should increase scores for expert messages."""
        query = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        corpus = np.array([
            [0.8, 0.2, 0.0],   # non-expert, high base similarity
            [0.5, 0.5, 0.0],   # expert, medium base similarity
        ], dtype=np.float32)
        corpus = corpus / np.linalg.norm(corpus, axis=1, keepdims=True)
        expert_mask = np.array([False, True])

        results = EmbeddingEngine.search(
            query, corpus, expert_mask=expert_mask, expert_boost=2.0, top_k=2
        )
        # With 2x boost, the expert (idx 1) should rank first
        assert results[0][0] == 1

    def test_top_k_limits_output(self):
        query = np.array([1.0, 0.0], dtype=np.float32)
        corpus = np.random.randn(100, 2).astype(np.float32)
        corpus = corpus / np.linalg.norm(corpus, axis=1, keepdims=True)

        results = EmbeddingEngine.search(query, corpus, top_k=5)
        assert len(results) == 5
