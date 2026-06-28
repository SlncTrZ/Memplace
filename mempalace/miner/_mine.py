"""Mine — main mining orchestration logic.

Wing: miner | Topic: mine | Updated: 2026-06-28 18:30
"""

import os
import shlex
from collections import defaultdict
from pathlib import Path
from typing import Optional

from ..palace import (
    MineValidationError,
    _validate_palace_fts5_after_mine,
    get_closets_collection,
    get_collection,
    mine_palace_lock,
)
from ._config import load_config
from ._entities import get_topics_by_wing
from ._gitignore import normalize_include_paths
from ._processing import process_file
from ._readable import _resolve_max_chunks_per_file


def mine(
    project_dir: str,
    palace_path: str,
    wing_override: Optional[str] = None,
    agent: str = "mempalace",
    limit: int = 0,
    dry_run: bool = False,
    respect_gitignore: bool = True,
    include_ignored: Optional[list] = None,
    files: Optional[list] = None,
    max_chunks_per_file: Optional[int] = None,
):
    """Mine a project directory into the palace.

    ``files`` may optionally be a pre-scanned list of file paths from
    :func:`scan_project`. When provided, the corpus walk is skipped — the
    caller (e.g. ``init`` showing a file-count estimate before the mine
    prompt) avoids walking the tree twice. When ``None`` (the default),
    ``mine`` walks the tree itself just like before.

    ``max_chunks_per_file`` overrides the per-file chunk cap (see
    :func:`_resolve_max_chunks_per_file`). ``None`` defers to
    ``MEMPALACE_MAX_CHUNKS_PER_FILE`` or ``MAX_CHUNKS_PER_FILE``; ``0``
    disables the cap entirely (#1455).
    """
    if dry_run:
        return _mine_impl(
            project_dir,
            palace_path,
            wing_override=wing_override,
            agent=agent,
            limit=limit,
            dry_run=dry_run,
            respect_gitignore=respect_gitignore,
            include_ignored=include_ignored,
            files=files,
            max_chunks_per_file=max_chunks_per_file,
        )

    # MineAlreadyRunning propagates so the CLI can render a clear holder-aware
    # message and exit non-zero. In-process callers (tests, library users) that
    # expect to coexist with another writer should handle the exception.
    with mine_palace_lock(palace_path):
        return _mine_impl(
            project_dir,
            palace_path,
            wing_override=wing_override,
            agent=agent,
            limit=limit,
            dry_run=dry_run,
            respect_gitignore=respect_gitignore,
            include_ignored=include_ignored,
            files=files,
            max_chunks_per_file=max_chunks_per_file,
        )


