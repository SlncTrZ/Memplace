"""test_search — Kiem tra semantic search tren Qdrant."""
import os
import requests, json

API_KEY = os.environ.get("QDRANT_API_KEY", "")
H = {"Content-Type": "application/json"}
if API_KEY:
    H["api-key"] = API_KEY

QDRANT_URL = os.environ.get("QDRANT_URL", "http://192.168.1.227:6333")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

# 1. Embed query
query = "Docker compose configuration"
r = requests.post(f"{OLLAMA_URL}/api/embeddings",
    json={"model": "nomic-embed-text:latest", "prompt": query}, timeout=45)
v = r.json().get("embedding")
print(f"Query: {query}")
print(f"Embed dim: {len(v)}")

# 2. Search
r2 = requests.post(f"{QDRANT_URL}/collections/meilin_tcdserver/points/search",
    headers=H, json={"vector": v, "limit": 3, "with_payload": True}, timeout=30)
hits = r2.json().get("result", [])
print(f"Results: {len(hits)}")
for h in hits:
    score = h["score"]
    content = h["payload"].get("content", "")[:150]
    print(f"  score={score:.4f} | {content}")
