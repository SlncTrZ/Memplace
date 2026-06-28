import os
import requests, json

API_KEY = os.environ.get("QDRANT_API_KEY", "")
H = {"Content-Type": "application/json"}
if API_KEY:
    H["api-key"] = API_KEY

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

# Lay 1 point
r = requests.post(f"{QDRANT_URL}/collections/meilin_omniscience_wiki/points/scroll", headers=H, json={"limit": 1, "with_payload": True, "with_vector": False})
p = r.json()["result"]["points"][0]
pid = p["id"]
c = p["payload"].get("content", "")
print(f"ID={pid}")
print(f"Content={c[:100]}")

# Embed
r2 = requests.post(f"{OLLAMA_URL}/api/embeddings", json={"model": "nomic-embed-text:latest", "prompt": c[:800].replace(chr(10), " ").strip()}, timeout=45)
v = r2.json().get("embedding")
print(f"Embed dim={len(v)}")

# PUT
r3 = requests.put(f"{QDRANT_URL}/collections/meilin_omniscience_wiki/points", headers=H, json={"points": [{"id": pid, "vector": v, "payload": p["payload"]}]}, timeout=60)
print(f"PUT={r3.status_code} {r3.text[:200]}")

# Check
r4 = requests.get(f"{QDRANT_URL}/collections/meilin_omniscience_wiki", headers=H)
d = r4.json()["result"]
print(f"After: pts={d['points_count']} idx={d['indexed_vectors_count']}")