def _mine_impl(
    project_dir: str,
    palace_path: str,
    wing_override: Optional[str] = None,
    agent: str = "mempalace",
    limit: int = 0,
    dry_run: bool = False,
    respect_gitignore: bool = True,
    include_ignored: Optional[list] = None,
    files: Optional[list] = None,
    max_chunks_per_file: Optional[int] = None,
):
    from ..config import MempalaceConfig

    project_path = Path(project_dir).expanduser().resolve()
    config = load_config(project_dir)
    palace_config = MempalaceConfig()

    cfg_chunk_size = palace_config.chunk_size
    cfg_chunk_overlap = palace_config.chunk_overlap
    cfg_min_chunk_size = palace_config.min_chunk_size

    wing = wing_override or config["wing"]
    rooms = config.get("rooms", [{"name": "general", "description": "All project files"}])

    if files is None:
        from ._processing import scan_project

        files = scan_project(
            project_dir,
            respect_gitignore=respect_gitignore,
            include_ignored=include_ignored,
        )
    assert files is not None
    from ..embedding import describe_device

    print(f"\n{'=' * 55}")
    print("  MemPalace Mine")
    print(f"{'=' * 55}")
    print(f"  Wing:    {wing}")
    print(f"  Rooms:   {', '.join(r['name'] for r in rooms)}")
    limit_suffix = f" (limit: {limit} new)" if limit > 0 else ""
    print(f"  Files:   {len(files)}{limit_suffix}")
    print(f"  Palace:  {palace_path}")
    print(f"  Device:  {describe_device()}")
    if dry_run:
        print("  DRY RUN — nothing will be filed")
    if not respect_gitignore:
        print("  .gitignore: DISABLED")
    if include_ignored:
        print(f"  Include: {', '.join(sorted(normalize_include_paths(include_ignored)))}")
    print(f"{'-' * 55}\n")

    if not dry_run:
        collection = get_collection(palace_path)
        closets_col = get_closets_collection(palace_path)
    else:
        collection = None
        closets_col = None

    total_drawers = 0
    files_mined = 0
    files_skipped = 0
    files_skipped_chunk_cap = 0
    files_processed = 0
    last_file = None
    room_counts = defaultdict(int)
    effective_chunk_cap = _resolve_max_chunks_per_file(max_chunks_per_file)

    try:
        for i, filepath in enumerate(files, 1):
            try:
                drawers, room, skip_reason = process_file(
                    filepath=filepath,
                    project_path=project_path,
                    collection=collection,
                    wing=wing,
                    rooms=rooms,
                    agent=agent,
                    dry_run=dry_run,
                    closets_col=closets_col,
                    chunk_size=cfg_chunk_size,
                    chunk_overlap=cfg_chunk_overlap,
                    min_chunk_size=cfg_min_chunk_size,
                    # Pass the already-resolved int so ``process_file``'s
                    # ``override is not None`` branch skips the env re-read;
                    # otherwise a malformed env var would emit its warning
                    # per file.
                    max_chunks_per_file=effective_chunk_cap,
                )
            except KeyboardInterrupt:
                # Re-raise so the outer handler prints the summary; we
                # capture the last-attempted file via last_file below.
                last_file = filepath.name
                raise
            files_processed = i
            last_file = filepath.name
            # All zero-drawer outcomes increment ``files_skipped`` in both
            # modes so the summary "Files processed" arithmetic and the
            # residual-skip counter stay honest under ``--dry-run`` too. The
            # chunk-cap counter is partitioned out for its dedicated
            # summary line (see #1455 + Gemini review on PR #1554).
            if drawers == 0:
                files_skipped += 1
                if skip_reason == "chunk_cap":
                    files_skipped_chunk_cap += 1
            else:
                total_drawers += drawers
                room_counts[room] += 1
                files_mined += 1
                if not dry_run:
                    print(f"  + [{i:4}/{len(files)}] {filepath.name[:50]:50} +{drawers}")
                if limit > 0 and files_mined >= limit:
                    break

        if not dry_run:
            # Cross-wing topic tunnels
            try:
                tunnels_added = _compute_topic_tunnels_for_wing(wing)
                if tunnels_added:
                    print(f"\n  Topic tunnels: +{tunnels_added} cross-wing link(s)")
            except Exception as e:
                print(
                    f"\n  WARNING: topic tunnel computation skipped — {e}",
                    file=__import__("sys").stderr,
                )

            # Within-wing hallways
            try:
                from ..hallways import compute_hallways_for_wing

                hallways_created = compute_hallways_for_wing(wing, col=collection)
                if hallways_created:
                    print(f"\n  Hallways: +{len(hallways_created)} within-wing entity link(s)")
            except Exception as e:
                print(
                    f"\n  WARNING: hallway computation skipped — {e}",
                    file=__import__("sys").stderr,
                )

            # Cross-wing entity tunnels
            try:
                entity_tunnels_added = _compute_entity_tunnels_for_wing(wing)
                if entity_tunnels_added:
                    print(f"\n  Entity tunnels: +{entity_tunnels_added} cross-wing entity link(s)")
            except Exception as e:
                print(
                    f"\n  WARNING: entity tunnel computation skipped — {e}",
                    file=__import__("sys").stderr,
                )

            _validate_palace_fts5_after_mine(palace_path)

        print(f"\n{'=' * 55}")
        print("  Done.")
        print(f"  Files processed: {files_processed - files_skipped}")
        residual_label = (
            "Files skipped (read error or too short)"
            if dry_run
            else "Files skipped (already filed or other)"
        )
        print(f"  {residual_label}: {max(0, files_skipped - files_skipped_chunk_cap)}")
        if files_skipped_chunk_cap > 0:
            print(
                f"  Files skipped (chunk cap {effective_chunk_cap}): {files_skipped_chunk_cap} "
                f"(raise via --max-chunks-per-file or MEMPALACE_MAX_CHUNKS_PER_FILE; "
                f"set 0 to disable)"
            )
        print(f"  Drawers filed: {total_drawers}")
        print("\n  By room:")
        for room, count in sorted(room_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"    {room:20} {count} files")
        print('\n  Next: mempalace search "what you\'re looking for"')
        print(f"{'=' * 55}\n")
    except KeyboardInterrupt:
        print("\n\n  Mine interrupted.")
        print(f"    files_processed: {files_processed}/{len(files)}")
        print(f"    drawers_filed:   {total_drawers}")
        print(f"    last_file:       {last_file or '<none>'}")
        print(
            f"\n  Re-run `mempalace mine {shlex.quote(project_dir)}` to resume — "
            "already-filed drawers are\n  upserted idempotently and will not duplicate.\n"
        )
        __import__("sys").exit(130)
    except MineValidationError:
        raise
    except Exception as exc:

        print("\n\n  Mine aborted by exception.")
        print(f"    files_processed: {files_processed}/{len(files)}")
        print(f"    drawers_filed:   {total_drawers}")
        print(f"    last_file:       {last_file or '<none>'}")
        print(f"    error:           {type(exc).__name__}: {exc}")
        print(
            f"\n  Re-run `mempalace mine {shlex.quote(project_dir)}` after addressing "
            "the cause — already-filed\n  drawers are upserted idempotently and will "
            "not duplicate.\n"
        )
        raise
    finally:
        _cleanup_mine_pid_file()


