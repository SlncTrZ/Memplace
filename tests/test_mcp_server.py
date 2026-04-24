"""test_mcp_server — Tests for MCP server protocol handling.

Wing: openclaw
Topic: mempalace_qdrant
Last Updated: 2026-04-24
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from mempalace.mcp_server import handle_request, dispatch_tool, TOOL_DEFINITIONS


class TestProtocol:
    """JSON-RPC protocol tests."""

    def test_initialize(self):
        resp = handle_request({"method": "initialize", "id": 1, "params": {}})
        assert resp["result"]["serverInfo"]["name"] == "mempalace"
        assert resp["id"] == 1

    def test_initialize_negotiates_client_version(self):
        resp = handle_request({
            "method": "initialize", "id": 1,
            "params": {"protocolVersion": "2025-03-26"},
        })
        assert resp["result"]["protocolVersion"] == "2025-03-26"

    def test_initialize_unknown_version_falls_back(self):
        resp = handle_request({
            "method": "initialize", "id": 1,
            "params": {"protocolVersion": "9999-12-31"},
        })
        from mempalace.mcp_server import SUPPORTED_PROTOCOL_VERSIONS
        assert resp["result"]["protocolVersion"] == SUPPORTED_PROTOCOL_VERSIONS[0]

    def test_ping(self):
        resp = handle_request({"method": "ping", "id": 11, "params": {}})
        assert resp["id"] == 11
        assert resp["result"] == {}

    def test_tools_list(self):
        resp = handle_request({"method": "tools/list", "id": 2, "params": {}})
        tools = resp["result"]["tools"]
        names = {t["name"] for t in tools}
        assert "mempalace_status" in names
        assert "mempalace_search" in names
        assert "mempalace_store" in names
        assert "mempalace_knowledge_store" in names
        assert "mempalace_knowledge_search" in names
        assert "mempalace_conversation_save" in names
        assert "mempalace_conversation_recall" in names
        assert "tech_store" in names
        assert "tech_find" in names

    def test_unknown_tool(self):
        resp = handle_request({
            "method": "tools/call", "id": 3,
            "params": {"name": "nonexistent_tool", "arguments": {}},
        })
        assert resp["error"]["code"] == -32601

    def test_unknown_method(self):
        resp = handle_request({"method": "unknown/method", "id": 4, "params": {}})
        assert resp["error"]["code"] == -32601

    def test_notification_returns_none(self):
        resp = handle_request({"method": "notifications/initialized", "params": {}})
        assert resp is None

    def test_null_arguments(self):
        with patch("mempalace.mcp_server.tool_qdrant_status") as mock_status:
            mock_status.return_value = {"backend": "qdrant", "total_points": 0}
            resp = handle_request({
                "method": "tools/call", "id": 10,
                "params": {"name": "mempalace_status", "arguments": None},
            })
            assert "result" in resp

    def test_tool_count(self):
        assert len(TOOL_DEFINITIONS) == 10


class TestDispatch:
    """Tool dispatch tests with mocked Qdrant backend."""

    @patch("mempalace.mcp_server.tool_qdrant_status")
    def test_status_dispatch(self, mock_status):
        mock_status.return_value = {"backend": "qdrant", "total_points": 100}
        result = dispatch_tool("mempalace_status", {})
        assert "content" in result
        data = json.loads(result["content"][0]["text"])
        assert data["total_points"] == 100

    @patch("mempalace.mcp_server.tool_qdrant_search")
    def test_search_dispatch(self, mock_search):
        mock_search.return_value = {"query": "test", "results": []}
        result = dispatch_tool("mempalace_search", {"query": "docker config"})
        assert "content" in result

    @patch("mempalace.mcp_server.tool_qdrant_store")
    def test_store_dispatch(self, mock_store):
        mock_store.return_value = {"success": True, "point_id": "abc-123"}
        result = dispatch_tool("mempalace_store", {"content": "test knowledge"})
        assert "content" in result

    @patch("mempalace.mcp_server.tool_qdrant_store")
    def test_knowledge_store_dispatch(self, mock_store):
        mock_store.return_value = {"success": True}
        result = dispatch_tool("mempalace_knowledge_store", {
            "content": "test", "wing": "openclaw", "topic": "test",
        })
        assert "content" in result

    @patch("mempalace.mcp_server.tool_qdrant_search")
    def test_conversation_recall_dispatch(self, mock_search):
        mock_search.return_value = {"results": []}
        result = dispatch_tool("mempalace_conversation_recall", {"query": "hello"})
        assert "content" in result
        # Verify wing=conversation was passed
        mock_search.assert_called_with(query="hello", wing="conversation", limit=5)

    @patch("mempalace.mcp_server.tool_qdrant_store")
    def test_conversation_save_dispatch(self, mock_store):
        mock_store.return_value = {"success": True}
        result = dispatch_tool("mempalace_conversation_save", {
            "content": "hello", "channel": "telegram",
        })
        assert "content" in result
        mock_store.assert_called_with(
            content="hello", wing="conversation", topic="telegram",
            entity_name="", entity_type="conversation", importance="medium",
        )

    @patch("mempalace.mcp_server.tool_qdrant_store")
    def test_tech_store_dispatch(self, mock_store):
        mock_store.return_value = {"success": True}
        result = dispatch_tool("tech_store", {
            "content": "SSH config", "action": "config_ssh", "subject": "RaspberryPi",
        })
        assert "content" in result
        mock_store.assert_called_with(
            content="SSH config", wing="openclaw", topic="config_ssh",
            entity_name="RaspberryPi", entity_type="tech", importance="medium",
        )

    @patch("mempalace.mcp_server.tool_qdrant_search")
    def test_tech_find_dispatch(self, mock_search):
        mock_search.return_value = {"results": []}
        result = dispatch_tool("tech_find", {"query": "SSH"})
        assert "content" in result

    def test_unknown_dispatch(self):
        result = dispatch_tool("nonexistent", {})
        assert "error" in result


class TestVersion:
    """Version consistency tests."""

    def test_version_exists(self):
        from mempalace.version import __version__
        assert __version__ == "4.0.0"

    def test_init_exports_version(self):
        from mempalace import __version__
        assert __version__