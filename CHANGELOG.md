# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [3.5.0] — 2026-06-28

### Added

- **Multi-Backend architecture**: Chroma (default), Qdrant, PgVector, SQLite Exact
- 30 MCP tools (from 10 in v4): Palace read/write, Knowledge Graph (5 tools),
  Navigation/Palace Graph (7 tools), Agent Diary (2 tools), Settings & Hooks (3 tools)
- **Knowledge Graph**: Temporal entity relationships with valid_from/valid_to, invalidation
- **Palace Graph**: Room navigation graph, cross-wing tunnels, BFS traversal
- **Agent Diary**: AAAK-compressed diary per agent name
- **CLI**: 12+ subcommands (init, mine, search, split, wake-up, compress, status, repair, mcp, hook, instructions)
- **AAAK Dialect**: Entity codes, emotion markers, 30x lossless compression
- **Entity Registry**: Maps names to AAAK codes, ambiguous name handling
- **Entity Detector**: Auto-detect people/projects from file content
- **General Extractor**: Classify text into 5 memory types
- **Auto-save Hooks**: Stop hook (every 15 messages), PreCompact hook
- **i18n**: 15 language translation files
- **Module expansion**: backups, repair, sweeper, migrate, daemon, dynamics,
  exporter, fact_checker, format_miner, corpus_origin, dedup, hallways, ids,
  sync, wal, palace_graph, closet_llm, convo_scanner, diary_ingest, spellcheck, sources
- **Sources framework** (RFC 002): BaseSourceAdapter pattern for extensible mining
- **Local ONNX embedding** (default): Zero-dependency, no API key needed

### Changed

- `qdrant_bridge.py` removed — replaced by `backends/` package (RFC 001)
- Architecture: Qdrant-only → Multi-Backend with Chroma as default
- MCP tools: 10 → 30 tools
- Embedding: Ollama-only → ONNX local (default) + Ollama (optional)
- Tool definitions: decorator-based → `TOOLS` dict in `mcp_server.py`
- Version: 5.0.0 → 3.5.0 (re-sync numbering)

### Removed

- `qdrant_bridge.py` — replaced by `backends/qdrant.py`
- `mempalace_store`, `mempalace_knowledge_store`, `mempalace_knowledge_search`
  — replaced by `mempalace_add_drawer` + Knowledge Graph tools

## [5.0.0] — 2026-05-01 (internal server)

See [CHANGELOG_V5.md](CHANGELOG_V5.md) for details.

### Added

- Dynamic Multi-Wing System (auto-detect from Qdrant)
- Pre-commit hook for API key detection
- `SECURITY.md` comprehensive security guide

## [4.0.0] — 2026-04-23

### Added

- 6-Wing Knowledge Palace architecture with Qdrant
- MCP (Model Context Protocol) server integration
- Knowledge Evolution system (soft delete + versioning)
- Conversation memory (save/recall)
- Technical knowledge store/search tools
- CI/CD pipeline (GitHub Actions — Python 3.9/3.11/3.13)
- Ruff linting integration

### Changed

- Migrated from ChromaDB to Qdrant as vector database
- Complete rewrite of knowledge management system
- New MCP-based tool interface

## [3.x] — Previous

### Added

- Initial ChromaDB-based knowledge storage
- Basic search and store functionality

## [2.x] — Previous

### Added

- Early prototype of memory palace concept
