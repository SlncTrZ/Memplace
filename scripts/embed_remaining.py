"""embed_remaining — Embed 2 collection nho: omniscience_wiki (16) + conversation (4)."""

import os
import requests
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", "")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text:latest")
EMBED_DIM = 768


def h():
    headers = {"Content-Type": "application/json"}
    if QDRANT_API_KEY:
        headers["api-key"] = QDRANT_API_KEY
    return headers


def embed(text):
    if not text or len(text.strip()) < 3:
        return None
    clean = text[:800].replace("\n", " ").strip()
    r = requests.post(
        f"{OLLAMA_URL}/api/embeddings", json={"model": EMBED_MODEL, "prompt": clean}, timeout=45
    )
    r.raise_for_status()
    v = r.json().get("embedding")
    return v if v and len(v) == EMBED_DIM else None


def process(col):
    print(f"\n--- {col} ---")
    r = requests.get(f"{QDRANT_URL}/collections/{col}", headers=h())
    info = r.json()["result"]
    pts = info["points_count"]
    idx = info["indexed_vectors_count"]
    print(f"  points={pts}, indexed={idx}")

    if idx >= pts:
        print(f"  [OK] Da co du vectors")
        return

    offset = None
    batch = []
    processed = 0

    while True:
        payload = {"limit": 100, "with_payload": True, "with_vector": False}
        if offset:
            payload["offset"] = offset
        r = requests.post(
            f"{QDRANT_URL}/collections/{col}/points/scroll", headers=h(), json=payload, timeout=30
        )
        data = r.json()["result"]
        points = data.get("points", [])
        offset = data.get("next_page_offset")

        if not points:
            break

        for p in points:
            content = p["payload"].get("content", "")
            if not content or len(content.strip()) < 3:
                continue
            v = embed(content)
            if not v:
                continue
            batch.append({"id": p["id"], "vector": v, "payload": p["payload"]})
            processed += 1

            if len(batch) >= 50:
                requests.put(
                    f"{QDRANT_URL}/collections/{col}/points",
                    headers=h(),
                    json={"points": batch},
                    timeout=60,
                )
                print(f"  [OK] {processed} points")
                batch = []

        if len(points) < 100:
            break

    if batch:
        requests.put(
            f"{QDRANT_URL}/collections/{col}/points",
            headers=h(),
            json={"points": batch},
            timeout=60,
        )
        print(f"  [OK] Final {len(batch)} points")

    r = requests.get(f"{QDRANT_URL}/collections/{col}", headers=h())
    idx2 = r.json()["result"]["indexed_vectors_count"]
    print(f"  Result: {idx} -> {idx2} indexed vectors")


process("meilin_omniscience_wiki")
process("meilin_conversation")
print("\nDone!")
