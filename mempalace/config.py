"""config — Multi-Wing Palace configuration.

Wing: openclaw
Topic: mempalace_qdrant
Last Updated: 2026-05-09
"""

import os
import requests

QDRANT_URL = os.environ.get("QDRANT_URL", "http://192.168.1.227:6333")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", "")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text:latest")
EMBED_DIMENSION = 768

DEFAULT_WING_COLLECTIONS = {
    "tcdserver": "meilin_tcdserver",
    "openclaw": "meilin_openclaw",
    "robotics": "meilin_robotics",
    "code_chronicles": "meilin_code_chronicles",
    "omniscience_wiki": "meilin_omniscience_wiki",
    "conversation": "meilin_conversation",
}

def get_wing_collections():
    """Fetch wing collections from Qdrant, fallback to defaults if unreachable.
    
    Wings count depends on actual Qdrant collections available.
    Users can customize by setting WING_COLLECTIONS in environment as JSON string.
    """
    env_collections = os.environ.get("WING_COLLECTIONS")
    if env_collections:
        try:
            import json
            return json.loads(env_collections)
        except json.JSONDecodeError:
            pass
    
    try:
        headers = {"Content-Type": "application/json"}
        if QDRANT_API_KEY:
            headers["api-key"] = QDRANT_API_KEY
        
        resp = requests.get(f"{QDRANT_URL}/collections", headers=headers, timeout=5)
        resp.raise_for_status()
        
        collections = resp.json().get("result", {}).get("collections", [])
        meilin_collections = {
            col["name"].replace("meilin_", ""): col["name"]
            for col in collections
            if col["name"].startswith("meilin_")
        }
        
        if meilin_collections:
            return meilin_collections
    except Exception:
        pass
    
    return DEFAULT_WING_COLLECTIONS

WING_COLLECTIONS = get_wing_collections()
WING_NAMES = list(WING_COLLECTIONS.keys())