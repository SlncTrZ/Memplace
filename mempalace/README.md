# mempalace/ — Core Package

The Python package that powers MemPalace. All modules, all logic.

## Modules

| Module | What it does |
|--------|-------------|
| `cli.py` | CLI entry point — routes to mine, search, init, compress, wake-up, and more (12+ subcommands) |
| `mcp_server.py` | MCP server — 30 MCP tools, Palace Protocol, agent diary |
| `config.py` | Configuration loading — `~/.mempalace/config.json`, env vars, defaults |
| `normalize.py` | Converts 5 chat formats (Claude Code JSONL, Claude.ai JSON, ChatGPT JSON, Slack JSON, plain text) to standard transcript format |
| `miner.py` | Project file ingest — scans directories, chunks by paragraph, stores to backend |
| `convo_miner.py` | Conversation ingest — chunks by exchange pair (Q+A), detects rooms from content |
| `searcher.py` | Semantic search — filters by wing/room, returns verbatim + scores |
| `layers.py` | 4-layer memory stack: L0 (identity), L1 (critical facts), L2 (room recall), L3 (deep search) |
| `dialect.py` | AAAK compression — entity codes, emotion markers, 30x lossless ratio |
| `knowledge_graph.py` | Temporal entity-relationship graph — SQLite, time-filtered queries, fact invalidation |
| `palace_graph.py` | Room-based navigation graph — BFS traversal, tunnel detection across wings |
| `onboarding.py` | Guided first-run setup — asks about people/projects, generates AAAK bootstrap + wing config |
| `entity_registry.py` | Entity code registry — maps names to AAAK codes, handles ambiguous names |
| `entity_detector.py` | Auto-detect people and projects from file content |
| `general_extractor.py` | Classifies text into 5 memory types (decision, preference, milestone, problem, emotional) |
| `room_detector_local.py` | Maps folders to room names using 70+ patterns — no API |
| `spellcheck.py` | Name-aware spellcheck — won't "correct" proper nouns in your entity registry |
| `split_mega_files.py` | Splits concatenated transcript files into per-session files |
| `backups.py` | Palace backup & restore |
| `repair.py` | Rebuild corrupted vector indices, fix inconsistencies |
| `sweeper.py` | Clean up stale/expired drawers |
| `migrate.py` | Schema migration across MemPalace versions |
| `daemon.py` | Background daemon for periodic maintenance |
| `dynamics.py` | Dynamic wing management (auto-detect, create) |
| `exporter.py` | Export palace data to various formats |
| `fact_checker.py` | Cross-reference facts across knowledge graph |
| `format_miner.py` | Extract structured data from formatted content |
| `corpus_origin.py` | Track corpus origin and provenance |
| `dedup.py` | Deduplicate drawers using semantic similarity |
| `hallways.py` | Hallway management (intra-wing room connections) |
| `ids.py` | ID generation and management |
| `sync.py` | Sync palace with filesystem (prune stale drawers) |
| `wal.py` | Write-ahead log for crash-safe operations |

## Architecture

```
User → CLI → miner/convo_miner → Palace (Chroma / Qdrant / PgVector / SQLite)
                                      ↕
                               knowledge_graph (SQLite — temporal facts)
                                      ↕
                               palace_graph (room navigation, tunnels)
                                      ↕
User → MCP Server → searcher   → results
                  → kg_query   → entity facts
                  → diary      → agent journal
                  → traverse   → room connections
```

The palace stores verbatim content in the chosen backend (default: Chroma). The knowledge graph (SQLite) stores temporal entity relationships (subject → predicate → object with valid_from/valid_to). The palace graph manages room-to-room navigation and cross-wing tunnels. The MCP server (30 tools) exposes all three to any AI tool via stdio JSON-RPC.

## Backends

| Backend | File | Best for |
|---------|------|---------|
| Chroma (default) | `backends/chroma.py` | Local, zero-config, single-user |
| Qdrant | `backends/qdrant.py` | Shared/multi-client palaces, server deployment |
| PgVector | `backends/pgvector.py` | Existing PostgreSQL deployments |
| SQLite Exact | `backends/sqlite_exact.py` | Debug, CI, tiny palaces, exact search |
