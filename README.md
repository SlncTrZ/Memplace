# MemPalace — Local-First AI Memory Palace

Give your AI a memory. Mine projects and conversations into a searchable palace.
No API key required. Exposed via MCP (Model Context Protocol) and CLI.

**Version:** 3.5.0 | **License:** MIT
[![CI](https://github.com/SlncTrZ/Memplace/actions/workflows/ci.yml/badge.svg)](https://github.com/SlncTrZ/Memplace/actions/workflows/ci.yml)

> **Forked from [MemPalace/mempalace](https://github.com/MemPalace/mempalace)** — đang được kiểm tra, nâng cấp và vận hành bởi [@SlncTrZ](https://github.com/SlncTrZ) (Trương Công Định)

---

## ⚠️ Trạng thái dự án

> Dự án này đang trong quá trình **kiểm tra, sửa lỗi và nâng cấp**. Một số thành phần có thể chưa ổn định hoặc đang được tái cấu trúc.

---

## 🚀 Nâng cấp từ bản gốc

| Khoản mục | Bản gốc | Bản này |
|-----------|---------|--------|
| **MCP Tools** | ~10 tools | **30 tools** — Palace R/W, Knowledge Graph, Navigation, Agent Diary, Hooks |
| **Storage Backend** | Qdrant-only | **4 backends** — Chroma (default), Qdrant, PgVector, SQLite Exact |
| **Embedding** | Ollama-dependent | **ONNX local** (zero-dep) + Ollama (optional) |
| **Knowledge Graph** | ❌ Không có | Temporal entity-relationship graph (SQLite, valid_from/valid_to, invalidation) |
| **Palace Navigation** | ❌ Không có | Room graph, BFS traversal, cross-wing tunnels, halls |
| **Agent Diary** | ❌ Không có | AAAK-compressed diary per agent, read/write tools |
| **i18n** | ❌ Không có | **15 ngôn ngữ** (EN, VI, JA, KO, ZH, FR, DE, ES, RU, IT, PT-BR, HI, ID, BE, ZH-TW) |
| **Sources Framework** | ❌ Không có | RFC 002 — extensible source adapters for mining |
| **Auto-Save Hooks** | ❌ Không có | Stop hook (15 msg), PreCompact hook |
| **AAAK Dialect** | ❌ Không có | Entity codes, emotion markers, 30× lossless compression |
| **Entity System** | ❌ Không có | Auto-detect people/projects, entity code registry |
| **CLI** | 5 subcommands | **12+ subcommands** (init, mine, search, split, wake-up, compress, status, repair, mcp, hook, instructions) |
| **Modules** | 8 modules | **32 modules** — thêm repair, backups, sweeper, migrate, daemon, dynamics, exporter, fact_checker, format_miner, corpus_origin, dedup, hallways, ids, sync, wal, closet_llm, convo_scanner, diary_ingest, spellcheck, sources |
| **Tests** | ~20 (lỗi import) | **139 tests pass** — protocol, backend registry, Chroma, Qdrant, error classes |
| **HTTP Server** | ❌ Không có | SSE transport + Qdrant query API + landing page |
| **Security** | API key trong code | Pre-commit hook, env vars, `.gitignore`, không hardcoded IP |
| **CLI Entry Point** | Không rõ ràng | `mempalace` + `mempalace-mcp` (pyproject.toml scripts) |

---

## Architecture

```
┌──────────────────────────────────────────────────┐
│         MCP Client (Claude Code / Cline)         │
│              ↓ stdio JSON-RPC                    │
├──────────────────────────────────────────────────┤
│          mcp_server.py — 30 MCP tools            │
├──────────────────────────────────────────────────┤
│   CLI (mempalace) ←→ Palace (ChromaDB / Qdrant) │
│                    ↕                             │
│         Knowledge Graph (SQLite, temporal)       │
│                    ↕                             │
│      Palace Graph (room navigation, tunnels)     │
├──────────────────────────────────────────────────┤
│   Backends: Chroma | Qdrant | PgVector | SQLite  │
│   Embeddings: ONNX (local) | Ollama | external   │
└──────────────────────────────────────────────────┘
```

### Palace Structure

```
Wings (projects/people)
  └── Rooms (topics)
        └── Closets (summaries)
              └── Drawers (verbatim memories)

Halls  → connect rooms within a wing
Tunnels → connect rooms across wings
```

## MCP Tools — 30 tools

### Palace (Read)

| Tool | Description |
|------|-------------|
| `mempalace_status` | Palace overview — total drawers, wing & room counts |
| `mempalace_list_wings` | List all wings with drawer counts |
| `mempalace_list_rooms` | List rooms within a wing (or all) |
| `mempalace_get_taxonomy` | Full taxonomy: wing → room → drawer count |
| `mempalace_search` | Semantic search — query, wing/room filter, distance threshold |
| `mempalace_check_duplicate` | Check if content already exists before filing |
| `mempalace_get_drawer` | Fetch a single drawer by ID (full content + metadata) |
| `mempalace_list_drawers` | List drawers with pagination, wing/room filter |
| `mempalace_get_aaak_spec` | Get the AAAK specification — ⚠️ lossy summary, not lossless compression |

### Palace (Write)

| Tool | Description |
|------|-------------|
| `mempalace_add_drawer` | File verbatim content into a wing/room |
| `mempalace_update_drawer` | Update an existing drawer's content / metadata |
| `mempalace_delete_drawer` | Delete a drawer by ID (irreversible) |
| `mempalace_sync` | Prune drawers from deleted/moved source files |

### Knowledge Graph (Temporal Facts)

| Tool | Description |
|------|-------------|
| `mempalace_kg_query` | Query entity relationships (outgoing/incoming/both) with temporal filter |
| `mempalace_kg_add` | Add a fact: subject → predicate → object (optional valid_from/valid_to) |
| `mempalace_kg_invalidate` | Mark a fact as no longer true |
| `mempalace_kg_timeline` | Chronological timeline of facts for an entity (or all) |
| `mempalace_kg_stats` | Knowledge graph overview: entities, triples, current vs expired |

### Navigation (Palace Graph)

| Tool | Description |
|------|-------------|
| `mempalace_traverse` | Walk the palace graph from a room (BFS, max_hops) |
| `mempalace_find_tunnels` | Find rooms bridging two wings |
| `mempalace_create_tunnel` | Create a cross-wing tunnel |
| `mempalace_list_tunnels` | List all explicit tunnels (optional wing filter) |
| `mempalace_delete_tunnel` | Delete a tunnel by ID |
| `mempalace_follow_tunnels` | Follow tunnels from a room to connected wings |
| `mempalace_graph_stats` | Graph overview: rooms, tunnels, edges between wings |

### Agent Diary

| Tool | Description |
|------|-------------|
| `mempalace_diary_write` | Write to agent diary in AAAK format |
| `mempalace_diary_read` | Read recent diary entries |

### Settings & Hooks

| Tool | Description |
|------|-------------|
| `mempalace_hook_settings` | Get/set hook behavior (silent_save, desktop_toast) |
| `mempalace_memories_filed_away` | Check if a recent checkpoint was saved |
| `mempalace_reconnect` | Force reconnect after external writes |

## CLI Commands

```bash
mempalace init <dir>                  Initialize a new palace
mempalace mine <dir>                  Mine a project (default mode)
mempalace mine <dir> --mode convos    Mine conversation exports
mempalace search "query"              Search your memories
mempalace split <dir>                 Split large transcript files
mempalace wake-up                     Load palace into context
mempalace compress                    Compress palace storage
mempalace status                      Show palace status
mempalace repair                      Rebuild vector index
mempalace mcp                         Show MCP setup command
mempalace hook run                    Run hook logic (for harness)
mempalace instructions <name>         Output skill instructions
```

## Setup

```bash
pip install -e ".[dev]"
# Or: pip install mempalace
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MEMPALACE_HOME` | `~/.mempalace` | Palace data directory |
| `MEMPALACE_EMBEDDING_DEVICE` | `auto` | Embedding device: `cpu`, `cuda`, `dml`, `coreml` |
| `PALACE_BACKEND` | `chroma` | Storage backend: `chroma`, `qdrant`, `pgvector`, `sqlite_exact` |
| `PALACE_PATH` | (auto) | Explicit palace path |
| `QDRANT_URL` | `http://localhost:6333` | Qdrant server URL (qdrant backend) |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server URL (optional) |

## Backends

| Backend | Purpose |
|---------|---------|
| **Chroma** (default) | Local vector store — zero config, no server needed |
| **Qdrant** | Remote vector DB — for shared/multi-client palaces |
| **PgVector** | PostgreSQL vector extension — for existing Postgres deployments |
| **SQLite Exact** | Exact (brute-force) search — debug, tiny palaces, CI |

## Embedding Options

- **Local ONNX model** (default) — zero-dependency, no API key
- **Ollama** — `nomic-embed-text:latest` (768d) or other models
- External embedding API (custom adapters)

## Key Modules

| Module | Description |
|--------|-------------|
| `cli.py` | CLI entry point — 12+ subcommands |
| `mcp_server.py` | MCP server — 30 MCP tools |
| `miner.py` | Project file ingest — chunks by paragraph |
| `convo_miner.py` | Conversation ingest — exchange pairs, room detection |
| `searcher.py` | Semantic search with filters |
| `layers.py` | 4-layer memory stack (L0 identity → L3 deep search) |
| `dialect.py` | AAAK compression — entity codes, 30× lossless ratio |
| `knowledge_graph.py` | Temporal entity-relationship graph (SQLite) |
| `palace_graph.py` | Room-based navigation graph (BFS, tunnels) |
| `entity_registry.py` | Entity code registry — AAAK codes, ambiguous names |
| `entity_detector.py` | Auto-detect people/projects from file content |
| `normalize.py` | Convert 5 chat formats to standard transcript |
| `onboarding.py` | Guided first-run setup |
| `backups.py` | Palace backup & restore |
| `repair.py` | Rebuild corrupted vector indices |
| `sweeper.py` | Clean up stale/expired drawers |
| `migrate.py` | Schema migration across versions |

## Test

```bash
python -m pytest tests/ -v
```

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/check_qdrant.py` | Check Qdrant collections status |
| `scripts/pre_commit_check.py` | Pre-commit API key scanner |
| `scripts/embed_all.py` | Full embedding pipeline |

## Security

See [SECURITY.md](SECURITY.md) for API key protection and pre-commit hook setup.

## ⚠️ Hạn chế hiện tại

### AAAK Dialect — Lossy Summary, không phải nén lossless

AAAK (`dialect.py`) là định dạng **tóm tắt có cấu trúc (structured summary)**, không phải nén lossless:

- **Nén (Compression)**: Xử lý cục bộ bằng Python (`dialect.py`) — dùng regex, keyword mapping, emotion dictionary, entity extraction. **Không gọi LLM.**
- **Giải nén (Decompression)**: Format được thiết kế để LLM đọc trực tiếp — không có decoder. LLM **suy diễn lại ngữ cảnh** từ các token còn lại, dẫn đến hallucination.
- **Dữ liệu gốc**: Verbatim content được lưu riêng trong **drawers** (ChromaDB/Qdrant). AAAK chỉ là summary layer để định hướng tra cứu, không thay thế dữ liệu gốc.
- Xem docstring đầu file `mempalace/dialect.py` để biết chi tiết.

### Các hạn chế khác

| Hạn chế | Mô tả |
|---------|-------|
| **MCP Server monolith** | `mcp_server.py` ~2k lines — 30 tools + request handler trong 1 file |
| **CLI monolith** | `cli.py` ~2k lines — 31 functions, quá nhiều responsibility |
| **Thiếu type hints** | Hầu hết các module chưa có type annotations đầy đủ |
| **Version history** | Lịch sử git đã qua force push / rebase — một số commit cũ có thể không trace được |
| **Phụ thuộc ChromaDB** | Backend mặc định ChromaDB có native dependencies (onnxruntime) có thể gây lỗi trên một số platform |
| **Documentation** | Chưa có API docs tự động (Sphinx/MkDocs) |
| **CI/CD** | Chưa có GitHub Actions workflow tự động |
| **HTTP Server coupling** | `http_server.py` hardcode Qdrant wings, không dùng backend abstraction |
| **Scripts technical debt** | `scripts/` có 7 script Python riêng lẻ trùng logic với code chính |

## License

MIT
