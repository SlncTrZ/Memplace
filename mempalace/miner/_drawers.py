"""Drawers — metadata building and upsert for the miner.

Wing: miner | Topic: drawers | Updated: 2026-06-28 18:30
"""

import os
from datetime import datetime

from typing import Optional

from ..ids import ID_RECIPE, make_drawer_id_from_chunk
from ..palace import NORMALIZE_VERSION
from ._entities import _extract_entities_for_metadata

_HALL_KEYWORDS_CACHE = None


def detect_hall(content: str) -> str:
    """Route content to a hall based on keyword scoring.

    Halls connect rooms within a wing — they categorize the TYPE of content
    (emotional, technical, family, etc.) while rooms categorize the TOPIC.
    """
    global _HALL_KEYWORDS_CACHE
    if _HALL_KEYWORDS_CACHE is None:
        from ..config import MempalaceConfig

        _HALL_KEYWORDS_CACHE = MempalaceConfig().hall_keywords
    content_lower = content[:3000].lower()

    scores = {}
    for hall, keywords in _HALL_KEYWORDS_CACHE.items():
        score = sum(1 for kw in keywords if kw in content_lower)
        if score > 0:
            scores[hall] = score

    if scores:
        return max(scores, key=lambda k: scores[k])
    return "general"


def _build_drawer_metadata(
    wing: str,
    room: str,
    source_file: str,
    chunk_index: int,
    agent: str,
    content: str,
    source_mtime: Optional[float],
    line_start: Optional[int] = None,
    line_end: Optional[int] = None,
    content_date: Optional[str] = None,
) -> dict:
    """Build the metadata dict for one drawer without upserting.

    Split out from ``add_drawer`` so ``process_file`` can batch all chunks
    of a file into a single ``collection.upsert`` — one embedding forward
    pass per batch instead of per chunk.

    Tier 6a — ``line_start`` / ``line_end`` are optional 1-indexed line
    numbers in the source file. ``content_date`` is the optional ISO date
    extracted from filename / frontmatter / content body / mtime. When
    passed, they're stored in metadata so closet pointers can carry
    "where in the source" + "when the content is from" info. When omitted
    (legacy callers, pre-Tier-6a drawers), the keys are absent from the
    returned dict and downstream code falls back to ``filed_at`` for the
    date and the 3-segment closet pointer format.
    """
    metadata = {
        "wing": wing,
        "room": room,
        "source_file": source_file,
        "chunk_index": chunk_index,
        "added_by": agent,
        "filed_at": datetime.now().isoformat(),
        "normalize_version": NORMALIZE_VERSION,
        "id_recipe": ID_RECIPE,
    }
    if source_mtime is not None:
        metadata["source_mtime"] = source_mtime
    if line_start is not None:
        metadata["line_start"] = line_start
    if line_end is not None:
        metadata["line_end"] = line_end
    if content_date:
        metadata["content_date"] = content_date
    metadata["hall"] = detect_hall(content)
    entities = _extract_entities_for_metadata(content)
    if entities:
        metadata["entities"] = entities
    return metadata


def add_drawer(
    collection, wing: str, room: str, content: str, source_file: str, chunk_index: int, agent: str
):
    """Add one drawer to the palace.

    Kept for backward compatibility with external callers. In-tree the
    miner uses ``_build_drawer_metadata`` + a batched ``collection.upsert``
    to amortize the embedding model's forward-pass cost across chunks.
    """
    drawer_id = make_drawer_id_from_chunk(wing, room, source_file, chunk_index)
    try:
        source_mtime = os.path.getmtime(source_file)
    except OSError:
        source_mtime = None
    metadata = _build_drawer_metadata(
        wing, room, source_file, chunk_index, agent, content, source_mtime
    )
    collection.upsert(
        documents=[content],
        ids=[drawer_id],
        metadatas=[metadata],
    )
    return True
