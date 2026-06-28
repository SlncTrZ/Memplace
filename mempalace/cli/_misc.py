"""_misc — Miscellaneous subcommands: split, wake-up, compress, mcp, hook, instructions.

Wing: mempalace | Topic: cli | Updated: 2026-06-28
"""

import os
import sys
import shlex
from pathlib import Path

from ..config import MempalaceConfig


def _backend_arg(args):
    """Return a CLI-selected backend from subcommand or global flags."""
    return getattr(args, "backend", None) or getattr(args, "global_backend", None)


def cmd_split(args):
    """Split concatenated transcript mega-files into per-session files."""
    from ..split_mega_files import main as split_main

    argv = ["--source", str(Path(args.dir).expanduser().resolve())]
    if args.output_dir:
        argv += ["--output-dir", args.output_dir]
    if args.dry_run:
        argv.append("--dry-run")
    if args.min_sessions != 2:
        argv += ["--min-sessions", str(args.min_sessions)]

    old_argv = sys.argv
    sys.argv = ["mempalace split"] + argv
    try:
        split_main()
    finally:
        sys.argv = old_argv


def cmd_wakeup(args):
    """Show L0 (identity) + L1 (essential story) — the wake-up context."""
    from ..layers import MemoryStack

    palace_path = os.path.expanduser(args.palace) if args.palace else MempalaceConfig().palace_path
    stack = MemoryStack(palace_path=palace_path)

    text = stack.wake_up(wing=args.wing)
    tokens = len(text) // 4
    print(f"Wake-up text (~{tokens} tokens):")
    print("=" * 50)
    print(text)


def cmd_compress(args):
    """Compress drawers in a wing using AAAK Dialect."""
    from ..dialect import Dialect
    from ..palace import get_closets_collection

    palace_path = os.path.expanduser(args.palace) if args.palace else MempalaceConfig().palace_path

    config_path = args.config
    if not config_path:
        for candidate in ["entities.json", os.path.join(palace_path, "entities.json")]:
            if os.path.exists(candidate):
                config_path = candidate
                break

    if config_path and os.path.exists(config_path):
        dialect = Dialect.from_config(config_path)
        print(f"  Loaded entity config: {config_path}")
    else:
        dialect = Dialect()

    from ..palace import _open_collection_or_explain

    col = _open_collection_or_explain(palace_path, collection_name="mempalace_drawers")
    if col is None:
        sys.exit(1)

    where = {"wing": args.wing} if args.wing else None
    _BATCH = 500
    docs, metas, ids = [], [], []
    offset = 0
    while True:
        try:
            kwargs = {
                "include": ["documents", "metadatas"],
                "limit": _BATCH,
                "offset": offset,
            }
            if where:
                kwargs["where"] = where
            batch = col.get(**kwargs)
        except Exception as e:
            if not docs:
                print(f"\n  Error reading drawers: {e}")
                sys.exit(1)
            break
        batch_docs = batch.get("documents", [])
        if not batch_docs:
            break
        docs.extend(batch_docs)
        metas.extend(batch.get("metadatas", []) or [])
        ids.extend(batch.get("ids", []) or [])
        offset += len(batch_docs)
        if len(batch_docs) < _BATCH:
            break

    if not docs:
        wing_label = f" in wing '{args.wing}'" if args.wing else ""
        print(f"\n  No drawers found{wing_label}.")
        return

    print(
        f"\n  Compressing {len(docs)} drawers"
        + (f" in wing '{args.wing}'" if args.wing else "")
        + "..."
    )
    print()

    total_original = 0
    total_compressed = 0
    compressed_entries = []

    for doc, meta, doc_id in zip(docs, metas, ids):
        compressed = dialect.compress(doc, metadata=meta)
        stats = dialect.compression_stats(doc, compressed)

        total_original += stats["original_chars"]
        total_compressed += stats["summary_chars"]

        compressed_entries.append((doc_id, compressed, meta, stats))

        if args.dry_run:
            wing_name = meta.get("wing", "?")
            room_name = meta.get("room", "?")
            source = Path(meta.get("source_file", "?")).name
            print(f"  [{wing_name}/{room_name}] {source}")
            print(
                f"    {stats['original_tokens_est']}t -> {stats['summary_tokens_est']}t ({stats['size_ratio']:.1f}x)"
            )
            print(f"    {compressed}")
            print()

    if not args.dry_run:
        try:
            comp_col = get_closets_collection(palace_path, create=True)
            for doc_id, compressed, meta, stats in compressed_entries:
                comp_meta = dict(meta)
                comp_meta["compression_ratio"] = round(stats["size_ratio"], 1)
                comp_meta["original_tokens"] = stats["original_tokens_est"]
                comp_col.upsert(
                    ids=[doc_id],
                    documents=[compressed],
                    metadatas=[comp_meta],
                )
            print(
                f"  Stored {len(compressed_entries)} compressed drawers in 'mempalace_closets' collection."
            )
        except Exception as e:
            print(f"  Error storing compressed drawers: {e}")
            sys.exit(1)

    ratio = total_original / max(total_compressed, 1)
    orig_tokens = max(1, int(total_original / 3.8))
    comp_tokens = max(1, int(total_compressed / 3.8))
    print(f"  Total: {orig_tokens:,}t -> {comp_tokens:,}t ({ratio:.1f}x compression)")
    if args.dry_run:
        print("  (dry run -- nothing stored)")


def cmd_mcp(args):
    """Show how to wire MemPalace into MCP-capable hosts."""
    base_server_cmd = "mempalace-mcp"
    cmd_parts = [base_server_cmd]

    if args.palace:
        resolved_palace = str(Path(args.palace).expanduser())
        cmd_parts.extend(["--palace", shlex.quote(resolved_palace)])
    backend = _backend_arg(args)
    if backend:
        cmd_parts.extend(["--backend", shlex.quote(str(backend).strip().lower())])
    server_cmd = " ".join(cmd_parts)

    print("MemPalace MCP quick setup:")
    print(f"  claude mcp add mempalace -- {server_cmd}")
    print(f"  codex mcp add mempalace -- {server_cmd}")
    print("\nRun the server directly:")
    print(f"  {server_cmd}")

    if not args.palace:
        print("\nOptional custom palace:")
        print(f"  claude mcp add mempalace -- {base_server_cmd} --palace /path/to/palace")
        print(f"  codex mcp add mempalace -- {base_server_cmd} --palace /path/to/palace")
        print(f"  {base_server_cmd} --palace /path/to/palace")


def cmd_hook(args):
    """Run hook logic: reads JSON from stdin, outputs JSON to stdout."""
    from ..hooks_cli import run_hook

    run_hook(hook_name=args.hook, harness=args.harness)


def cmd_instructions(args):
    """Output skill instructions to stdout."""
    from ..instructions_cli import run_instructions

    run_instructions(name=args.name)
