"""Chunking — text chunking logic for the miner.

Wing: miner | Topic: chunking | Updated: 2026-06-28 18:30
"""

from typing import Optional

from ..config import DEFAULT_CHUNK_SIZE as CHUNK_SIZE
from ..config import DEFAULT_CHUNK_OVERLAP as CHUNK_OVERLAP
from ..config import DEFAULT_MIN_CHUNK_SIZE as MIN_CHUNK_SIZE


def chunk_text(
    content: str,
    source_file: str,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
    min_chunk_size: Optional[int] = None,
) -> list:
    """
    Split content into drawer-sized chunks.
    Tries to split on paragraph/line boundaries.
    Returns list of {"content": str, "chunk_index": int, "line_start": int, "line_end": int}

    ``line_start`` / ``line_end`` are 1-indexed line numbers in the stripped
    source, giving an approximate locator for where the chunk came from.
    Closet pointers (Tier 6a) use this to emit ``YYYY-MM-DD:L42-L78`` segments
    so retrieval can jump straight to the right span without opening the
    whole drawer.

    Optional params override module-level defaults when provided.
    """
    if chunk_size is None:
        chunk_size = CHUNK_SIZE
    if chunk_overlap is None:
        chunk_overlap = CHUNK_OVERLAP
    if min_chunk_size is None:
        min_chunk_size = MIN_CHUNK_SIZE

    # Defensive invariant guard. ``MempalaceConfig.chunk_*`` already
    # enforces these and falls back to defaults on bad config.json
    # values, but ``chunk_text`` is a public function — direct callers
    # (tests, library users, future caller paths) might still pass
    # values that would loop forever. Fail fast and loud rather than
    # hang. See review feedback on #1024.
    if not isinstance(chunk_size, int) or chunk_size <= 0:
        raise ValueError(f"chunk_size must be a positive int, got {chunk_size!r}")
    if not isinstance(chunk_overlap, int) or chunk_overlap < 0:
        raise ValueError(f"chunk_overlap must be a non-negative int, got {chunk_overlap!r}")
    if chunk_overlap >= chunk_size:
        # ``start = end - chunk_overlap`` would not advance (or would go
        # backward) when overlap >= size, producing an infinite loop on
        # any non-empty input.
        raise ValueError(
            f"chunk_overlap ({chunk_overlap}) must be less than chunk_size "
            f"({chunk_size}); equality or greater would loop forever"
        )
    if not isinstance(min_chunk_size, int) or min_chunk_size < 0:
        raise ValueError(f"min_chunk_size must be a non-negative int, got {min_chunk_size!r}")

    # Clean up
    content = content.strip()
    if not content:
        return []

    chunks = []
    start = 0
    chunk_index = 0

    while start < len(content):
        end = min(start + chunk_size, len(content))

        # Try to break at paragraph boundary
        if end < len(content):
            newline_pos = content.rfind("\n\n", start, end)
            if newline_pos > start + chunk_size // 2:
                end = newline_pos
            else:
                newline_pos = content.rfind("\n", start, end)
                if newline_pos > start + chunk_size // 2:
                    end = newline_pos

        chunk = content[start:end].strip()
        if len(chunk) >= min_chunk_size:
            # Tier 6a — 1-indexed line range in the stripped source.
            # Approximate locator (±1 at boundaries is fine for "jump to
            # roughly here"); exact-quote positioning is a future tier.
            # Use the bounds form of ``str.count`` (counts on the original
            # string with start/end limits) instead of slicing — slicing
            # would allocate a new substring per chunk and produce O(N^2)
            # work on a 500MB file with 50K chunks. Per PR #1579 review
            # (gemini-code-assist, medium priority).
            line_start = content.count("\n", 0, start) + 1
            line_end = content.count("\n", 0, end) + 1
            chunks.append(
                {
                    "content": chunk,
                    "chunk_index": chunk_index,
                    "line_start": line_start,
                    "line_end": line_end,
                }
            )
            chunk_index += 1

        start = end - chunk_overlap if end < len(content) else end

    return chunks
