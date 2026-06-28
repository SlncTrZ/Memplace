"""_main — CLI entry point + argparse setup + dispatch.

Wing: mempalace | Topic: cli | Updated: 2026-06-28
"""

import os
import argparse

from ..version import __version__


_EXPLICIT_BACKEND_ENV = "MEMPALACE_BACKEND_EXPLICIT"

# Keep parser construction lightweight for --version and hook commands.
_CLI_MAX_CHUNKS_PER_FILE_DEFAULT = 50_000


# ── Shared backend helpers ────────────────────────────────────────────────


def _backend_arg(args):
    """Return a CLI-selected backend from subcommand or global flags."""
    return getattr(args, "backend", None) or getattr(args, "global_backend", None)


def _apply_backend_arg(args) -> None:
    backend = _backend_arg(args)
    if not backend:
        return
    backend = str(backend).strip().lower()
    from ..backends import get_backend_class

    get_backend_class(backend)
    os.environ[_EXPLICIT_BACKEND_ENV] = backend
    os.environ["MEMPALACE_BACKEND"] = backend


def _selected_backend_for_palace(palace_path: str) -> str:
    from ..palace import resolve_backend_name

    return resolve_backend_name(palace_path, explicit=os.environ.get(_EXPLICIT_BACKEND_ENV))


# ── Stdio helpers ─────────────────────────────────────────────────────────


def _reconfigure_stdio_utf8_on_windows():
    """Decode stdio as UTF-8 on Windows for the primary ``mempalace`` CLI.

    Thin wrapper around the shared helper in ``mempalace._stdio``. The CLI
    overrides stdout/stderr to ``replace`` because ``mempalace search``
    prints verbatim drawer text that may carry surrogate halves
    round-tripped from filenames — ``strict`` would crash mid-print and
    lose the rest of the search result block. stdin keeps the default
    ``surrogateescape`` so a redirected non-UTF-8 file does not kill the
    read on the first bad byte.
    """
    from .._stdio import reconfigure_stdio_utf8_on_windows as _reconfigure

    _reconfigure(stdout_errors="replace", stderr_errors="replace")


# ── Import subcommand modules (after all shared defs to avoid circular) ────

from ._init import cmd_init  # noqa: E402
from ._mine import cmd_mine, cmd_sweep, cmd_sync, cmd_daemon  # noqa: E402
from ._search import cmd_search  # noqa: E402
from ._status import (  # noqa: E402
    cmd_status,
    cmd_check_qdrant,
    cmd_repair_status,
    cmd_palace_set_embedder,
)
from ._repair import cmd_repair  # noqa: E402
from ._misc import (  # noqa: E402
    cmd_split,
    cmd_wakeup,
    cmd_compress,
    cmd_mcp,
    cmd_hook,
    cmd_instructions,
)


# ── Main entry point ──────────────────────────────────────────────────────


