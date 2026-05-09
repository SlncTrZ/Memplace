# MemPalace — Multi-Wing Memory Palace

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
│  nomic-embed-text  │  Multi-Wing collections │
│  768 dimensions    │  (dynamic, user-config) │
└────────────────────┴────────────────────────┘
```

### Wings Architecture

**Multi-Wing Palace**: Số lượng wings phụ thuộc vào Qdrant collections có sẵn.

Users có thể:
- Sử dụng default 6 wings: tcdserver, openclaw, robotics, code_chronicles, omniscience_wiki, conversation
- Custom wings bằng cách tạo Qdrant collections với prefix `meilin_*`
- Config qua environment variable `WING_COLLECTIONS` (JSON format)

**Default Wings:**

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
| `mempalace_status` | Overview all wings (points, vectors, indexed, status) - dynamic based on Qdrant |

### Search & Store

| Tool | Params | Description |
|------|--------|-------------|
| `mempalace_search` | `query`, `wing?`, `limit?`(1-50), `score_threshold?`(0-1) | Semantic search across wings |
| `mempalace_store` | `content`, `wing?`(default=openclaw), `topic?`, `entity_name?`, `entity_type?`, `importance?` | Store knowledge |
| `mempalace_knowledge_store` | `content`, `wing`, `topic`, `entity_name?`, `entity_type?`, `importance?`, `change_reason?` | Store with Knowledge Evolution |
| `mempalace_knowledge_search` | `query`, `wing?`, `topic?`, `limit?` | Search across wings (depends on config) |
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
| `QDRANT_API_KEY` | (required) | Qdrant API key - **NEVER commit to git** |
| `OLLAMA_URL` | `http://ollama:11434` | Ollama server URL |
| `EMBED_MODEL` | `nomic-embed-text:latest` | Embedding model name |
| `WING_COLLECTIONS` | (auto-fetch) | JSON string mapping wings to Qdrant collections |

### Security: Protect API Keys

**CRITICAL: Khi public/commit GitHub repo:**

1. **Luôn dùng `.env` file** (đã có trong `.gitignore`)
2. **Không bao giờ hardcode API keys** trong code
3. **Chỉ commit `.env.example`** với placeholder values
4. **Verifying `.gitignore`** contains:
   ```
   .env
   *.key
   *_secrets.json
   ```

5. **Pre-commit hook (recommended):**
   ```bash
   # .git/hooks/pre-commit
   if git diff --cached --name-only | grep -E '\.(py|json|yaml|yml)$'; then
       if git diff --cached | grep -E 'api[_-]?key.*[=:][[:space:]]*['\''"'][^'\''"]+['\''"']'; then
           echo "ERROR: API key detected in staged files!"
           exit 1
       fi
   fi
   ```

### Custom Wings

Tùy chỉnh wings bằng environment variable:

```bash
export WING_COLLECTIONS='{"wing1": "meilin_wing1", "wing2": "meilin_wing2"}'
python -m mempalace
```

Hoặc tạo collections trong Qdrant với prefix `meilin_*` - MemPlace sẽ auto-detect.

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
| `check_qdrant.py` | Check all collections status (dynamic wings) |
| `test_search.py` | Manual semantic search test |
| `test_embed.py` | Test single point embedding |
| `embed_all.py` | Full embedding pipeline |
| `embed_remaining.py` | Embed remaining unprocessed points |
| `fix_threshold.py` | Lower indexing_threshold for small collections |

## License

MIT
