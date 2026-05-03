# MemPalace — 6-Wing Memory Palace

Qdrant-backed knowledge management cho AI assistants, exposed qua MCP (Model Context Protocol).

## Kiến trúc

```
┌─────────────────────────────────────────────┐
│           MCP Client (Cline/AI)             │
│              ↓ stdio JSON-RPC               │
├─────────────────────────────────────────────┤
│           mcp_server.py (10 tools)          │
│           dispatch_tool()                   │
├─────────────────────────────────────────────┤
│           qdrant_bridge.py                  │
│           get_embedding()                   │
├────────────────────┬────────────────────────┤
│    Ollama API      │    Qdrant REST API     │
│  nomic-embed-text  │  6 collections         │
│  768 dimensions    │  meilin_* prefix       │
└────────────────────┴────────────────────────┘
```

### 6 Wings

| Wing | Collection | Purpose |
|------|-----------|---------|
| tcdserver | meilin_tcdserver | Server infrastructure & operations |
| openclaw | meilin_openclaw | AI/MeiLin knowledge & skills |
| robotics | meilin_robotics | Robotics & hardware |
| code_chronicles | meilin_code_chronicles | Code evolution history |
| omniscience_wiki | meilin_omniscience_wiki | General knowledge encyclopedia |
| conversation | meilin_conversation | Chat history & memory |

## MCP Tools

### System

| Tool | Description |
|------|-------------|
| `mempalace_status` | Overview all 6 wings (points, vectors, indexed, status) |

### Search & Store

| Tool | Params | Description |
|------|--------|-------------|
| `mempalace_search` | `query`, `wing?`, `limit?`(1-50), `score_threshold?`(0-1) | Semantic search across wings |
| `mempalace_store` | `content`, `wing?`(default=openclaw), `topic?`, `entity_name?`, `entity_type?`, `importance?` | Store knowledge |
| `mempalace_knowledge_store` | `content`, `wing`, `topic`, `entity_name?`, `entity_type?`, `importance?`, `change_reason?` | Store with Knowledge Evolution |
| `mempalace_knowledge_search` | `query`, `wing?`, `topic?`, `limit?` | Search across 5 wings (excludes conversation) |
| `knowledge_timeline` | `wing`, `entity_name?`, `source_file?` | View entity evolution history |

### Conversation

| Tool | Params | Description |
|------|--------|-------------|
| `mempalace_conversation_save` | `content`, `channel`, `role?`, `session_id?`, `importance?` | Save to conversation wing |
| `mempalace_conversation_recall` | `query`, `channel?`, `limit?` | Search conversation history |

### Technical Knowledge

| Tool | Params | Description |
|------|--------|-------------|
| `tech_store` | `content`, `action`, `subject`, `importance?` | Store tech knowledge (wing=openclaw, entity_type=tech) |
| `tech_find` | `query`, `wing?` | Search tech knowledge |

## Setup

```bash
pip install -e ".[dev]"
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `QDRANT_URL` | `http://192.168.1.227:6333` | Qdrant server URL |
| `QDRANT_API_KEY` | (required) | Qdrant API key |
| `OLLAMA_URL` | `http://ollama:11434` | Ollama server URL |
| `EMBED_MODEL` | `nomic-embed-text:latest` | Embedding model name |

## Payload Structure

```json
{
  "content": "knowledge text...",
  "metadata": {
    "wing": "openclaw",
    "topic": "docker_config",
    "entity_type": "config",
    "entity_name": "qdrant_setup",
    "importance": "high",
    "version": 1,
    "status": "active",
    "source": "mempalace_mcp",
    "created_at": "2026-04-23T10:30:00"
  }
}
```

## Embedding Pipeline

- Model: `nomic-embed-text:latest` via Ollama
- Dimension: 768
- Text truncated to 800 chars for embedding
- Min content: 5 chars (embed), 10 chars (store)
- Score threshold default: 0.3

## Test

```bash
python -m pytest tests/ -v
```

## Scripts

| Script | Purpose |
|--------|---------|
| `check_qdrant.py` | Check 6 collections status |
| `test_search.py` | Manual semantic search test |
| `test_embed.py` | Test single point embedding |
| `embed_all.py` | Full embedding pipeline |
| `embed_remaining.py` | Embed remaining unprocessed points |
| `fix_threshold.py` | Lower indexing_threshold for small collections |

## License

MIT
