"""Rooms — file-to-room routing logic for the miner.

Wing: miner | Topic: rooms | Updated: 2026-06-28 18:30
"""

import re
from collections import defaultdict
from pathlib import Path


_TOKEN_SPLIT = re.compile(r"[-_./]+")


def _tokens(value: str) -> set:
    """Split ``value`` into lowercased tokens bounded by ``-``, ``_``, ``.`` or ``/``."""
    return {t for t in _TOKEN_SPLIT.split(value.lower()) if t}


def _name_matches(a: str, b: str) -> bool:
    """Return True when ``a`` and ``b`` match as equal strings or as
    separator-bounded tokens of each other.

    Prevents incidental substring collisions (e.g., ``"views" in "interviews"``)
    that a raw ``in`` check would produce, while preserving the intended
    match for real tokens (e.g., ``"frontend"`` in ``"frontend-app"``).
    """
    a = a.lower()
    b = b.lower()
    if a == b:
        return True
    return b in _tokens(a) or a in _tokens(b)


def detect_room(filepath: Path, content: str, rooms: list, project_path: Path) -> str:
    """
    Route a file to the right room.
    Priority:
    1. Folder path matches a room name
    2. Filename matches a room name or keyword
    3. Content keyword scoring
    4. Fallback: "general"
    """
    relative = str(filepath.relative_to(project_path)).lower()
    filename = filepath.stem.lower()
    content_lower = content[:2000].lower()

    # Priority 1: folder path matches room name or keywords
    path_parts = relative.replace("\\", "/").split("/")
    for part in path_parts[:-1]:  # skip filename itself
        for room in rooms:
            candidates = [room["name"].lower()] + [k.lower() for k in room.get("keywords", [])]
            if any(_name_matches(part, c) for c in candidates):
                return room["name"]

    # Priority 2: filename matches room name
    for room in rooms:
        if _name_matches(filename, room["name"]):
            return room["name"]

    # Priority 3: keyword scoring from room keywords + name
    scores = defaultdict(int)
    for room in rooms:
        keywords = room.get("keywords", []) + [room["name"]]
        for kw in keywords:
            count = content_lower.count(kw.lower())
            scores[room["name"]] += count

    if scores:
        best = max(scores, key=lambda k: scores[k])
        if scores[best] > 0:
            return best

    return "general"
