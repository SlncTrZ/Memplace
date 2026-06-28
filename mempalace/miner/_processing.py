"""Processing — per-file processing and project scanning for the miner.

Wing: miner | Topic: processing | Updated: 2026-06-28 18:30
"""

import hashlib
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..collision_scan import assert_no_collisions
from ..ids import make_drawer_id_from_chunk
from ..palace import (
    NORMALIZE_VERSION,
    MineValidationError,
    _open_collection_or_explain,
    _validate_palace_fts5_after_mine,
    build_closet_lines,
    file_already_mined,
    get_closets_collection,
    get_collection,
    mine_lock,
    mine_palace_lock,
    purge_file_closets,
    upsert_closet_lines,
)
from ._chunking import MIN_CHUNK_SIZE, chunk_text
from ._dates import _extract_content_date
from ._drawers import _build_drawer_metadata
from ._gitignore import (
    is_exact_force_include,
    is_force_included,
    is_gitignored,
    load_gitignore_matcher,
    normalize_include_paths,
    should_skip_dir,
)
from ._readable import (
    DRAWER_UPSERT_BATCH_SIZE,
    MAX_FILE_SIZE,
    SKIP_FILENAMES,
    _path_within_root,
    _read_text_no_follow,
    _resolve_max_chunks_per_file,
    READABLE_EXTENSIONS,
)
from ._rooms import detect_room

import logging

logger = logging.getLogger("mempalace_mcp")


def process_file(
    filepath: Path,
    project_path: Path,
    collection,
    wing: str,
    rooms: list,
    agent: str,
    dry_run: bool,
    closets_col=None,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
    min_chunk_size: Optional[int] = None,
    max_chunks_per_file: Optional[int] = None,
) -> tuple:
    """Read, chunk, route, and file one file.

    Returns ``(drawer_count, room_name, skip_reason)``. ``skip_reason`` is
    ``None`` on success and on every non-chunk-cap skip path: already
    filed (pre- or post-lock re-check), unreadable (``OSError``), or
    too-short content (below ``min_chunk_size``). It is ``"chunk_cap"``
    when the per-file chunk cap aborted the file. Callers use the tag to
    surface a separate counter in the mine summary (see #1455).
    """
    effective_min = min_chunk_size if min_chunk_size is not None else MIN_CHUNK_SIZE

    # Skip if already filed
    source_file = str(filepath)
    if not dry_run and file_already_mined(collection, source_file, check_mtime=True):
        return 0, "general", None

    content = _read_text_no_follow(filepath, project_path)
    if content is None:
        return 0, "general", None

    content = content.strip()
    if len(content) < effective_min:
        return 0, "general", None

    room = detect_room(filepath, content, rooms, project_path)
    chunks = chunk_text(
        content,
        source_file,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        min_chunk_size=min_chunk_size,
    )

    effective_cap = _resolve_max_chunks_per_file(max_chunks_per_file)
    if effective_cap > 0 and len(chunks) > effective_cap:
        # Skip notice goes to stderr alongside the existing symlink-skip
        # warning style (see ``scan_project``'s ``SKIP: <rel> (symlink)``
        # line). This keeps ``mempalace mine ... > out.log 2> err.log``
        # piping coherent: degraded outcomes on stderr, progress on stdout.
        print(
            f"  ! [skip] {filepath.name[:50]:50} produced {len(chunks)} chunks "
            f"(> {effective_cap}); raise via --max-chunks-per-file or "
            f"MEMPALACE_MAX_CHUNKS_PER_FILE (set 0 to disable), or add to "
            f"SKIP_FILENAMES if this is a generated artifact",
            file=sys.stderr,
        )
        return 0, room, "chunk_cap"

    if dry_run:
        print(f"    [DRY RUN] {filepath.name} -> room:{room} ({len(chunks)} drawers)")
        return len(chunks), room, None

    # Lock this file so concurrent agents don't interleave delete+insert.
    # Without the lock, two agents can both pass file_already_mined(),
    # both delete, and both insert — creating duplicates or losing data.
    with mine_lock(source_file):
        # Re-check after acquiring lock — another agent may have just finished
        if file_already_mined(collection, source_file, check_mtime=True):
            return 0, room, None

        # Purge stale drawers for this file before re-inserting the fresh chunks.
        # Converts modified-file re-mines from upsert-over-existing-IDs (which hits
        # hnswlib's thread-unsafe updatePoint path and can segfault on macOS ARM
        # with the legacy backend) into a clean delete+insert, bypassing the update
        # path entirely.
        try:
            collection.delete(where={"source_file": source_file})
        except Exception:
            logger.debug("Stale-drawer purge failed for %s", source_file, exc_info=True)

        # Batch chunks into bounded upserts so the embedding model sees many
        # chunks per forward pass without building one huge request
        # for pathological files. A bad chunk can fail its sub-batch;
        # that is the deliberate trade-off for amortizing embedding overhead.
        try:
            source_mtime = os.path.getmtime(source_file)
        except OSError:
            source_mtime = None

        # Tier 6a content-date: extract once per file (not per chunk) and
        # share across all chunks. Reads filename / frontmatter / content /
        # mtime hierarchy. Returns None when nothing usable found -> caller
        # falls back to filed_at downstream.
        file_content_date = _extract_content_date(source_file, content)

        drawers_added = 0
        # Accumulate drawer metadata across batches so the closet emitter
        # below can consume it (Tier 6a date+line locators). Without this,
        # the new ``drawer_metas`` kwarg never reaches ``build_closet_lines``
        # in production and the 4-segment pointer form lives only in tests.
        # Per PR #1584 review (Igor, 2026-05-22).
        all_metas: list = []
        for batch_start in range(0, len(chunks), DRAWER_UPSERT_BATCH_SIZE):
            batch_docs: list = []
            batch_ids: list = []
            batch_metas: list = []
            for chunk in chunks[batch_start : batch_start + DRAWER_UPSERT_BATCH_SIZE]:
                drawer_id = make_drawer_id_from_chunk(wing, room, source_file, chunk["chunk_index"])
                batch_docs.append(chunk["content"])
                batch_ids.append(drawer_id)
                batch_metas.append(
                    _build_drawer_metadata(
                        wing,
                        room,
                        source_file,
                        chunk["chunk_index"],
                        agent,
                        chunk["content"],
                        source_mtime,
                        line_start=chunk.get("line_start"),
                        line_end=chunk.get("line_end"),
                        content_date=file_content_date,
                    )
                )
            assert_no_collisions(list(zip(batch_ids, batch_metas)), collection)
            collection.upsert(
                documents=batch_docs,
                ids=batch_ids,
                metadatas=batch_metas,
            )
            drawers_added += len(batch_docs)
            all_metas.extend(batch_metas)

        # Build closet — the searchable index pointing to these drawers.
        # Purge first: a re-mine (mtime change or normalize_version bump) must
        # fully replace the prior closets, not append to them.
        if closets_col and drawers_added > 0:
            drawer_ids = [
                make_drawer_id_from_chunk(wing, room, source_file, c["chunk_index"]) for c in chunks
            ]
            # Pass drawer_metas so build_closet_lines can emit the Tier 6a
            # 4-segment pointer (``topic|entities|YYYY-MM-DD:Lstart-Lend|->ids``)
            # when line_start / line_end / content_date are present. Falls
            # back to the legacy 3-segment form automatically when not.
            closet_lines = build_closet_lines(
                source_file,
                drawer_ids,
                content,
                wing,
                room,
                drawer_metas=all_metas,
            )
            closet_id_base = (
                f"closet_{wing}_{room}_{hashlib.sha256(source_file.encode()).hexdigest()[:24]}"
            )
            entities = _build_drawer_metadata(
                wing, room, source_file, 0, agent, content, source_mtime
            ).get("entities", "")
            # Use _extract_entities_for_metadata for the closet meta
            closet_meta = {
                "wing": wing,
                "room": room,
                "source_file": source_file,
                "drawer_count": drawers_added,
                "filed_at": datetime.now().isoformat(),
                "normalize_version": NORMALIZE_VERSION,
            }
            if entities:
                closet_meta["entities"] = entities
            purge_file_closets(closets_col, source_file)
            upsert_closet_lines(closets_col, closet_id_base, closet_lines, closet_meta)

    return drawers_added, room, None


