# MemPalace — 6-Wing Memory Palace

Qdrant-backed knowledge management for AI assistants. No ChromaDB.

## Architecture

6 Wings stored in Qdrant collections (`meilin_*`):

| Wing | Collection | Purpose |
|------|-----------|---------|
| tcdserver | meilin_tcdserver | Server infrastructure |
| openclaw | meilin_openclaw | AI/MeiLin knowledge |
| robotics | meilin_robotics | Robotics & hardware |
| code_chronicles | meilin_code_chronicles | Code history |
| omniscience_wiki | meilin_omniscience_wiki | General knowledge |
| conversation | meilin_conversation | Conversation memory |

## MCP Tools

- `mempalace_status` — Overview of all wings
- `mempalace_search` — Semantic search across wings
- `mempalace_store` — Store knowledge
- `mempalace_knowledge_store` — Store with Knowledge Evolution
- `mempalace_knowledge_search` — Search with filters
- `mempalace_conversation_save` / `recall` — Chat memory
- `tech_store` / `tech_find` — Technical knowledge

## Setup

```bash
pip install -e ".[dev]"
```

## Test

```bash
python -m pytest tests/ -v
```

## License

MIT