"""test_mcp_server — Tests for MCP server protocol and tool dispatch.

Tests handle_request() JSON-RPC protocol (initialize, ping, tools/list,
tools/call) and verifies all 30 registered tools in the TOOLS dict.

No real backend is required — handlers are mocked via TOOLS dict patching.

Wing: openclaw | Topic: mempalace | Updated: 2026-06-28
"""

import json
from typing import Any
from unittest.mock import MagicMock

from mempalace.mcp_server import handle_request, TOOLS


# ── hardcoded reference for version assertions ──
EXPECTED_VERSION = "3.5.0"
SUPPORTED_PROTOCOL_VERSIONS = ["2024-11-05", "2025-03-26"]


def _call(method: str, params: dict | None = None, req_id: int = 1) -> dict[str, Any]:
    """Helper: send a JSON-RPC request and assert it returns a dict (not None)."""
    body: dict[str, Any] = {"method": method, "id": req_id}
    if params is not None:
        body["params"] = params
    resp = handle_request(body)
    assert resp is not None, f"handle_request returned None for method={method}"
    return resp


# ── Initialize ──


class TestInitialize:
    """JSON-RPC initialize handshake."""

    def test_default_initialize(self):
        resp = _call("initialize", {})
        assert resp["result"]["serverInfo"]["name"] == "mempalace"
        assert resp["result"]["serverInfo"]["version"] == EXPECTED_VERSION
        assert resp["id"] == 1
        assert "tools" in resp["result"]["capabilities"]

    def test_negotiates_known_version(self):
        resp = _call("initialize", {"protocolVersion": "2025-03-26"})
        assert resp["result"]["protocolVersion"] == "2025-03-26"

    def test_unknown_version_falls_back(self):
        resp = _call("initialize", {"protocolVersion": "9999-12-31"})
        assert resp["result"]["protocolVersion"] == SUPPORTED_PROTOCOL_VERSIONS[0]


# ── Ping ──


class TestPing:
    """JSON-RPC ping."""

    def test_ping(self):
        resp = _call("ping", {}, req_id=11)
        assert resp["id"] == 11
        assert resp["result"] == {}


# ── tools/list ──


class TestToolsList:
    """tools/list — returns all registered tool definitions."""

    def test_lists_all_tools(self):
        resp = _call("tools/list", req_id=2)
        tools = resp["result"]["tools"]
        names = {t["name"] for t in tools}
        # Core tools that MUST be present
        assert "mempalace_status" in names
        assert "mempalace_search" in names
        assert "mempalace_add_drawer" in names
        assert "mempalace_diary_write" in names
        assert "mempalace_diary_read" in names
        assert "mempalace_kg_query" in names
        assert "mempalace_kg_add" in names
        # Old names that should NOT exist anymore
        assert "mempalace_store" not in names
        assert "mempalace_knowledge_store" not in names
        assert "mempalace_knowledge_search" not in names
        assert "mempalace_conversation_save" not in names
        assert "mempalace_conversation_recall" not in names
        assert "tech_store" not in names
        assert "tech_find" not in names

    def test_every_tool_has_schema_and_handler(self):
        resp = _call("tools/list", req_id=2)
        for tool in resp["result"]["tools"]:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool
            assert isinstance(tool["inputSchema"], dict)

    def test_tool_count(self):
        assert len(TOOLS) == 30


# ── tools/call ──


