"""Qdrant storage backend for MemPalace (RFC 001)."""
from __future__ import annotations
import logging
import os
import uuid
from typing import Any, Optional

import requests
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
    Filter as QdrantFilter,
    FieldCondition,
    MatchValue,
    MatchText,
    Range as QdrantRange,
    HasIdCondition,
)

from .base import (
    BackendClosedError,
    BaseBackend,
    BaseCollection,
    GetResult,
    HealthStatus,
    PalaceNotFoundError,
    PalaceRef,
    QueryResult,
    UnsupportedFilterError,
    _IncludeSpec,
)

logger = logging.getLogger(__name__)

_OLLAMA_BASE = os.getenv("OLLAMA_URL", "http://localhost:11434")
DEFAULT_QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
DEFAULT_QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
DEFAULT_OLLAMA_URL = os.getenv("OLLAMA_EMBED_URL", f"{_OLLAMA_BASE}/api/embeddings")
DEFAULT_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
EMBED_DIM = 768


def _stable_uuid(text: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, text))


def _get_embedding(text: str) -> Optional[list[float]]:
    _raw = os.getenv("OLLAMA_URL", "http://localhost:11434")
    _base = _raw.rstrip("/")
    url = os.getenv("OLLAMA_EMBED_URL", f"{_base}/api/embeddings")
    model = os.getenv("OLLAMA_EMBED_MODEL", DEFAULT_EMBED_MODEL)
    try:
        r = requests.post(url, json={"model": model, "prompt": text}, timeout=30.0)
        r.raise_for_status()
        return r.json()["embedding"]
    except Exception as e:
        logger.error("Ollama embedding failed: %s", e)
        return None


def _ensure_collection_exists(client: QdrantClient, name: str, dim: int = EMBED_DIM) -> None:
    if not client.collection_exists(name):
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
        logger.info("Created Qdrant collection '%s' (dim=%d, cosine)", name, dim)


def _convert_where(where: Optional[dict]) -> Optional[QdrantFilter]:
    if where is None:
        return None
    if not isinstance(where, dict):
        raise UnsupportedFilterError(f"where must be a dict, got {type(where).__name__}")
    conditions: list[FieldCondition] = []
    for key, value in where.items():
        if key in ("$and", "$or"):
            continue
        if isinstance(value, str):
            conditions.append(FieldCondition(key=f"metadata.{key}", match=MatchValue(value=value)))
        elif isinstance(value, dict):
            for op, val in value.items():
                if op == "$eq":
                    conditions.append(FieldCondition(key=f"metadata.{key}", match=MatchValue(value=str(val))))
                elif op == "$contains":
                    conditions.append(FieldCondition(key=f"metadata.{key}", match=MatchText(text=str(val))))
                elif op == "$gte" and isinstance(val, (int, float)):
                    conditions.append(FieldCondition(key=f"metadata.{key}", range=QdrantRange(gte=float(val))))
                elif op == "$lte" and isinstance(val, (int, float)):
                    conditions.append(FieldCondition(key=f"metadata.{key}", range=QdrantRange(lte=float(val))))
    if not conditions:
        return None
    return QdrantFilter(must=conditions)


class QdrantCollection(BaseCollection):
    def __init__(self, backend: "QdrantBackend", name: str):
        self._backend = backend
        self._name = name
        self._client = backend._lazy_client

    @property
    def metadata(self) -> dict:
        return {}

    def add(self, *, documents, ids, metadatas=None, embeddings=None):
        points = []
        for i, doc in enumerate(documents):
            pid = ids[i] if i < len(ids) else _stable_uuid(doc)
            qid = _stable_uuid(str(pid))
            vec = embeddings[i] if (embeddings and i < len(embeddings)) else _get_embedding(doc)
            if vec is None:
                logger.warning("Skipping doc '%s': embedding failed", pid)
                continue
            payload = {"document": doc, "metadata": (metadatas[i] if metadatas and i < len(metadatas) else {})}
            points.append(PointStruct(id=qid, vector=vec, payload=payload))
        if points:
            self._client.upsert(collection_name=self._name, points=points)

    def upsert(self, *, documents, ids, metadatas=None, embeddings=None):
        return self.add(documents=documents, ids=ids, metadatas=metadatas, embeddings=embeddings)

    def query(self, *, query_texts=None, query_embeddings=None, n_results=10, where=None, where_document=None, include=None):
        if (query_texts is None) == (query_embeddings is None):
            raise ValueError("query requires exactly one of query_texts or query_embeddings")
        query_vec = query_embeddings[0] if query_embeddings else (_get_embedding(query_texts[0]) or [0.0] * EMBED_DIM)
        spec = _IncludeSpec.resolve(include, default_distances=True)
        try:
            results = self._client.query_points(
                collection_name=self._name, query=query_vec, limit=n_results,
                with_payload=True, with_vectors=spec.embeddings, query_filter=_convert_where(where),
            )
        except Exception as e:
            logger.error("Qdrant query failed: %s", e)
            return QueryResult.empty(num_queries=1)
        hits = results.points if results and results.points else []
        if not hits:
            return QueryResult.empty(num_queries=1, embeddings_requested=spec.embeddings)
        return QueryResult(
            ids=[[str(p.id) for p in hits]],
            documents=[[(p.payload or {}).get("document", "") for p in hits]],
            metadatas=[[(p.payload or {}).get("metadata", {}) for p in hits]],
            distances=[[p.score or 0.0 for p in hits]],
            embeddings=[[p.vector or [] for p in hits]] if spec.embeddings else None,
        )

    def get(self, *, ids=None, where=None, where_document=None, limit=None, offset=None, include=None):
        spec = _IncludeSpec.resolve(include, default_distances=False)
        try:
            records, _ = self._client.scroll(
                collection_name=self._name, limit=limit or 100, offset=offset,
                with_payload=True, with_vectors=spec.embeddings,
                scroll_filter=_convert_where(where),
            )
        except Exception as e:
            logger.error("Qdrant scroll failed: %s", e)
            return GetResult.empty()
        ids_out, docs_out, metas_out = [], [], []
        embeds_out = None if not spec.embeddings else []
        for rec in records:
            ids_out.append(str(rec.id))
            docs_out.append((rec.payload or {}).get("document", ""))
            metas_out.append((rec.payload or {}).get("metadata", {}))
            if spec.embeddings and rec.vector:
                embeds_out.append(list(rec.vector))
        return GetResult(ids=ids_out, documents=docs_out, metadatas=metas_out, embeddings=embeds_out)

    def delete(self, *, ids=None, where=None):
        if ids:
            qids = [_stable_uuid(str(i)) for i in ids]
            self._client.delete(collection_name=self._name, points_selector=QdrantFilter(must=[HasIdCondition(has_id=qids)]))
        elif where:
            qfilter = _convert_where(where)
            if qfilter:
                self._client.delete(collection_name=self._name, points_selector=qfilter)
        else:
            self._client.delete(collection_name=self._name, points_selector=QdrantFilter())

    def count(self) -> int:
        try:
            return self._client.get_collection(self._name).points_count or 0
        except Exception:
            return 0


