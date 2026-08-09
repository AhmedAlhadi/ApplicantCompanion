"""Embedding providers.

`hash`  — deterministic, offline bag-of-words hashing embedding. Produces
          stable vectors with real cosine-similarity semantics for overlapping
          vocabulary; powers dev mode and the test-suite.
`openai`— OpenAI embeddings API, used when a key is configured.
"""
from __future__ import annotations

import hashlib
import math
import re

import httpx

from ..config import get_settings

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#.\-]*")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class HashEmbeddingProvider:
    """Deterministic feature-hashing embedding (no external calls)."""

    name = "hash"

    def __init__(self, dim: int = 384):
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            vec = [0.0] * self.dim
            tokens = tokenize(text)
            for token in tokens:
                # unigram
                h = int(hashlib.blake2b(token.encode(), digest_size=8).hexdigest(), 16)
                vec[h % self.dim] += 1.0
                # character 3-gram for fuzzy term overlap
                for i in range(max(0, len(token) - 2)):
                    tri = token[i : i + 3]
                    th = int(hashlib.blake2b(tri.encode(), digest_size=8).hexdigest(), 16)
                    vec[th % self.dim] += 0.3
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            vectors.append([v / norm for v in vec])
        return vectors


class OpenAIEmbeddingProvider:
    name = "openai"

    def embed(self, texts: list[str]) -> list[list[float]]:
        settings = get_settings()
        resp = httpx.post(
            f"{settings.openai_base_url}/embeddings",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={"model": settings.embedding_model, "input": texts},
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return [item["embedding"] for item in sorted(data["data"], key=lambda d: d["index"])]


def get_embedding_provider():
    settings = get_settings()
    if settings.embedding_provider == "openai" and settings.openai_api_key:
        return OpenAIEmbeddingProvider()
    return HashEmbeddingProvider(dim=settings.embedding_dim)
