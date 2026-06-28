"""Entities — known entity management for the miner.

Wing: miner | Topic: entities | Updated: 2026-06-28 18:30
"""

import json
import os
import re
from pathlib import Path as _Path

from typing import Optional

from ..entity_detector import _apply_known_systems_prepass, _get_coca_filter
from ..palace import _ENTITY_STOPLIST, _candidate_entity_words

_ENTITY_REGISTRY_PATH = os.path.join(os.path.expanduser("~"), ".mempalace", "known_entities.json")
_ENTITY_REGISTRY_CACHE: dict = {"mtime": None, "names": frozenset(), "raw": {}}
_ENTITY_EXTRACT_WINDOW = 5000  # chars of content scanned for capitalized words
_ENTITY_METADATA_LIMIT = 25  # max entities packed into the metadata field


def _refresh_known_entities_cache() -> None:
    """Reload ``~/.mempalace/known_entities.json`` into the module cache if
    its mtime changed since the last read. Shared by ``_load_known_entities``
    (flat set) and ``_load_known_entities_raw`` (category dict), so callers
    can pick whichever shape they need without duplicating the mtime-gated
    disk read.
    """
    try:
        mtime = os.path.getmtime(_ENTITY_REGISTRY_PATH)
    except OSError:
        if _ENTITY_REGISTRY_CACHE["mtime"] is not None:
            _ENTITY_REGISTRY_CACHE["mtime"] = None
            _ENTITY_REGISTRY_CACHE["names"] = frozenset()
            _ENTITY_REGISTRY_CACHE["raw"] = {}
        return

    if _ENTITY_REGISTRY_CACHE["mtime"] == mtime:
        return

    names: set = set()
    raw: dict = {}
    try:
        with open(_ENTITY_REGISTRY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            raw = data
            for cat_key, cat in data.items():
                # Special wing-keyed map — its inner values are topic
                # names but its outer keys are wings, which must NOT be
                # surfaced as known entities. Pull the topic names out
                # explicitly instead of treating it as a generic category.
                if cat_key == "topics_by_wing" and isinstance(cat, dict):
                    for topic_list in cat.values():
                        if isinstance(topic_list, list):
                            names.update(str(n) for n in topic_list if n)
                    continue
                if isinstance(cat, list):
                    names.update(str(n) for n in cat if n)
                elif isinstance(cat, dict):
                    names.update(str(k) for k in cat.keys() if k)
    except Exception:
        names = set()
        raw = {}

    _ENTITY_REGISTRY_CACHE["mtime"] = mtime
    _ENTITY_REGISTRY_CACHE["names"] = frozenset(names)
    _ENTITY_REGISTRY_CACHE["raw"] = raw


def _load_known_entities() -> frozenset:
    """Flat set of every known entity name (across all categories).

    Cached by mtime; invalidated when the registry file changes.
    """
    _refresh_known_entities_cache()
    return _ENTITY_REGISTRY_CACHE["names"]


def _load_known_entities_raw() -> dict:
    """Full category-dict view of the registry, shape
    ``{"category": ["Name1", ...], ...}``. Cached by mtime.

    Consumed by modules (e.g., fact_checker) that need to reason about
    categories rather than a flat name set. Never returns a mutable
    reference to the cache — callers get a shallow copy.
    """
    _refresh_known_entities_cache()
    return dict(_ENTITY_REGISTRY_CACHE["raw"])


def _set_wing_topics(existing: dict, wing_key: str, topics_for_wing: list, coerce) -> None:
    """Update ``existing['topics_by_wing'][wing_key]`` to the deduped list.

    Replaces (does not union) the wing's topic list — re-running ``init``
    should reflect the user's latest confirmation rather than accumulate
    stale labels. Empty input drops the wing entry; an empty map drops
    the ``topics_by_wing`` key entirely.
    """
    topics_map = existing.get("topics_by_wing")
    if not isinstance(topics_map, dict):
        topics_map = {}
    seen_lower: set = set()
    ordered: list = []
    for n in topics_for_wing:
        name = coerce(n)
        if not name:
            continue
        key = name.lower()
        if key in seen_lower:
            continue
        seen_lower.add(key)
        ordered.append(name)
    if ordered:
        topics_map[wing_key] = ordered
    else:
        topics_map.pop(wing_key, None)
    if topics_map:
        existing["topics_by_wing"] = topics_map
    else:
        existing.pop("topics_by_wing", None)


def add_to_known_entities(entities_by_category: dict, wing: Optional[str] = None) -> str:
    """Union ``entities_by_category`` into ``~/.mempalace/known_entities.json``.

    Accepts ``{category: [names]}`` shape as produced by ``mempalace init``
    and merges into the registry the miner reads at mine time. Existing
    categories are preserved untouched unless also present in the input;
    for categories present in both, entries are unioned case-insensitively
    without changing the on-disk ordering of pre-existing names.

    If a category is stored on-disk as ``{name: code}`` (the alternate
    miner-supported shape, used by dialect-style configs), new names are
    added as keys with ``None`` values so existing code mappings aren't
    overwritten. A later compress pass can assign codes.

    When ``wing`` is provided AND ``entities_by_category`` contains a
    ``topics`` list, those topics are also recorded under
    ``topics_by_wing[wing]`` (case-insensitive dedup, preserving the
    casing of the first observed name). This is the signal source for
    ``palace_graph.compute_topic_tunnels`` at mine time. Topics for a
    wing are *replaced*, not unioned, so a re-run of ``init`` reflects
    the user's latest confirmation rather than accumulating stale labels
    indefinitely.

    The in-process cache is invalidated on write so same-process callers
    (notably ``cmd_init`` → ``cmd_mine`` in sequence) see the update
    immediately instead of waiting for a mtime re-check.

    Returns the registry path as a string for logging.
    """
    registry_path = _Path(_ENTITY_REGISTRY_PATH)
    registry_path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict = {}
    if registry_path.exists():
        try:
            loaded = json.loads(registry_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except (json.JSONDecodeError, OSError):
            existing = {}

    def _coerce_name(value):
        if not value:
            return None
        name = str(value)
        return name if name else None

    # Separate the topics_by_wing key from regular categories so we don't
    # treat it as a flat name-list elsewhere in this function.
    topics_for_wing = None
    wing_val = wing
    if wing_val and isinstance(wing_val, str) and wing_val.strip():
        topics_for_wing = entities_by_category.get("topics") or []

    for category, names in entities_by_category.items():
        if category == "topics_by_wing":
            # Reserved key — managed separately below.
            continue
        if not isinstance(names, list) or not names:
            continue
        current = existing.get(category)
        if isinstance(current, list):
            seen_lower = {str(n).lower() for n in current}
            for n in names:
                name = _coerce_name(n)
                if not name:
                    continue
                if name.lower() not in seen_lower:
                    current.append(name)
                    seen_lower.add(name.lower())
        elif isinstance(current, dict):
            seen_lower = {str(name).lower() for name in current}
            for n in names:
                name = _coerce_name(n)
                if not name or name.lower() in seen_lower:
                    continue
                current[name] = None
                seen_lower.add(name.lower())
        else:
            # Missing or unrecognized shape — seed as a fresh list, deduped
            seen: set = set()
            ordered: list = []
            for n in names:
                name = _coerce_name(n)
                if not name:
                    continue
                key = name.lower()
                if key in seen:
                    continue
                seen.add(key)
                ordered.append(name)
            existing[category] = ordered

    if topics_for_wing is not None and isinstance(wing_val, str):
        _set_wing_topics(existing, wing_val.strip(), topics_for_wing, _coerce_name)

    registry_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        registry_path.chmod(0o600)
    except (OSError, NotImplementedError):
        pass

    # Invalidate in-process cache so later calls in the same run see the write.
    _ENTITY_REGISTRY_CACHE["mtime"] = None
    _ENTITY_REGISTRY_CACHE["names"] = frozenset()
    _ENTITY_REGISTRY_CACHE["raw"] = {}

    return str(registry_path)


def get_topics_by_wing() -> dict:
    """Return ``topics_by_wing`` from the global registry as a dict.

    Returns ``{}`` if the registry is missing, malformed, or has no
    ``topics_by_wing`` key. Casing is preserved from disk; callers that
    need case-insensitive comparison should normalize themselves.
    """
    raw = _load_known_entities_raw()
    topics_map = raw.get("topics_by_wing")
    if not isinstance(topics_map, dict):
        return {}
    out: dict = {}
    for wing, topics in topics_map.items():
        if not isinstance(wing, str) or not wing.strip():
            continue
        if isinstance(topics, list):
            cleaned = [str(t) for t in topics if isinstance(t, str) and t.strip()]
            if cleaned:
                out[wing.strip()] = cleaned
    return out


def _extract_entities_for_metadata(content: str) -> str:
    """Extract entity names from content for metadata tagging.

    Combines the user's known-entity registry (cached across calls) with
    capitalized words appearing ≥2 times in the first ``_ENTITY_EXTRACT_WINDOW``
    chars. Filters out the closet stoplist (``When``, ``After``, ``The``, …)
    so sentence-starters don't masquerade as proper nouns.

    Returns semicolon-separated string suitable for metadata
    filtering. The list is truncated to ``_ENTITY_METADATA_LIMIT`` entries
    *before* joining so a name is never cut in half.
    """
    matched: set = set()

    known = _load_known_entities()
    for name in known:
        # Case-insensitive match — mirrors entity_detector.py's init-time
        # behavior so a known entity like "Aya" tags drawers that mention
        # "aya" / "AYA" / "Aya". Without re.IGNORECASE, lowercase mentions
        # in chat transcripts and voice-typed content get silently untagged.
        if re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", content, re.IGNORECASE):
            matched.add(name)

    coca_filter = _get_coca_filter()
    window = content[:_ENTITY_EXTRACT_WINDOW]
    # Tier 3 linguistics cleanup — known-systems compound pre-pass. Detects
    # multi-word product names atomically and masks them from the window so
    # the single-word extraction below doesn't decompose them into their
    # constituent tokens (which would then either get COCA-filtered or
    # appear as wrongly-attributed standalone entities).
    working_window, compound_counts = _apply_known_systems_prepass(window)
    words = _candidate_entity_words(working_window)
    freq: dict = dict(compound_counts)
    for w in words:
        if w in _ENTITY_STOPLIST:
            continue
        # Tier 2 linguistics cleanup — drop common English content words
        # ("Code", "Line", "Note", "Phase", …) from per-drawer entity
        # metadata so they don't poison hallways/tunnels/search.
        if w.lower() in coca_filter:
            continue
        freq[w] = freq.get(w, 0) + 1
    for w, c in freq.items():
        if c >= 2 and len(w) > 2:
            matched.add(w)

    if not matched:
        return ""
    # Truncate the *list*, not the joined string — never split a name.
    capped = sorted(matched)[:_ENTITY_METADATA_LIMIT]
    return ";".join(capped)
