"""fix_threshold — Hạ indexing_threshold cho 2 collection nho."""

import os
import requests

API_KEY = os.environ.get("QDRANT_API_KEY", "")
H = {"Content-Type": "application/json"}
if API_KEY:
    H["api-key"] = API_KEY
BASE = os.environ.get("QDRANT_URL", "http://localhost:6333")

for col in ["meilin_omniscience_wiki", "meilin_conversation"]:
    r = requests.patch(
        f"{BASE}/collections/{col}",
        headers=H,
        json={"optimizers_config": {"indexing_threshold": 1}},
    )
    print(f"{col}: {r.status_code} {r.text[:200]}")
