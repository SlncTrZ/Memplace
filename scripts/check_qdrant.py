"""check_qdrant — Kiem tra trang thai Qdrant collections."""

import os
import requests
import sys
import io

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

API_KEY = os.environ.get("QDRANT_API_KEY", "")
HEADERS = {"api-key": API_KEY} if API_KEY else {"Content-Type": "application/json"}
BASE = os.environ.get("QDRANT_URL", "http://localhost:6333")

collections = [
    "meilin_tcdserver",
    "meilin_openclaw",
    "meilin_robotics",
    "meilin_code_chronicles",
    "meilin_omniscience_wiki",
    "meilin_conversation",
]

total_points = 0
total_indexed = 0

for col in collections:
    r = requests.get(f"{BASE}/collections/{col}", headers=HEADERS)
    info = r.json().get("result", {})
    pts = info.get("points_count", 0)
    idx = info.get("indexed_vectors_count", 0)
    total_points += pts
    total_indexed += idx
    status = "[OK]" if idx > 0 else "[..]"
    print(f"{status} {col}: points={pts}, indexed_vectors={idx}")

print(f"\nTOTAL: points={total_points}, indexed_vectors={total_indexed}")
