"""test_qdrant_bridge — Tests for Qdrant bridge module.

Wing: openclaw
Topic: mempalace_qdrant
Last Updated: 2026-04-24
"""

import pytest
from unittest.mock import patch, MagicMock

from mempalace.qdrant_bridge import (
    _resolve_collection,
    WING_COLLECTIONS,
    tool_qdrant_status,
    tool_qdrant_search,
    tool_qdrant_store,
)


class TestResolveCollection:
    def test_valid_wings(self):
        for wing in WING_COLLECTIONS:
            assert _resolve_collection(wing) == WING_COLLECTIONS[wing]

    def test_invalid_wing(self):
        assert _resolve_collection("invalid_wing") is None

    def test_none_wing(self):
        assert _resolve_collection(None) is None


class TestSearch:
    def test_query_too_short(self):
        result = tool_qdrant_search(query="ab")
        assert "error" in result

    @patch("mempalace.qdrant_bridge.get_embedding")
    def test_embedding_failure(self, mock_embed):
        mock_embed.return_value = None
        result = tool_qdrant_search(query="docker configuration")
        assert "error" in result

    @patch("mempalace.qdrant_bridge._qdrant_post")
    @patch("mempalace.qdrant_bridge.get_embedding")
    def test_search_success(self, mock_embed, mock_post):
        mock_embed.return_value = [0.1] * 768
        mock_post.return_value = {
            "result": [
                {
                    "id": "point-1",
                    "score": 0.95,
                    "payload": {
                        "content": "Docker compose configuration",
                        "metadata": {"wing": "openclaw", "topic": "docker"},
                    },
                }
            ]
        }
        result = tool_qdrant_search(query="docker", wing="openclaw")
        assert result["total_hits"] == 1
        assert result["results"][0]["score"] == 0.95

    def test_unknown_wing(self):
        result = tool_qdrant_search(query="test query", wing="invalid_wing")
        assert "error" in result


class TestStore:
    def test_content_too_short(self):
        result = tool_qdrant_store(content="short")
        assert "error" in result

    @patch("mempalace.qdrant_bridge.get_embedding")
    def test_embedding_failure(self, mock_embed):
        mock_embed.return_value = None
        result = tool_qdrant_store(content="This is a longer content for testing store")
        assert "error" in result

    def test_unknown_wing(self):
        result = tool_qdrant_store(content="This is valid content for testing", wing="invalid")
        assert "error" in result

    @patch("mempalace.qdrant_bridge._qdrant_put")
    @patch("mempalace.qdrant_bridge.get_embedding")
    def test_store_success(self, mock_embed, mock_put):
        mock_embed.return_value = [0.1] * 768
        mock_put.return_value = {"result": {"operation": "upsert"}}
        result = tool_qdrant_store(
            content="Docker compose file for deploying services",
            wing="openclaw",
            topic="docker_config",
        )
        assert result["success"] is True
        assert "point_id" in result


class TestStatus:
    @patch("mempalace.qdrant_bridge._qdrant_get")
    def test_status_all_collections(self, mock_get):
        def side_effect(path):
            return {
                "result": {
                    "points_count": 100,
                    "vectors_count": 100,
                    "indexed_vectors_count": 100,
                    "status": "green",
                }
            }
        mock_get.side_effect = side_effect
        result = tool_qdrant_status()
        assert result["total_points"] == 600  # 6 wings x 100
        assert len(result["wings"]) == 6

    @patch("mempalace.qdrant_bridge._qdrant_get")
    def test_status_collection_not_found(self, mock_get):
        mock_get.return_value = None
        result = tool_qdrant_status()
        assert result["total_points"] == 0
        for wing_info in result["wings"].values():
            assert wing_info["status"] == "not_found"