class TestToolsCall:
    """tools/call — invokes handlers through the protocol."""

    def test_unknown_tool(self):
        resp = _call("tools/call", {"name": "nonexistent_tool", "arguments": {}}, req_id=3)
        assert resp["error"]["code"] == -32601

    def test_missing_name(self):
        resp = _call("tools/call", {"arguments": {}}, req_id=4)
        assert resp["error"]["code"] == -32602

    def test_null_arguments(self):
        """arguments=None should be treated as {}."""
        orig = TOOLS["mempalace_status"]["handler"]
        mock_handler = MagicMock(return_value={"total_drawers": 0})
        TOOLS["mempalace_status"]["handler"] = mock_handler
        try:
            resp = _call("tools/call", {"name": "mempalace_status", "arguments": None}, req_id=10)
            assert "result" in resp
            mock_handler.assert_called_once_with()
        finally:
            TOOLS["mempalace_status"]["handler"] = orig

    def test_handler_called_with_args(self):
        orig = TOOLS["mempalace_search"]["handler"]
        mock_handler = MagicMock(return_value={"results": []})
        TOOLS["mempalace_search"]["handler"] = mock_handler
        try:
            resp = _call(
                "tools/call",
                {"name": "mempalace_search", "arguments": {"query": "docker config"}},
                req_id=11,
            )
            assert "result" in resp
            mock_handler.assert_called_once_with(query="docker config")
        finally:
            TOOLS["mempalace_search"]["handler"] = orig

    def test_handler_returns_content_with_json_text(self):
        orig = TOOLS["mempalace_status"]["handler"]
        mock_handler = MagicMock(return_value={"total_drawers": 42, "wings": {}})
        TOOLS["mempalace_status"]["handler"] = mock_handler
        try:
            resp = _call("tools/call", {"name": "mempalace_status", "arguments": {}}, req_id=12)
            content = resp["result"]["content"]
            assert len(content) == 1
            assert content[0]["type"] == "text"
            data = json.loads(content[0]["text"])
            assert data["total_drawers"] == 42
        finally:
            TOOLS["mempalace_status"]["handler"] = orig

    def test_handler_error_bubbles_as_internal_error(self):
        orig = TOOLS["mempalace_status"]["handler"]
        TOOLS["mempalace_status"]["handler"] = MagicMock(side_effect=ValueError("boom"))
        try:
            resp = _call("tools/call", {"name": "mempalace_status", "arguments": {}}, req_id=13)
            assert resp["error"]["code"] == -32000
        finally:
            TOOLS["mempalace_status"]["handler"] = orig

    def test_argument_whitelist_filtering(self):
        """Only args declared in input_schema should be passed to handler.

        Use a real function (no **kwargs) so inspect detects no VAR_KEYWORD
        and the whitelist filter kicks in.
        """
        captured: dict = {}

        def _handler(query: str) -> dict:
            captured.clear()
            captured.update(query=query)
            return {"results": []}

        orig = TOOLS["mempalace_search"]["handler"]
        TOOLS["mempalace_search"]["handler"] = _handler
        try:
            _call(
                "tools/call",
                {
                    "name": "mempalace_search",
                    "arguments": {
                        "query": "test",
                        "added_by": "hacker",  # NOT in search schema
                        "source_file": "/etc/passwd",  # NOT in search schema
                    },
                },
                req_id=14,
            )
            # Only 'query' should reach the handler — the others are filtered
            assert captured == {"query": "test"}, f"Got: {captured}"
        finally:
            TOOLS["mempalace_search"]["handler"] = orig


# ── Error handling ──


class TestErrorHandling:
    """Edge cases and error paths."""

    def test_unknown_method(self):
        resp = _call("unknown/method", req_id=4)
        assert resp["error"]["code"] == -32601

    def test_invalid_request_not_dict(self):
        resp = handle_request("not a dict")
        assert resp is not None
        assert resp["error"]["code"] == -32600
        assert resp["id"] is None


# ── Notifications ──


class TestNotifications:
    """JSON-RPC notifications (no id) must get no response."""

    def test_initialized_notification_returns_none(self):
        resp = handle_request({"method": "notifications/initialized", "params": {}})
        assert resp is None

    def test_unknown_notification_returns_none(self):
        resp = handle_request({"method": "something/weird", "params": {}})
        assert resp is None


# ── Version ──


class TestVersion:
    """Version consistency."""

    def test_version_exists(self):
        from mempalace.version import __version__

        assert __version__ == EXPECTED_VERSION

    def test_init_exports_version(self):
        from mempalace import __version__

        assert __version__ == EXPECTED_VERSION