class QdrantBackend(BaseBackend):
    name = "qdrant"
    capabilities = frozenset({"supports_embeddings_in", "supports_embeddings_passthrough", "supports_embeddings_out", "supports_metadata_filters", "supports_contains_fast", "remote_mode"})

    def __init__(self):
        self._url = os.getenv("QDRANT_URL", DEFAULT_QDRANT_URL)
        self._api_key = os.getenv("QDRANT_API_KEY", DEFAULT_QDRANT_API_KEY)
        self._client: Optional[QdrantClient] = None
        self._closed = False

    @property
    def _lazy_client(self) -> QdrantClient:
        if self._client is None:
            kwargs: dict[str, Any] = {"url": self._url, "prefer_grpc": False}
            if self._api_key:
                kwargs["api_key"] = self._api_key
            self._client = QdrantClient(**kwargs)
        return self._client

    def get_collection(self, *args, **kwargs) -> QdrantCollection:
        if self._closed:
            raise BackendClosedError("QdrantBackend has been closed")
        palace_ref, collection_name, create, options = _normalize_args(args, kwargs)
        client = self._lazy_client
        full_name = collection_name
        if create:
            _ensure_collection_exists(client, full_name)
        elif not client.collection_exists(full_name):
            raise PalaceNotFoundError(f"Qdrant collection '{full_name}' not found")
        return QdrantCollection(self, full_name)

    def close(self) -> None:
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
        self._closed = True

    def health(self, palace: Optional[PalaceRef] = None) -> HealthStatus:
        if self._closed:
            return HealthStatus.unhealthy("backend closed")
        try:
            info = self._lazy_client.get_collections()
            return HealthStatus.healthy(f"Qdrant connected: {len(info.collections)} collections")
        except Exception as e:
            return HealthStatus.unhealthy(str(e))

    @classmethod
    def detect(cls, path: str) -> bool:
        return False


def _normalize_args(args, kwargs):
    if "palace" in kwargs:
        palace_ref = kwargs.pop("palace")
        if not isinstance(palace_ref, PalaceRef):
            raise TypeError("palace= must be a PalaceRef instance")
        collection_name = kwargs.pop("collection_name")
        create = kwargs.pop("create", False)
        options = kwargs.pop("options", None)
        if kwargs:
            raise TypeError(f"unexpected kwargs: {sorted(kwargs)}")
        if args:
            raise TypeError("positional args not allowed with palace= kwarg")
        return palace_ref, collection_name, create, options
    if args:
        palace_path = args[0]
        rest = list(args[1:])
        collection_name = kwargs.pop("collection_name", None) or (rest.pop(0) if rest else None)
        create = kwargs.pop("create", False)
        if rest:
            create = rest.pop(0)
        if kwargs:
            raise TypeError(f"unexpected kwargs: {sorted(kwargs)}")
        return PalaceRef(id=str(palace_path), local_path=str(palace_path) if isinstance(palace_path, str) else None), collection_name, bool(create), None
    if "palace_path" in kwargs:
        palace_path = kwargs.pop("palace_path")
        collection_name = kwargs.pop("collection_name")
        create = kwargs.pop("create", False)
        if kwargs:
            raise TypeError(f"unexpected kwargs: {sorted(kwargs)}")
        return PalaceRef(id=str(palace_path), local_path=str(palace_path) if isinstance(palace_path, str) else None), collection_name, bool(create), None
    raise TypeError("get_collection requires palace= or a positional palace_path")
