"""mcp_server — Multi-Wing Palace MCP Server (Qdrant-only).

Exposes tools for knowledge management via stdio JSON-RPC.
No ChromaDB dependency. Wings count depends on Qdrant collections.

Wing: openclaw
Topic: mempalace_qdrant
Last Updated: 2026-05-09
"""

import json
import sys

from .version import __version__
from .qdrant_bridge import (
    tool_qdrant_status,
    tool_qdrant_search,
    tool_qdrant_store,
    tool_qdrant_knowledge_store,
)

# Protocol versions we support (MCP spec)
SUPPORTED_PROTOCOL_VERSIONS = ["2025-11-25", "2025-03-26"]

# ==================== TOOL DEFINITIONS ====================

TOOL_DEFINITIONS = [
    {
        "name": "mempalace_status",
        "description": (
            "Multi-Wing Palace overview — collection sizes, vector counts, index status. "
            "Shows all wings available in Qdrant (dynamic, user-configurable). "
            "Default: tcdserver, openclaw, robotics, code_chronicles, omniscience_wiki, conversation."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "mempalace_search",
        "description": (
            "Semantic search across Multi-Wing Palace (meilin_* Qdrant collections). "
            "Uses Ollama nomic-embed-text embeddings. Searches all wings unless filtered. "
            "Available wings depend on Qdrant collections."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query — keywords or natural language",
                    "maxLength": 500,
                },
                "wing": {
                    "type": "string",
                    "description": "Filter by wing name (optional, depends on available wings)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 5, max 50)",
                    "minimum": 1,
                    "maximum": 50,
                },
                "score_threshold": {
                    "type": "number",
                    "description": "Min similarity 0-1 (default 0.3)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "mempalace_store",
        "description": (
            "Store knowledge into Multi-Wing Palace with metadata. "
            "Wings depend on Qdrant collections. Compatible with Cline MCP (meilin_knowledge) format."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Content to store",
                },
                "wing": {
                    "type": "string",
                    "description": "Target wing (default: openclaw)",
                },
                "topic": {
                    "type": "string",
                    "description": "Topic tag (default: general)",
                },
                "entity_name": {
                    "type": "string",
                    "description": "Entity name (optional)",
                },
                "entity_type": {
                    "type": "string",
                    "description": "Entity type: function|class|concept|skill|config",
                },
                "importance": {
                    "type": "string",
                    "description": "Importance: high|medium|low",
                },
            },
            "required": ["content"],
        },
    },
    {
        "name": "mempalace_knowledge_store",
        "description": (
            "Store knowledge into Multi-Wing Palace with Knowledge Evolution. "
            "Auto-classifies, embeds, soft-deletes old versions. Wings depend on Qdrant collections."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Knowledge content",
                },
                "wing": {
                    "type": "string",
                    "description": "Wing name (depends on available Qdrant collections)",
                },
                "topic": {
                    "type": "string",
                    "description": "Topic (e.g. docker_config, skill, code_evolution)",
                },
                "entity_name": {
                    "type": "string",
                    "description": "Entity name",
                },
                "entity_type": {
                    "type": "string",
                    "description": "Type: function|class|concept|skill|config",
                },
                "importance": {
                    "type": "string",
                    "description": "Importance: high|medium|low",
                },
                "change_reason": {
                    "type": "string",
                    "description": "Reason for change",
                },
            },
            "required": ["content", "wing", "topic"],
        },
    },
    {
        "name": "mempalace_knowledge_search",
        "description": (
            "Semantic search across Multi-Wing Palace. Returns results with score, wing, topic, version."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query",
                },
                "wing": {
                    "type": "string",
                    "description": "Filter by wing (optional)",
                },
                "topic": {
                    "type": "string",
                    "description": "Filter by topic (optional)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 5)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "knowledge_timeline",
        "description": "View evolution timeline of an entity (versions, changes).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "wing": {
                    "type": "string",
                    "description": "Wing name",
                },
                "entity_name": {
                    "type": "string",
                    "description": "Entity name",
                },
                "source_file": {
                    "type": "string",
                    "description": "Source file path",
                },
            },
            "required": ["wing"],
        },
    },
    {
        "name": "mempalace_conversation_save",
        "description": "Save conversation to memory room (meilin_conversation).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Conversation content",
                },
                "channel": {
                    "type": "string",
                    "description": "Channel: telegram|cline|openclaw|api",
                },
                "role": {
                    "type": "string",
                    "description": "Role: user|assistant|summary",
                },
                "session_id": {
                    "type": "string",
                    "description": "Session ID",
                },
                "importance": {
                    "type": "string",
                    "description": "Importance: high|medium|low",
                },
            },
            "required": ["content", "channel"],
        },
    },
    {
        "name": "mempalace_conversation_recall",
        "description": "Search conversation history. Semantic search across meilin_conversation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Query to recall",
                },
                "channel": {
                    "type": "string",
                    "description": "Filter: telegram|cline|openclaw",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 5)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "tech_store",
        "description": "Store technical knowledge with context metadata.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Content",
                },
                "action": {
                    "type": "string",
                    "description": "Action (e.g. config_ssh, update_firmware)",
                },
                "subject": {
                    "type": "string",
                    "description": "Subject (e.g. RaspberryPi, STM32, n8n)",
                },
                "importance": {
                    "type": "string",
                    "description": "Importance: high|medium|low",
                },
            },
            "required": ["content", "action", "subject"],
        },
    },
    {
        "name": "tech_find",
        "description": "Search technical knowledge across all wings.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Query",
                },
                "wing": {
                    "type": "string",
                    "description": "Filter by wing (optional)",
                },
            },
            "required": ["query"],
        },
    },
]