def main():
    """CLI entry point for the ``mempalace`` console script.

    Side effect: pops ``PYTHONPATH`` from ``os.environ`` (see #1423) so
    any subprocess this CLI spawns inherits a clean env. Host applications
    that call ``main()`` programmatically should be aware that the parent
    process loses ``PYTHONPATH`` as well. Library imports
    (``import mempalace.searcher`` from a host app) do NOT trigger this
    side effect; only the CLI/MCP entry points pop the env var.
    """
    # Drop leaked PYTHONPATH so any subprocess the CLI spawns (mine workers,
    # repair tooling) starts with a clean env. The sys.path filter in
    # mempalace/__init__.py already protects this process from the same
    # ABI mismatch; here we extend the protection to children.
    os.environ.pop("PYTHONPATH", None)

    _reconfigure_stdio_utf8_on_windows()

    version_label = f"MemPalace {__version__}"
    parser = argparse.ArgumentParser(
        description="MemPalace — Give your AI a memory. No API key required.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"{version_label}\n\n{__doc__}",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=version_label,
        help="Show version and exit",
    )
    parser.add_argument(
        "--palace",
        default=None,
        help="Where the palace lives (default: from ~/.mempalace/config.json or ~/.mempalace/palace)",
    )
    parser.add_argument(
        "--backend",
        dest="global_backend",
        default=None,
        help="Storage backend to use for this command (default: config/env/detected/qdrant)",
    )

    sub = parser.add_subparsers(dest="command")

    # init
    p_init = sub.add_parser("init", help="Detect rooms from your folder structure")
    p_init.add_argument("dir", help="Project directory to set up")
    p_init.add_argument(
        "--backend",
        default=None,
        help="Storage backend to persist for this palace (default: qdrant)",
    )
    p_init.add_argument(
        "--yes",
        action="store_true",
        help="Auto-accept all detected entities (non-interactive)",
    )
    p_init.add_argument(
        "--auto-mine",
        action="store_true",
        help=(
            "Skip the post-init mine prompt and run mine automatically. "
            "Combine with --yes for a fully non-interactive setup."
        ),
    )
    p_init.add_argument(
        "--lang",
        default=None,
        help=(
            "Comma-separated language codes for entity detection "
            "(e.g. 'en' or 'en,pt-br'). Defaults to value from config "
            "(MEMPALACE_ENTITY_LANGUAGES env var or config.json), or 'en'. "
            "When given, the value is also persisted to config.json."
        ),
    )
    p_init.add_argument(
        "--llm",
        action="store_true",
        help=(
            "DEPRECATED — LLM-assisted entity refinement is now ON by default. "
            "This flag is preserved for backward compatibility; pass --no-llm "
            "to opt out instead."
        ),
    )
    p_init.add_argument(
        "--no-llm",
        action="store_true",
        help=(
            "Disable LLM-assisted entity refinement. Run init in heuristics-only "
            "mode (no provider acquisition, no LLM calls). Use when running "
            "without a local LLM and you don't want the graceful-fallback message."
        ),
    )
    p_init.add_argument(
        "--llm-provider",
        default="ollama",
        choices=["ollama", "openai-compat", "anthropic"],
        help="LLM provider (default: ollama). Pass --no-llm to disable LLM-assisted refinement entirely.",
    )
    p_init.add_argument(
        "--llm-model",
        default="gemma4:e4b",
        help="Model name for the chosen provider (default: gemma4:e4b for Ollama).",
    )
    p_init.add_argument(
        "--llm-endpoint",
        default=None,
        help=(
            "Provider endpoint URL. Default for Ollama: http://localhost:11434. "
            "Required for openai-compat."
        ),
    )
    p_init.add_argument(
        "--llm-api-key",
        default=None,
        help=(
            "API key for the provider. For anthropic, defaults to $ANTHROPIC_API_KEY; "
            "for openai-compat, defaults to $OPENAI_API_KEY."
        ),
    )
    p_init.add_argument(
        "--accept-external-llm",
        action="store_true",
        help=(
            "Bypass the interactive consent prompt that fires when an external "
            "LLM is configured via an environment-variable API key (issue #26). "
            "Use this in CI / non-interactive runs where you've already decided "
            "the external send is acceptable."
        ),
    )

    # mine
    p_mine = sub.add_parser("mine", help="Mine files into the palace")
    p_mine.add_argument("dir", help="Directory to mine")
    p_mine.add_argument(
        "--backend",
        default=None,
        help="Storage backend to use for this mine (default: config/env/detected/qdrant)",
    )
    p_mine.add_argument(
        "--mode",
        choices=["projects", "convos", "extract"],
        default="projects",
        help=(
            "Ingest mode: 'projects' for code/docs (default), 'convos' for chat "
            "exports, 'extract' for office documents (PDF/DOCX/RTF/etc., requires "
            "mempalace[extract])"
        ),
    )
    p_mine.add_argument("--wing", default=None, help="Wing name (default: directory name)")
    p_mine.add_argument(
        "--no-gitignore",
        action="store_true",
        help="Don't respect .gitignore files when scanning project files",
    )
    p_mine.add_argument(
        "--include-ignored",
        action="append",
        default=[],
        help="Always scan these project-relative paths even if ignored; repeat or pass comma-separated paths",
    )
    p_mine.add_argument(
        "--agent",
        default="mempalace",
        help="Your name — recorded on every drawer (default: mempalace)",
    )
    p_mine.add_argument("--limit", type=int, default=0, help="Max files to process (0 = all)")
    p_mine.add_argument(
        "--redetect-origin",
        action="store_true",
        help=(
            "Re-run corpus_origin detection on this directory and overwrite "
            "<palace>/.mempalace/origin.json. Useful when the corpus has grown "
            "since `mempalace init` and the stored origin may be stale. "
            "Heuristic-only (no LLM call) — re-run `mempalace init --llm` for "
            "Tier 2 refinement."
        ),
    )
    p_mine.add_argument(
        "--dry-run", action="store_true", help="Show what would be filed without filing"
    )
    p_mine.add_argument(
        "--daemon",
        action="store_true",
        help="Submit this mine to the opt-in local daemon queue",
    )
    p_mine.add_argument(
        "--background",
        action="store_true",
        help="With --daemon, return a job id immediately instead of waiting",
    )
    p_mine.add_argument(
        "--extract",
        choices=["exchange", "general"],
        default="exchange",
        help="Extraction strategy for convos mode: 'exchange' (default) or 'general' (5 memory types)",
    )
    p_mine.add_argument(
        "--max-chunks-per-file",
        type=int,
        default=None,
        metavar="N",
        help=(
            f"Per-file chunk cap; files producing more chunks are skipped with a "
            f"summary counter. Default {_CLI_MAX_CHUNKS_PER_FILE_DEFAULT} "
            f"(or MEMPALACE_MAX_CHUNKS_PER_FILE). Set 0 to disable. Lower this on "
            f"Windows if you hit ONNX bad_alloc (#1455)."
        ),
    )

    # sweep
    p_sweep = sub.add_parser(
        "sweep",
        help="Tandem miner: catch anything the primary miner missed "
        "(message-level, timestamp-coordinated, idempotent)",
    )
    p_sweep.add_argument(
        "target",
        help="A .jsonl transcript file, or a directory to scan recursively",
    )

    # sync
    p_sync = sub.add_parser(
        "sync",
        help="Prune drawers whose source files are gitignored, deleted, or moved (#1252)",
    )
    p_sync.add_argument(
        "dir",
        nargs="?",
        default=None,
        help="Project root to sync (optional; auto-detects from drawer metadata)",
    )
    p_sync.add_argument("--wing", default=None, help="Limit to one wing")
    p_sync.add_argument(
        "--root",
        action="append",
        default=[],
        help="Additional project root (repeatable)",
    )
    p_sync.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=True,
        help="Preview only (default)",
    )
    p_sync.add_argument(
        "--apply",
        dest="dry_run",
        action="store_false",
        help="Actually delete drawers (overrides --dry-run; requires --wing or a project root)",
    )
    p_sync.add_argument(
        "--daemon",
        action="store_true",
        help="Submit this sync to the opt-in local daemon queue",
    )
    p_sync.add_argument(
        "--background",
        action="store_true",
        help="With --daemon, return a job id immediately instead of waiting",
    )

    # search
    p_search = sub.add_parser("search", help="Find anything, exact words")
    p_search.add_argument("query", help="What to search for")
    p_search.add_argument(
        "--backend",
        default=None,
        help="Storage backend to use for this search (default: config/env/detected/qdrant)",
    )
    p_search.add_argument("--wing", default=None, help="Limit to one project")
    p_search.add_argument("--room", default=None, help="Limit to one room")
    p_search.add_argument("--results", type=int, default=5, help="Number of results")

    # compress
    p_compress = sub.add_parser(
        "compress", help="Compress drawers using AAAK Dialect (~30x reduction)"
    )
    p_compress.add_argument("--wing", default=None, help="Wing to compress (default: all wings)")
    p_compress.add_argument(
        "--dry-run", action="store_true", help="Preview compression without storing"
    )
    p_compress.add_argument(
        "--config", default=None, help="Entity config JSON (e.g. entities.json)"
    )

    # wake-up
    p_wakeup = sub.add_parser("wake-up", help="Show L0 + L1 wake-up context (~600-900 tokens)")
    p_wakeup.add_argument("--wing", default=None, help="Wake-up for a specific project/wing")

    # split
    p_split = sub.add_parser(
        "split",
        help="Split concatenated transcript mega-files into per-session files (run before mine)",
    )
    p_split.add_argument("dir", help="Directory containing transcript files")
    p_split.add_argument(
        "--output-dir",
        default=None,
        help="Write split files here (default: same directory as source files)",
    )
    p_split.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be split without writing files",
    )
    p_split.add_argument(
        "--min-sessions",
        type=int,
        default=2,
        help="Only split files containing at least N sessions (default: 2)",
    )

    # hook
    p_hook = sub.add_parser(
        "hook",
        help="Run hook logic (reads JSON from stdin, outputs JSON to stdout)",
    )
    hook_sub = p_hook.add_subparsers(dest="hook_action")
    p_hook_run = hook_sub.add_parser("run", help="Execute a hook")
    p_hook_run.add_argument(
        "--hook",
        required=True,
        choices=["session-start", "stop", "session-end", "precompact"],
        help="Hook name to run",
    )
    p_hook_run.add_argument(
        "--harness",
        required=True,
        choices=["claude-code", "codex"],
        help="Harness type (determines stdin JSON format)",
    )

    # instructions
    p_instructions = sub.add_parser(
        "instructions",
        help="Output skill instructions to stdout",
    )
    instructions_sub = p_instructions.add_subparsers(dest="instructions_name")
    for instr_name in ["init", "search", "mine", "help", "status"]:
        instructions_sub.add_parser(instr_name, help=f"Output {instr_name} instructions")

    # repair
    p_repair = sub.add_parser(
        "repair",
        help=(
            "Rebuild palace vector index (legacy mode) or un-poison max_seq_id rows "
            "(--mode max-seq-id)"
        ),
    )
    p_repair.add_argument(
        "--yes", action="store_true", help="Skip confirmation for destructive changes"
    )
    p_repair.add_argument(
        "repair_action",
        nargs="?",
        choices=["rebuild-index"],
        help=(
            "Re-embed the palace from SQLite using the current embedding model "
            "(alias for --mode from-sqlite --archive-existing)."
        ),
    )
    p_repair.add_argument(
        "--backup",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Back up Qdrant collection before repair (default: on)",
    )

    # repair-status — read-only Qdrant health check
    sub.add_parser(
        "repair-status",
        help="Read-only Qdrant collection health check",
    )

    # check-qdrant — quick Qdrant connectivity check
    sub.add_parser("check-qdrant", help="Quick Qdrant connectivity check")

    # daemon
    p_daemon = sub.add_parser("daemon", help="Manage the opt-in long-lived daemon")
    daemon_sub = p_daemon.add_subparsers(dest="daemon_action")
    p_daemon_start = daemon_sub.add_parser("start", help="Start the daemon")
    p_daemon_start.add_argument(
        "--foreground",
        action="store_true",
        help="Run in the foreground for debugging or process supervisors",
    )
    p_daemon_start.add_argument(
        "--backend",
        default=None,
        help="Storage backend for this daemon (default: config/env/detected/qdrant)",
    )
    daemon_sub.add_parser("stop", help="Stop the daemon")
    daemon_sub.add_parser("status", help="Show daemon status")
    p_daemon_jobs = daemon_sub.add_parser("jobs", help="List recent daemon jobs")
    p_daemon_jobs.add_argument("--limit", type=int, default=20, help="Max jobs to show")
    p_daemon_wait = daemon_sub.add_parser("wait", help="Wait for a daemon job")
    p_daemon_wait.add_argument("job_id", help="Job id returned by --background")

    # mcp
    p_mcp = sub.add_parser(
        "mcp",
        help="Show MCP setup command for connecting MemPalace to your AI client",
    )
    p_mcp.add_argument(
        "--backend",
        default=None,
        help="Storage backend to include in the MCP startup command",
    )

    # status
    p_status = sub.add_parser("status", help="Show what's been filed")
    p_status.add_argument(
        "--backend",
        default=None,
        help="Storage backend to use for status (default: config/env/detected/qdrant)",
    )

    # palace
    p_palace = sub.add_parser("palace", help="Palace maintenance commands")
    palace_sub = p_palace.add_subparsers(dest="palace_action")
    p_set_embedder = palace_sub.add_parser(
        "set-embedder",
        help="Record/override the palace's embedder identity (resolve 'unknown', or switch models)",
    )
    p_set_embedder.add_argument(
        "--model",
        default=None,
        help="Embedder model to record (default: current configured model). "
        "Records identity on the palace only; does not change the configured "
        "model (prints how to align MEMPALACE_EMBEDDING_MODEL if they differ).",
    )
    p_set_embedder.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing identity that names a different model "
        "(only if you know the stored vectors are compatible)",
    )
    p_set_embedder.add_argument(
        "--backend",
        default=None,
        help="Storage backend (default: config/env/detected/qdrant)",
    )

    args = parser.parse_args()
    _apply_backend_arg(args)

    if not args.command:
        parser.print_help()
        return

    # Handle two-level subcommands
    if args.command == "hook":
        if not getattr(args, "hook_action", None):
            p_hook.print_help()
            return
        cmd_hook(args)
        return

    if args.command == "instructions":
        name = getattr(args, "instructions_name", None)
        if not name:
            p_instructions.print_help()
            return
        args.name = name
        cmd_instructions(args)
        return

    if args.command == "palace":
        if getattr(args, "palace_action", None) == "set-embedder":
            cmd_palace_set_embedder(args)
        else:
            p_palace.print_help()
        return

    if args.command == "daemon":
        if not getattr(args, "daemon_action", None):
            p_daemon.print_help()
            return
        cmd_daemon(args)
        return

    dispatch = {
        "init": cmd_init,
        "mine": cmd_mine,
        "split": cmd_split,
        "search": cmd_search,
        "sweep": cmd_sweep,
        "sync": cmd_sync,
        "mcp": cmd_mcp,
        "compress": cmd_compress,
        "wake-up": cmd_wakeup,
        "repair": cmd_repair,
        "repair-status": cmd_repair_status,
        "check-qdrant": cmd_check_qdrant,
        "status": cmd_status,
    }
    dispatch[args.command](args)
