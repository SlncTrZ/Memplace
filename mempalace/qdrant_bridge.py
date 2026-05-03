"""qdrant_bridge — Qdrant 6-Wing Palace backend for MemPalace.

All knowledge stored in Qdrant vector database via REST API.
6 Wings: tcdserver, openclaw, robotics, code_chronicles, omniscience_wiki, conversation.

Wing: openclaw
Topic: mempalace_qdrant
Last Updated: 2026-04-24
"""

import logging
import uuid
from datetime import datetime
from typing import Optional

import requests

from .config import (
    QDRANT_URL,
    QDRANT_API_KEY,
    OLLAMA_URL,
    EMBED_MODEL,
    EMBED_DIMENSION,
    WING_COLLECTIONS,
)

logger = logging.getLogger("mempalace_mcp")

# ==================== LOW-LEVEL HELPERS ====================


def _qdrant_headers():
    headers = {"Content-Type": "application/json"}
    if QDRANT_API_KEY:
        headers["api-key"] = QDRANT_API_KEY
    return headers


def _qdrant_get(path: str, timeout: int = 10):
    """GET request to Qdrant REST API."""
    try:
        resp = requests.get(
            f"{QDRANT_URL}{path}", headers=_qdrant_headers(), timeout=timeout
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Qdrant GET {path} failed: {e}")
        return None


def _qdrant_post(path: str, data: dict, timeout: int = 30):
    """POST request to Qdrant REST API."""
    try:
        resp = requests.post(
            f"{QDRANT_URL}{path}", headers=_qdrant_headers(), json=data, timeout=timeout
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Qdrant POST {path} failed: {e}")
        return None


def _qdrant_put(path: str, data: dict, timeout: int = 30):
    """PUT request to Qdrant REST API."""
    try:
        resp = requests.put(
            f"{QDRANT_URL}{path}", headers=_qdrant_headers(), json=data, timeout=timeout
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Qdrant PUT {path} failed: {e}")
        return None


def get_embedding(text: str) -> Optional[list]:
    """Get embedding from Ollama."""
    if not text or len(text.strip()) < 5:
        return None
    clean = text[:800].replace("\n", " ").strip()
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": clean},
            timeout=45,
        )
        resp.raise_for_status()
        result = resp.json()
        embedding = result.get("embedding")
        if embedding and len(embedding) == EMBED_DIMENSION:
            return embedding
        got = len(embedding) if embedding else 0
        logger.warning(f"Embedding dimension mismatch: got {got}, expected {EMBED_DIMENSION}")
        return None
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        return None


def _resolve_collection(wing: str = None) -> str:
    """Resolve wing name to Qdrant collection name."""
    if wing and wing in WING_COLLECTIONS:
        return WING_COLLECTIONS[wing]
    return None


# ==================== TOOL IMPLEMENTATIONS ====================


def tool_qdrant_status():
    """Overview of 6-Wing Qdrant Palace — collection sizes and config."""
    result = {
        "backend": "qdrant",
        "qdrant_url": QDRANT_URL,
        "ollama_url": OLLAMA_URL,
        "embed_model": EMBED_MODEL,
        "wings": {},
        "total_points": 0,
    }

    for wing_name, collection_name in WING_COLLECTIONS.items():
        info = _qdrant_get(f"/collections/{collection_name}")
        if info and "result" in info:
            points = info["result"].get("points_count", 0)
            vectors = info["result"].get("vectors_count", 0)
            result["wings"][wing_name] = {
                "collection": collection_name,
                "points": points,
                "vectors": vectors,
                "indexed": info["result"].get("indexed_vectors_count", 0),
                "status": info["result"].get("status", "unknown"),
            }
            result["total_points"] += points
        else:
            result["wings"][wing_name] = {
                "collection": collection_name,
                "points": 0,
                "status": "not_found",
            }

    return result


def tool_qdrant_search(
    query: str,
    wing: str = None,
    limit: int = 5,
    score_threshold: float = 0.3,
):
    """Semantic search across 6-Wing Qdrant Palace. Uses Ollama embeddings."""
    if not query or len(query.strip()) < 3:
        return {"error": "Query too short (min 3 chars)"}

    limit = max(1, min(limit, 50))

    embedding = get_embedding(query)
    if not embedding:
        return {"error": "Failed to generate embedding. Check Ollama connectivity."}

    results = []
    collections_to_search = {}

    if wing:
        col_name = _resolve_collection(wing)
        if col_name:
            collections_to_search[wing] = col_name
        else:
            return {"error": f"Unknown wing: {wing}. Available: {list(WING_COLLECTIONS.keys())}"}
    else:
        collections_to_search = WING_COLLECTIONS

    for wing_name, collection_name in collections_to_search.items():
        search_data = {
            "vector": embedding,
            "limit": limit,
            "with_payload": True,
            "with_vector": False,
        }

        resp = _qdrant_post(
            f"/collections/{collection_name}/points/search",
            search_data,
        )

        if resp and "result" in resp:
            for hit in resp["result"]:
                score = hit.get("score", 0)
                if score >= score_threshold:
                    payload = hit.get("payload", {})
                    results.append({
                        "wing": wing_name,
                        "collection": collection_name,
                        "point_id": hit.get("id", ""),
                        "score": round(score, 4),
                        "content": payload.get("content", "")[:500],
                        "metadata": payload.get("metadata", {}),
                        "raw_payload_keys": list(payload.keys()),
                    })

    results.sort(key=lambda x: x["score"], reverse=True)
    results = results[:limit]

    return {
        "query": query[:100],
        "backend": "qdrant",
        "total_hits": len(results),
        "wings_searched": list(collections_to_search.keys()),
        "results": results,
    }


def tool_qdrant_store(
    content: str,
    wing: str = "openclaw",
    topic: str = "general",
    entity_name: str = None,
    entity_type: str = "concept",
    importance: str = "medium",
):
    """Store knowledge into 6-Wing Qdrant Palace with metadata."""
    if not content or len(content.strip()) < 10:
        return {"error": "Content too short (min 10 chars)"}

    collection_name = _resolve_collection(wing)
    if not collection_name:
        return {"error": f"Unknown wing: {wing}. Available: {list(WING_COLLECTIONS.keys())}"}

    embedding = get_embedding(content)
    if not embedding:
        return {"error": "Failed to generate embedding. Check Ollama connectivity."}

    point_id = str(uuid.uuid4())
    now = datetime.now().isoformat()

    payload = {
        "content": content[:2000],
        "metadata": {
            "wing": wing,
            "topic": topic,
            "entity_type": entity_type,
            "entity_name": entity_name or "",
            "importance": importance,
            "version": 1,
            "status": "active",
            "source": "mempalace_mcp",
            "created_at": now,
        },
    }

    data = {
        "points": [
            {
                "id": point_id,
                "vector": embedding,
                "payload": payload,
            }
        ]
    }

    resp = _qdrant_put(
        f"/collections/{collection_name}/points",
        data,
    )

    if resp and "result" in resp:
        logger.info(f"Qdrant store: {wing}/{topic} -> {point_id}")
        return {
            "success": True,
            "point_id": point_id,
            "wing": wing,
            "collection": collection_name,
            "topic": topic,
            "stored_at": now,
        }
    else:
        return {"success": False, "error": "Qdrant write failed", "detail": str(resp)}


def tool_qdrant_knowledge_store(
    content: str,
    wing: str = "openclaw",
    topic: str = "general",
    entity_name: str = None,
    entity_type: str = "concept",
    importance: str = "medium",
    change_reason: str = None,
):
    """Store knowledge with Knowledge Evolution — soft-deprecates old versions.

    If an active point with the same entity_name + wing exists, it gets
    soft-deprecated (status='deprecated') before the new version is stored.
    Max 2 deprecated versions retained per entity.
    """
    if not content or len(content.strip()) < 10:
        return {"error": "Content too short (min 10 chars)"}

    collection_name = _resolve_collection(wing)
    if not collection_name:
        return {"error": f"Unknown wing: {wing}. Available: {list(WING_COLLECTIONS.keys())}"}

    # Find existing active versions of this entity
    existing_version = 1
    existing_ids_to_deprecate = []

    if entity_name:
        # Search for existing entries with same entity_name
        search_data = {
            "vector": get_embedding(content) or [],
            "limit": 20,
            "with_payload": True,
            "with_vector": False,
        }
        # Use filter to find same entity
        search_data["filter"] = {
            "must": [
                {"key": "metadata.entity_name", "match": {"value": entity_name}},
                {"key": "metadata.wing", "match": {"value": wing}},
                {"key": "metadata.status", "match": {"value": "active"}},
            ]
        }
        # Need embedding for search
        embedding = get_embedding(content)
        if not embedding:
            return {"error": "Failed to generate embedding. Check Ollama connectivity."}
        search_data["vector"] = embedding

        resp = _qdrant_post(
            f"/collections/{collection_name}/points/scroll",
            {
                "filter": {
                    "must": [
                        {"key": "metadata.entity_name", "match": {"value": entity_name}},
                        {"key": "metadata.wing", "match": {"value": wing}},
                        {"key": "metadata.status", "match": {"value": "active"}},
                    ]
                },
                "limit": 10,
                "with_payload": True,
                "with_vector": False,
            },
        )

        if resp and "result" in resp:
            points = resp["result"].get("points", [])
            for pt in points:
                meta = pt.get("payload", {}).get("metadata", {})
                existing_version = max(existing_version, meta.get("version", 0))
                existing_ids_to_deprecate.append(pt["id"])

    # Soft-deprecate old active versions
    for old_id in existing_ids_to_deprecate:
        # Fetch current payload by point ID
        get_resp = _qdrant_post(
            f"/collections/{collection_name}/points",
            {"ids": [old_id], "with_payload": True, "with_vector": False},
        )
        if get_resp and "result" in get_resp:
            result = get_resp["result"]
            pts = result.get("points", []) if isinstance(result, dict) else (result if isinstance(result, list) else [])
            if pts:
                old_meta = pts[0].get("payload", {}).get("metadata", {})
                old_meta["status"] = "deprecated"
                old_meta["deprecated_at"] = datetime.now().isoformat()
                # Use POST /points/payload with full metadata object
                _qdrant_post(
                    f"/collections/{collection_name}/points/payload",
                    {"points": [old_id], "payload": {"metadata": old_meta}},
                )
            else:
                logger.warning(f"No points found for ID {old_id[:12]}...")
        else:
            logger.warning(f"Failed to fetch point {old_id[:12]}... response: {get_resp}")

    # Store new version
    embedding = embedding if entity_name else get_embedding(content)
    if not embedding:
        return {"error": "Failed to generate embedding. Check Ollama connectivity."}

    point_id = str(uuid.uuid4())
    now = datetime.now().isoformat()

    payload = {
        "content": content[:2000],
        "metadata": {
            "wing": wing,
            "topic": topic,
            "entity_type": entity_type,
            "entity_name": entity_name or "",
            "importance": importance,
            "version": existing_version + 1,
            "status": "active",
            "source": "mempalace_mcp",
            "created_at": now,
            "change_reason": change_reason or "",
            "parent_ids": existing_ids_to_deprecate[-2:],  # Keep last 2 deprecated refs
        },
    }

    data = {
        "points": [
            {
                "id": point_id,
                "vector": embedding,
                "payload": payload,
            }
        ]
    }

    resp = _qdrant_put(
        f"/collections/{collection_name}/points",
        data,
    )

    if resp and "result" in resp:
        logger.info(f"Qdrant knowledge_store: {wing}/{topic} v{existing_version + 1} -> {point_id}")
        return {
            "success": True,
            "point_id": point_id,
            "wing": wing,
            "collection": collection_name,
            "topic": topic,
            "version": existing_version + 1,
            "deprecated_count": len(existing_ids_to_deprecate),
            "stored_at": now,
        }
    else:
        return {"success": False, "error": "Qdrant write failed", "detail": str(resp)}