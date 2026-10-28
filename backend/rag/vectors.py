"""Qdrant wrapper. Payload holds only IDs and citation location; chunk text stays in SQLite."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qdrant_client import QdrantClient, models


@dataclass(frozen=True)
class Hit:
    chunk_id: int
    document_id: int
    score: float


class VectorStore:
    def __init__(self, client: QdrantClient, collection: str, dim: int) -> None:
        self.client = client
        self.collection = collection
        self.dim = dim

    @classmethod
    def connect(cls, url: str, collection: str, dim: int) -> VectorStore:
        # check_compatibility would make an extra request; versions are pinned together anyway.
        return cls(QdrantClient(url=url, timeout=30, check_compatibility=False), collection, dim)

    @classmethod
    def in_memory(cls, collection: str = "chunks", dim: int = 768) -> VectorStore:
        return cls(QdrantClient(location=":memory:"), collection, dim)

    def ensure_collection(self) -> None:
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                self.collection,
                vectors_config=models.VectorParams(size=self.dim, distance=models.Distance.COSINE),
            )
            self.client.create_payload_index(self.collection, "document_id", models.PayloadSchemaType.INTEGER)

    def upsert(self, items: list[tuple[int, list[float], dict[str, Any]]]) -> None:
        if not items:
            return
        points = [models.PointStruct(id=cid, vector=vec, payload=payload) for cid, vec, payload in items]
        for i in range(0, len(points), 256):
            self.client.upsert(self.collection, points=points[i : i + 256], wait=True)

    def delete_document(self, document_id: int) -> None:
        self.client.delete(
            self.collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id))]
                )
            ),
            wait=True,
        )

    def search(self, vector: list[float], limit: int, document_id: int | None = None) -> list[Hit]:
        flt = None
        if document_id is not None:
            flt = models.Filter(must=[models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id))])
        res = self.client.query_points(self.collection, query=vector, limit=limit, query_filter=flt, with_payload=True)
        return [
            Hit(chunk_id=int(p.id), document_id=int((p.payload or {})["document_id"]), score=float(p.score))
            for p in res.points
        ]

    def count(self) -> int:
        return int(self.client.count(self.collection, exact=True).count)