def scan_project(
    project_dir: str,
    respect_gitignore: bool = True,
    include_ignored: Optional[list] = None,
) -> list:
    """Return list of all readable file paths under ``project_dir``.

    Skips symlinks and oversized files. Each skipped symlink is logged to
    ``sys.stderr`` with a ``  SKIP: <relative-path> (symlink)`` line so the
    caller can tell why a directory looks empty after walking.
    """
    project_path = Path(project_dir).expanduser().resolve()
    files = []
    active_matchers = []
    matcher_cache = {}
    include_paths = normalize_include_paths(include_ignored)

    for root, dirs, filenames in os.walk(project_path):
        root_path = Path(root)

        if respect_gitignore:
            active_matchers = [
                matcher
                for matcher in active_matchers
                if root_path == matcher.base_dir or matcher.base_dir in root_path.parents
            ]
            current_matcher = load_gitignore_matcher(root_path, matcher_cache)
            if current_matcher is not None:
                active_matchers.append(current_matcher)

        dirs[:] = [
            d
            for d in dirs
            if is_force_included(root_path / d, project_path, include_paths)
            or not should_skip_dir(d)
        ]
        if respect_gitignore and active_matchers:
            dirs[:] = [
                d
                for d in dirs
                if is_force_included(root_path / d, project_path, include_paths)
                or not is_gitignored(root_path / d, active_matchers, is_dir=True)
            ]

        for filename in filenames:
            filepath = root_path / filename
            force_include = is_force_included(filepath, project_path, include_paths)
            exact_force_include = is_exact_force_include(filepath, project_path, include_paths)

            if not force_include and filename in SKIP_FILENAMES:
                continue
            if filepath.suffix.lower() not in READABLE_EXTENSIONS and not exact_force_include:
                continue
            if respect_gitignore and active_matchers and not force_include:
                if is_gitignored(filepath, active_matchers, is_dir=False):
                    continue
            # Skip symlinks — prevents following links to /dev/urandom, etc.
            if filepath.is_symlink():
                rel = filepath.relative_to(project_path).as_posix()
                try:
                    print(f"  SKIP: {rel} (symlink)", file=sys.stderr)
                except OSError:
                    pass
                continue
            # Skip files exceeding size limit
            try:
                if filepath.stat().st_size > MAX_FILE_SIZE:
                    continue
            except OSError:
                continue
            files.append(filepath)
    return files
