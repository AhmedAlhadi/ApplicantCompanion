"""Vector store abstraction with Qdrant and in-process backends (§3, §35).

Qdrant is used in production (VECTOR_STORE=qdrant). The in-process backend
keeps local development and CI fully self-contained; it implements the same
interface with brute-force cosine similarity.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..config import get_settings


@dataclass
class VectorRecord:
    id: str
    vector: list[float]
    payload: dict = field(default_factory=dict)


@dataclass
class ScoredRecord:
    id: str
    score: float
    payload: dict


class VectorStore:
    def upsert(self, records: list[VectorRecord]) -> None:  # pragma: no cover
        raise NotImplementedError

    def search(
        self, vector: list[float], limit: int = 20, where: dict | None = None
    ) -> list[ScoredRecord]:  # pragma: no cover
        raise NotImplementedError

    def delete(self, ids: list[str]) -> None:  # pragma: no cover
        raise NotImplementedError

    def clear(self) -> None:  # pragma: no cover
        raise NotImplementedError


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def _matches(payload: dict, where: dict | None) -> bool:
    if not where:
        return True
    for key, expected in where.items():
        value = payload.get(key)
        if isinstance(expected, (list, tuple, set)):
            if value not in expected:
                return False
        elif value != expected:
            return False
    return True


class MemoryVectorStore(VectorStore):
    def __init__(self):
        self._records: dict[str, VectorRecord] = {}

    def upsert(self, records: list[VectorRecord]) -> None:
        for rec in records:
            self._records[rec.id] = rec

    def search(self, vector, limit=20, where=None) -> list[ScoredRecord]:
        scored = [
            ScoredRecord(rec.id, _cosine(vector, rec.vector), rec.payload)
            for rec in self._records.values()
            if _matches(rec.payload, where)
        ]
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:limit]

    def delete(self, ids: list[str]) -> None:
        for i in ids:
            self._records.pop(i, None)

    def clear(self) -> None:
        self._records.clear()


class QdrantVectorStore(VectorStore):
    def __init__(self):
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams

        settings = get_settings()
        self._collection = settings.qdrant_collection
        self._client = QdrantClient(
            url=settings.qdrant_url, api_key=settings.qdrant_api_key or None
        )
        existing = {c.name for c in self._client.get_collections().collections}
        if self._collection not in existing:
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(size=settings.embedding_dim, distance=Distance.COSINE),
            )

    def upsert(self, records: list[VectorRecord]) -> None:
        from qdrant_client.models import PointStruct

        self._client.upsert(
            collection_name=self._collection,
            points=[PointStruct(id=r.id, vector=r.vector, payload=r.payload) for r in records],
        )

    def search(self, vector, limit=20, where=None) -> list[ScoredRecord]:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        qfilter = None
        if where:
            qfilter = Filter(
                must=[FieldCondition(key=k, match=MatchValue(value=v)) for k, v in where.items()]
            )
        hits = self._client.query_points(
            collection_name=self._collection, query=vector, limit=limit, query_filter=qfilter
        ).points
        return [ScoredRecord(str(h.id), h.score, h.payload or {}) for h in hits]

    def delete(self, ids: list[str]) -> None:
        self._client.delete(collection_name=self._collection, points_selector=ids)

    def clear(self) -> None:
        from qdrant_client.models import Filter

        self._client.delete(collection_name=self._collection, points_selector=Filter())


_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    global _store
    if _store is None:
        settings = get_settings()
        if settings.vector_store == "qdrant":
            try:
                _store = QdrantVectorStore()
            except Exception:  # qdrant-client missing or unreachable
                _store = MemoryVectorStore()
        else:
            _store = MemoryVectorStore()
    return _store


def reset_vector_store() -> None:
    global _store
    _store = None