# ==================== DISPATCH ====================


def _tool_result(data):
    """Wrap data as MCP tool result."""
    return {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}]}


def _error_result(code, message):
    """Wrap error as MCP error."""
    return {"error": {"code": code, "message": message}}


def dispatch_tool(name, arguments):  # noqa: C901
    """Dispatch a tool call to the appropriate handler."""
    arguments = arguments or {}

    if name == "mempalace_status":
        return _tool_result(tool_qdrant_status())

    if name == "mempalace_search":
        return _tool_result(tool_qdrant_search(
            query=arguments.get("query", ""),
            wing=arguments.get("wing"),
            limit=arguments.get("limit", 5),
            score_threshold=arguments.get("score_threshold", 0.3),
        ))

    if name == "mempalace_store":
        return _tool_result(tool_qdrant_store(
            content=arguments.get("content", ""),
            wing=arguments.get("wing", "openclaw"),
            topic=arguments.get("topic", "general"),
            entity_name=arguments.get("entity_name"),
            entity_type=arguments.get("entity_type", "concept"),
            importance=arguments.get("importance", "medium"),
        ))

    if name == "mempalace_knowledge_store":
        return _tool_result(tool_qdrant_knowledge_store(
            content=arguments.get("content", ""),
            wing=arguments.get("wing", "openclaw"),
            topic=arguments.get("topic", "general"),
            entity_name=arguments.get("entity_name"),
            entity_type=arguments.get("entity_type", "concept"),
            importance=arguments.get("importance", "medium"),
            change_reason=arguments.get("change_reason"),
        ))

    if name == "mempalace_knowledge_search":
        return _tool_result(tool_qdrant_search(
            query=arguments.get("query", ""),
            wing=arguments.get("wing"),
            limit=arguments.get("limit", 5),
        ))

    if name == "knowledge_timeline":
        return _tool_result(tool_qdrant_search(
            query=arguments.get("entity_name", arguments.get("source_file", "")),
            wing=arguments.get("wing"),
            limit=5,
        ))

    if name == "mempalace_conversation_save":
        return _tool_result(tool_qdrant_store(
            content=arguments.get("content", ""),
            wing="conversation",
            topic=arguments.get("channel", "cline"),
            entity_name=arguments.get("session_id", ""),
            entity_type="conversation",
            importance=arguments.get("importance", "medium"),
        ))

    if name == "mempalace_conversation_recall":
        return _tool_result(tool_qdrant_search(
            query=arguments.get("query", ""),
            wing="conversation",
            limit=arguments.get("limit", 5),
        ))

    if name == "tech_store":
        return _tool_result(tool_qdrant_store(
            content=arguments.get("content", ""),
            wing="openclaw",
            topic=arguments.get("action", "general"),
            entity_name=arguments.get("subject", ""),
            entity_type="tech",
            importance=arguments.get("importance", "medium"),
        ))

    if name == "tech_find":
        return _tool_result(tool_qdrant_search(
            query=arguments.get("query", ""),
            wing=arguments.get("wing"),
            limit=5,
        ))

    return _error_result(-32601, f"Unknown tool: {name}")


# ==================== JSON-RPC SERVER ====================


def handle_request(msg):
    """Handle a single JSON-RPC request."""
    method = msg.get("method")
    msg_id = msg.get("id")
    params = msg.get("params", {})

    # Notifications (no id = no response)
    if msg_id is None and method and method.startswith("notifications/"):
        return None
    if msg_id is None and method != "initialize":
        return None

    # initialize
    if method == "initialize":
        client_version = params.get("protocolVersion", "")
        if client_version in SUPPORTED_PROTOCOL_VERSIONS:
            negotiated = client_version
        else:
            negotiated = SUPPORTED_PROTOCOL_VERSIONS[0]

        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": negotiated,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "mempalace", "version": __version__},
            },
        }

    # ping
    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

    # notifications/initialized
    if method == "notifications/initialized":
        return None

    # tools/list
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOL_DEFINITIONS}}

    # tools/call
    if method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments") or {}
        result = dispatch_tool(tool_name, arguments)
        if "error" in result:
            return {"jsonrpc": "2.0", "id": msg_id, "error": result["error"]}
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    # Unknown method
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}


def run_stdio():
    """Run MCP server over stdio (newline-delimited JSON-RPC)."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        response = handle_request(msg)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
