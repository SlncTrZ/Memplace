"""Status — palace status reporting for the miner.

Wing: miner | Topic: status | Updated: 2026-06-28 18:30
"""

from collections import defaultdict


def status(palace_path: str):
    """Show what's been filed in the palace.

    Tallies drawers by wing/room from the backend in a routine
    status check. Falls back when the query is unavailable (missing DB,
    un-bootstrapped collection, or an unexpected schema); the fallback also
    emits the state-specific guidance for absent/empty palaces.
    """
    from ..palace import _open_collection_or_explain

    col = _open_collection_or_explain(palace_path)
    if col is None:
        return

    # Count by wing and room — paginate to avoid SQLite "too many SQL
    # variables" error on large palaces (see #802, #850).
    total = col.count()
    wing_rooms: dict = defaultdict(lambda: defaultdict(int))
    batch_size = 5000
    offset = 0
    while offset < total:
        r = col.get(limit=batch_size, offset=offset, include=["metadatas"])
        batch = r["metadatas"]
        if not batch:
            break
        for m in batch:
            m = m or {}
            wing_rooms[m.get("wing", "?")][m.get("room", "?")] += 1
        offset += len(batch)

    _print_status(total, wing_rooms)


def _print_status(total: int, wing_rooms: defaultdict) -> None:
    """Render the wing/room histogram shared by both status code paths."""
    print(f"\n{'=' * 55}")
    print(f"  MemPalace Status — {total} drawers")
    print(f"{'=' * 55}\n")
    for wing, rooms in sorted(wing_rooms.items()):
        print(f"  WING: {wing}")
        for room, count in sorted(rooms.items(), key=lambda x: x[1], reverse=True):
            print(f"    ROOM: {room:20} {count:5} drawers")
        print()
    print(f"{'=' * 55}\n")
