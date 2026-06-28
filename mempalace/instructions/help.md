# MemPalace

AI memory system. Store everything, find anything. Local, free, no API key.

---

## Slash Commands

| Command              | Description                    |
|----------------------|--------------------------------|
| /mempalace:init      | Install and set up MemPalace   |
| /mempalace:search    | Search your memories           |
| /mempalace:mine      | Mine projects and conversations|
| /mempalace:status    | Palace overview and stats      |
| /mempalace:help      | This help message              |

---

## MCP Tools (30)

### Palace (read)

- mempalace_status -- Palace overview — total drawers, wing & room counts
- mempalace_list_wings -- List all wings with drawer counts
- mempalace_list_rooms -- List rooms within a wing (or all)
- mempalace_get_taxonomy -- Full taxonomy: wing → room → drawer count
- mempalace_search -- Semantic search with wing/room filter, distance threshold
- mempalace_check_duplicate -- Check if a memory already exists
- mempalace_get_drawer -- Fetch a single drawer by ID (full content + metadata)
- mempalace_list_drawers -- List drawers with pagination (wing/room filter, limit/offset)
- mempalace_get_aaak_spec -- Get the AAAK dialect specification

### Palace (write)

- mempalace_add_drawer -- File verbatim content into a wing/room
- mempalace_update_drawer -- Update an existing drawer's content / metadata
- mempalace_delete_drawer -- Delete a drawer by ID (irreversible)
- mempalace_sync -- Prune drawers from deleted/moved source files (dry-run by default)

### Knowledge Graph

- mempalace_kg_query -- Query entity relationships (outgoing/incoming/both, temporal filter)
- mempalace_kg_add -- Add a fact: subject → predicate → object (optional valid_from/valid_to)
- mempalace_kg_invalidate -- Mark a fact as no longer true
- mempalace_kg_timeline -- Chronological timeline of facts
- mempalace_kg_stats -- Knowledge graph overview: entities, triples, current vs expired

### Navigation (Palace Graph)

- mempalace_traverse -- Walk the palace graph from a room (BFS, max_hops)
- mempalace_find_tunnels -- Find rooms bridging two wings
- mempalace_create_tunnel -- Create a cross-wing tunnel
- mempalace_list_tunnels -- List all explicit tunnels (optional wing filter)
- mempalace_delete_tunnel -- Delete a tunnel by ID
- mempalace_follow_tunnels -- Follow tunnels from a room to connected wings
- mempalace_graph_stats -- Graph overview: rooms, tunnels, edges between wings

### Agent Diary

- mempalace_diary_write -- Write to agent diary in AAAK format
- mempalace_diary_read -- Read recent diary entries

### Settings & Hooks

- mempalace_hook_settings -- Get/set hook behavior (silent_save, desktop_toast)
- mempalace_memories_filed_away -- Check if a recent checkpoint was saved
- mempalace_reconnect -- Force reconnect after external writes

---

## CLI Commands

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
    mempalace hook run                    Run hook logic (for harness integration)
    mempalace instructions <name>         Output skill instructions

---

## Auto-Save Hooks

- Stop hook -- Automatically saves memories every 15 messages. Counts human
  messages in the session transcript (skipping command-messages). When the
  threshold is reached, blocks the AI with a save instruction. Uses
  ~/.mempalace/hook_state/ to track save points per session. If
  stop_hook_active is true, passes through to prevent infinite loops.

- PreCompact hook -- Emergency save before context compaction. Always blocks
  with a comprehensive save instruction because compaction means the AI is
  about to lose detailed context.

Hooks read JSON from stdin and output JSON to stdout. They can be invoked via:

    echo '{"session_id":"abc","stop_hook_active":false,"transcript_path":"..."}' | mempalace hook run --hook stop --harness claude-code

---

## Architecture

    Wings (projects/people)
      +-- Rooms (topics)
            +-- Closets (summaries)
                  +-- Drawers (verbatim memories)

    Halls connect rooms within a wing.
    Tunnels connect rooms across wings.

The palace is stored locally using ChromaDB for vector search and SQLite for
metadata. No cloud services or API keys required.

---

## Getting Started

1. /mempalace:init -- Set up your palace
2. /mempalace:mine -- Mine a project or conversation
3. /mempalace:search -- Find what you stored
