"""embed_all — Tạo embeddings cho toàn bộ Qdrant collections.

Đọc tất cả points từ 6 collections, tạo embedding bằng Ollama (nomic-embed-text),
và update vectors vào Qdrant.

Usage:
    python scripts/embed_all.py

Wing: tcdserver
Topic: mempalace_qdrant
Last Updated: 2026-05-02
"""

import logging
import os
import sys
import time
from typing import Optional

import requests

# ==================== CONFIG ====================

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", "")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text:latest")
EMBED_DIMENSION = 768

COLLECTIONS = [
    "meilin_tcdserver",
    "meilin_openclaw",
    "meilin_robotics",
    "meilin_code_chronicles",
    "meilin_omniscience_wiki",
    "meilin_conversation",
]

BATCH_SIZE = 50  # Số points gửi embedding cùng lúc
SCROLL_LIMIT = 100  # Số points đọc mỗi lần scroll

# ==================== LOGGING ====================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("embed_all")


# ==================== HELPERS ====================


def _headers():
    headers = {"Content-Type": "application/json"}
    if QDRANT_API_KEY:
        headers["api-key"] = QDRANT_API_KEY
    return headers


def get_embedding(text: str) -> Optional[list]:
    """Get embedding từ Ollama."""
    if not text or len(text.strip()) < 3:
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
        logger.warning(f"Embedding dimension mismatch: got {len(embedding) if embedding else 0}, expected {EMBED_DIMENSION}")
        return None
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        return None


def get_embeddings_batch(texts: list[str]) -> list[Optional[list]]:
    """Get embeddings cho nhiều texts cùng lúc (sequential do Ollama API)."""
    results = []
    for i, text in enumerate(texts):
        if i > 0 and i % 10 == 0:
            logger.info(f"  ... embedded {i}/{len(texts)}")
        results.append(get_embedding(text))
    return results


def scroll_points(collection: str, offset: Optional[str] = None) -> dict:
    """Scroll qua các points trong collection."""
    payload = {
        "limit": SCROLL_LIMIT,
        "with_payload": True,
        "with_vector": False,
    }
    if offset:
        payload["offset"] = offset

    resp = requests.post(
        f"{QDRANT_URL}/collections/{collection}/points/scroll",
        headers=_headers(),
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def update_vectors(collection: str, points_with_vectors: list[dict]) -> bool:
    """Update vectors cho các points."""
    if not points_with_vectors:
        return True

    payload = {"points": points_with_vectors}
    resp = requests.put(
        f"{QDRANT_URL}/collections/{collection}/points",
        headers=_headers(),
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    result = resp.json()
    return result.get("status") == "ok"


def get_collection_info(collection: str) -> dict:
    """Lấy thông tin collection."""
    resp = requests.get(
        f"{QDRANT_URL}/collections/{collection}",
        headers=_headers(),
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("result", {})


# ==================== MAIN ====================


def process_collection(collection: str) -> dict:
    """Process một collection: đọc points, tạo embedding, update vectors."""
    info = get_collection_info(collection)
    total_points = info.get("points_count", 0)
    total_vectors = info.get("vectors_count", 0)

    logger.info(f"\n{'='*60}")
    logger.info(f"Collection: {collection}")
    logger.info(f"  Points: {total_points}, Existing vectors: {total_vectors}")

    if total_vectors >= total_points:
        logger.info(f"  ✅ Đã có đủ vectors ({total_vectors}/{total_points}), skip.")
        return {"collection": collection, "processed": 0, "skipped": total_points}

    # Chỉ xử lý points chưa có vector
    points_to_embed = total_points - total_vectors
    logger.info(f"  Cần tạo embedding cho {points_to_embed} points")

    processed = 0
    failed = 0
    skipped = 0
    offset = None
    batch_points = []

    while True:
        # Scroll lấy points
        data = scroll_points(collection, offset)
        result = data.get("result", {})
        points = result.get("points", [])
        offset = result.get("next_page_offset")

        if not points:
            break

        for point in points:
            point_id = point.get("id")
            payload = point.get("payload", {})

            # Lấy content để tạo embedding
            content = payload.get("content", "")
            if not content or len(content.strip()) < 3:
                skipped += 1
                continue

            # Tạo embedding
            embedding = get_embedding(content)
            if not embedding:
                failed += 1
                continue

            batch_points.append({
                "id": point_id,
                "vector": embedding,
                "payload": payload,  # Giữ nguyên payload gốc
            })
            processed += 1

            # Batch update
            if len(batch_points) >= BATCH_SIZE:
                if update_vectors(collection, batch_points):
                    logger.info(f"  ✅ Batch {processed} points updated")
                else:
                    logger.error(f"  ❌ Batch update failed at point {processed}")
                batch_points = []

        # Qdrant scroll: break khi points < limit (đã hết)
        if len(points) < SCROLL_LIMIT:
            break
        if not offset:
            break

    # Flush batch cuối
    if batch_points:
        if update_vectors(collection, batch_points):
            logger.info(f"  ✅ Final batch {len(batch_points)} points updated")
        else:
            logger.error("  ❌ Final batch update failed")

    # Kiểm tra kết quả
    info_after = get_collection_info(collection)
    vectors_after = info_after.get("vectors_count", 0)

    logger.info(f"  Kết quả: processed={processed}, failed={failed}, skipped={skipped}")
    logger.info(f"  Vectors: {total_vectors} -> {vectors_after}")

    return {
        "collection": collection,
        "processed": processed,
        "failed": failed,
        "skipped": skipped,
        "vectors_before": total_vectors,
        "vectors_after": vectors_after,
    }


def main():
    logger.info("=" * 60)
    logger.info("EMBED ALL — Tạo embeddings cho Qdrant collections")
    logger.info(f"Ollama: {OLLAMA_URL} | Model: {EMBED_MODEL}")
    logger.info(f"Qdrant: {QDRANT_URL}")
    logger.info("=" * 60)

    # Kiểm tra Ollama
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=10)
        models = [m["name"] for m in resp.json().get("models", [])]
        logger.info(f"Ollama models: {models}")
        if EMBED_MODEL not in models:
            logger.warning(f"Model {EMBED_MODEL} not found! Pulling...")
            requests.post(f"{OLLAMA_URL}/api/pull", json={"name": EMBED_MODEL}, timeout=300)
    except Exception as e:
        logger.error(f"Cannot connect to Ollama: {e}")
        sys.exit(1)

    start_time = time.time()
    results = []

    for collection in COLLECTIONS:
        result = process_collection(collection)
        results.append(result)

    # Summary
    elapsed = time.time() - start_time
    total_processed = sum(r["processed"] for r in results)
    total_failed = sum(r["failed"] for r in results)
    total_skipped = sum(r["skipped"] for r in results)

    logger.info("\n" + "=" * 60)
    logger.info("SUMMARY")
    logger.info(f"Total time: {elapsed:.1f}s")
    logger.info(f"Total processed: {total_processed}")
    logger.info(f"Total failed: {total_failed}")
    logger.info(f"Total skipped: {total_skipped}")
    logger.info("=" * 60)

    for r in results:
        status = "✅" if r["vectors_after"] > r["vectors_before"] else "⏭️"
        logger.info(f"  {status} {r['collection']}: {r['vectors_before']} -> {r['vectors_after']} vectors")


if __name__ == "__main__":
    main()