def _cleanup_mine_pid_file() -> None:
    """Remove this process's per-target PID slot on exit."""
    pid_file_env = os.environ.get("MEMPALACE_MINE_PID_FILE", "")
    if not pid_file_env:
        return
    try:
        pid_file = Path(pid_file_env)
        if not pid_file.exists():
            return
        recorded = pid_file.read_text().strip()
        pid_token = recorded.split()[0] if recorded else ""
        if pid_token and pid_token.isdigit() and int(pid_token) == os.getpid():
            pid_file.unlink()
    except OSError:
        pass


def _compute_topic_tunnels_for_wing(wing: str) -> int:
    """Drop tunnels between ``wing`` and every other wing that shares
    confirmed topics, honoring the ``topic_tunnel_min_count`` config knob.

    Returns the number of tunnels created or refreshed. Zero means no
    overlap found (or the registry has no ``topics_by_wing`` map yet).
    """
    from ..config import MempalaceConfig
    from ..palace_graph import topic_tunnels_for_wing

    topics_map = get_topics_by_wing()
    if not topics_map or wing not in topics_map:
        return 0
    cfg = MempalaceConfig()
    min_count = cfg.topic_tunnel_min_count
    created = topic_tunnels_for_wing(wing, topics_map, min_count=min_count)
    return len(created)


def _compute_entity_tunnels_for_wing(wing: str) -> int:
    """Drop tunnels between ``wing`` and every other wing that shares an
    entity via the within-wing hallway primitive.

    Reads hallway records (``mempalace.hallways.list_hallways``) and
    materializes cross-wing tunnels for any entity that has hallways in
    this wing AND at least one other wing. Tunnels use ``kind="entity"``
    and the synthetic endpoint room ``entity:<name>`` so they're
    distinguishable from explicit and topic tunnels at read time but
    interchangeable with them via the standard ``list_tunnels`` /
    ``follow_tunnels`` API.

    Returns the number of tunnels created or refreshed. Zero means no
    eligible entity exists in this wing yet (or no hallway records do).
    """
    from ..hallways import list_hallways
    from ..palace_graph import entity_tunnels_for_wing

    hallways = list_hallways()
    if not hallways:
        return 0
    created = entity_tunnels_for_wing(wing, hallways)
    return len(created)
