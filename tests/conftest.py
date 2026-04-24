"""conftest — Test fixtures for mempalace tests.

Wing: openclaw
Topic: mempalace_qdrant
Last Updated: 2026-04-24
"""

import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def mock_qdrant_status():
    """Mock Qdrant status response."""
    return {
        "backend": "qdrant",
        "qdrant_url": "http://localhost:6333",
        "ollama_url": "http://localhost:11434",
        "embed_model": "nomic-embed-text:latest",
        "wings": {
            "tcdserver": {"collection": "meilin_tcdserver", "points": 100, "status": "green"},
            "openclaw": {"collection": "meilin_openclaw", "points": 200, "status": "green"},
            "robotics": {"collection": "meilin_robotics", "points": 50, "status": "green"},
            "code_chronicles": {"collection": "meilin_code_chronicles", "points": 75, "status": "green"},
            "omniscience_wiki": {"collection": "meilin_omniscience_wiki", "points": 30, "status": "green"},
            "conversation": {"collection": "meilin_conversation", "points": 500, "status": "green"},
        },
        "total_points": 955,
    }


@pytest.fixture
def mock_embedding():
    """Return a fake 768-dim embedding vector."""
    return [0.1] * 768