"""config — 6-Wing Palace configuration.

Wing: openclaw
Topic: mempalace_qdrant
Last Updated: 2026-04-24
"""

import os

QDRANT_URL = os.environ.get("QDRANT_URL", "http://192.168.1.227:6333")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", "")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text:latest")
EMBED_DIMENSION = 768

WING_NAMES = [
    "tcdserver",
    "openclaw",
    "robotics",
    "code_chronicles",
    "omniscience_wiki",
    "conversation",
]

WING_COLLECTIONS = {
    "tcdserver": "meilin_tcdserver",
    "openclaw": "meilin_openclaw",
    "robotics": "meilin_robotics",
    "code_chronicles": "meilin_code_chronicles",
    "omniscience_wiki": "meilin_omniscience_wiki",
    "conversation": "meilin_conversation",
}