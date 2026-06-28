"""conftest — Shared fixtures for MemPalace tests.

Wing: openclaw | Topic: mempalace | Updated: 2026-06-28
"""

from unittest.mock import MagicMock

import pytest


def _patch_tool(tool_name, response):
    """Context manager: temporarily replace a tool handler in TOOLS dict."""
    from mempalace.mcp_server import TOOLS

    _orig = TOOLS[tool_name]["handler"]
    TOOLS[tool_name]["handler"] = MagicMock(return_value=response)
    return _orig


def _unpatch_tool(tool_name, orig_handler):
    """Restore original tool handler."""
    from mempalace.mcp_server import TOOLS

    TOOLS[tool_name]["handler"] = orig_handler


@pytest.fixture
def mock_tool_response():
    """Return a (start, stop) pair for temporarily patching a tool handler.

    Usage::

        orig = mock_tool_response("mempalace_status", {"total_drawers": 42})
        try:
            resp = handle_request({...})
        finally:
            mock_tool_response.stop("mempalace_status", orig)
    """
    return _patch_tool


@pytest.fixture
def sample_drawer_data():
    """Sample drawer metadata for unit tests."""
    return {
        "id": "drawer-001",
        "wing": "test_wing",
        "room": "test_room",
        "content": "This is test content for MemPalace unit tests.",
        "source_file": "/test/source.md",
        "added_by": "mcp",
        "filed_at": "2026-06-28T12:00:00",
    }


@pytest.fixture
def sample_kg_data():
    """Sample knowledge graph triple for unit tests."""
    return {
        "subject": "TestEntity",
        "predicate": "test_relation",
        "object": "TestValue",
        "valid_from": "2026-01-01",
        "valid_to": None,
    }
