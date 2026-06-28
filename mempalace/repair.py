"""
repair.py — Palace health check and snapshot-based recovery (Qdrant edition)

When the legacy backend was removed (RFC 001), the old repair module that managed
HNSW index rebuilds became vestigial. Qdrant handles its own HNSW index
internally — no manual rebuild needed.

This module provides:

  status        — read-only health check: KG SQLite integrity + Qdrant
                  collection stats
  repair_backup — create a Qdrant collection snapshot
  repair_rebuild  — alias of repair_backup (Qdrant has no index to rebuild)
  repair_health — lightweight health summary for automation

Legacy function signatures exposed to cli.py are preserved as thin
wrappers or no-ops.

Wing: palace | Topic: maintenance | Updated: 2026-06-28 15:00
"""

import argparse
import os
import sqlite3
from typing import Optional

from qdrant_client import QdrantClient

from .config import sqlite_read_uri

COLLECTION_NAME = "mempalace_drawers"
CLOSETS_COLLECTION_NAME = "mempalace_closets"


# ── Qdrant helpers ──────────────────────────────────────────────────────


def _get_qdrant_client(url: Optional[str] = None) -> QdrantClient:
    """Return a lazily-initialised QdrantClient.

    Falls back to ``QDRANT_URL`` env var, then ``http://localhost:6333``.
    """
    resolved = url or os.getenv("QDRANT_URL", "http://localhost:6333")
    return QdrantClient(url=resolved, prefer_grpc=False)


def _drawers_collection_name() -> str:
    """Resolve the drawers collection name from user config."""
    try:
        from .config import MempalaceConfig

        return MempalaceConfig().collection_name or COLLECTION_NAME
    except Exception:
        return COLLECTION_NAME


def _get_palace_path() -> str:
    """Resolve palace path from config."""
    try:
        from .config import MempalaceConfig

        return MempalaceConfig().palace_path
    except Exception:
        return os.path.join(os.path.expanduser("~"), ".mempalace", "palace")


# ── KG SQLite helpers ───────────────────────────────────────────────────


def _kg_path(palace_path: str) -> str:
    """Full path to the Knowledge Graph SQLite database."""
    return os.path.join(palace_path, "knowledge_graph.sqlite3")


def sqlite_integrity_errors(palace_path: str) -> list[str]:
    """Run ``PRAGMA quick_check`` against the Knowledge Graph SQLite database.

    Returns a list of error messages (empty = healthy). Returns an empty
    list when the KG database does not exist (it is optional).
    """
    db_path = _kg_path(palace_path)
    if not os.path.isfile(db_path):
        return []

    try:
        with sqlite3.connect(sqlite_read_uri(db_path), uri=True) as conn:
            rows = conn.execute("PRAGMA quick_check").fetchall()
    except sqlite3.Error as exc:
        return [f"PRAGMA quick_check failed: {exc}"]
    except Exception as exc:
        return [f"Cannot open KG database: {exc}"]

    errors: list[str] = []
    for row in rows:
        if not row:
            continue
        msg = str(row[0])
        if msg.lower() != "ok":
            errors.append(msg)
    return errors


def print_sqlite_integrity_abort(palace_path: str, errors: list[str]) -> None:
    """Print a clear abort banner for Knowledge Graph SQLite corruption.

    (Preserved for the cli.py ``cmd_mine`` exception handler; now points
    at ``knowledge_graph.sqlite3``.)
    """
    db_path = _kg_path(palace_path)
    preview = errors[:5]
    n_extra = max(0, len(errors) - len(preview))

    print("\n  ABORT: Knowledge Graph SQLite database failed PRAGMA quick_check.")
    print(f"  Database: {db_path}")
    print()
    print("  quick_check output:")
    for msg in preview:
        print(f"    - {msg}")
    if n_extra:
        print(f"    ... and {n_extra} more issue(s)")
    print()
    print("  The Knowledge Graph is a separate SQLite database inside the palace")
    print("  directory. Drawers stored in Qdrant are unaffected by this corruption.")
    print()
    print("  Recovery options:")
    print("    1. Restore knowledge_graph.sqlite3 from backup.")
    print("    2. Run sqlite3 `.recover` or `REINDEX` on the database.")
    print("    3. Delete knowledge_graph.sqlite3 to start fresh (KG will be rebuilt).")
    print()


# ── Qdrant snapshot operations ─────────────────────────────────────────


def _collection_stats(
    palace_path: str,
    collection_name: str,
    client: QdrantClient,
) -> dict:
    """Return a dict of collection stats from Qdrant + local KG."""
    result: dict = {
        "collection": collection_name,
        "points_count": 0,
        "status": "unknown",
    }

    try:
        info = client.get_collection(collection_name)
        result["points_count"] = info.points_count or 0
        result["status"] = str(info.status or "")
    except Exception as exc:
        result["error"] = str(exc)

    # KG SQLite integrity
    kg_errors = sqlite_integrity_errors(palace_path)
    result["kg_integrity"] = "ok" if not kg_errors else "corrupt"
    if kg_errors:
        result["kg_errors"] = kg_errors

    # KG drawer count (approximate)
    try:
        db_path = _kg_path(palace_path)
        if os.path.isfile(db_path):
            with sqlite3.connect(sqlite_read_uri(db_path), uri=True) as conn:
                row = conn.execute("SELECT COUNT(*) FROM entities").fetchone()
                result["kg_entities"] = int(row[0]) if row else 0
    except Exception:
        result["kg_entities"] = None

    return result


def status(
    palace_path: Optional[str] = None,
    collection_name: Optional[str] = None,
) -> dict:
    """Read-only health check: KG SQLite integrity + Qdrant collection stats.

    Returns a dict of per-collection stats (printed as well). Returns
    ``{"status": "unknown"}`` when no palace exists at the given path.
    """
    palace_path = palace_path or _get_palace_path()
    collection_name = collection_name or _drawers_collection_name()

    print(f"\n{'=' * 55}")
    print("  MemPalace Repair — Status (Qdrant)")
    print(f"{'=' * 55}\n")
    print(f"  Palace: {palace_path}")

    if not os.path.isdir(palace_path):
        print("  No palace found.\n")
        return {"status": "unknown", "message": "no palace at path"}

    # KG SQLite check
    kg_errors = sqlite_integrity_errors(palace_path)
    print("\n  [knowledge_graph.sqlite3]")
    if kg_errors:
        print(f"    integrity:  CORRUPT ({len(kg_errors)} issue(s))")
    else:
        print("    integrity:  ok")

    try:
        db_path = _kg_path(palace_path)
        if os.path.isfile(db_path):
            with sqlite3.connect(sqlite_read_uri(db_path), uri=True) as conn:
                row = conn.execute("SELECT COUNT(*) FROM entities").fetchone()
                print(f"    entities:   {int(row[0]):,}" if row else "    entities:   0")
    except Exception:
        print("    entities:   (unreadable)")

    # Qdrant collection check
    try:
        client = _get_qdrant_client()

        drawers = _collection_stats(palace_path, collection_name, client)
        closets = _collection_stats(palace_path, CLOSETS_COLLECTION_NAME, client)

        for label, info in (("drawers", drawers), ("closets", closets)):
            print(f"\n  [{label}]")
            print(f"    points:     {info.get('points_count', '?'):,}")
            print(f"    status:     {info.get('status', 'unknown')}")
            if info.get("error"):
                print(f"    error:      {info['error']}")
            if info.get("kg_integrity"):
                print(f"    kg_sqlite:  {info['kg_integrity']}")
            if info.get("kg_entities") is not None:
                print(f"    kg_entities:{info['kg_entities']:,}")
    except Exception as exc:
        print(f"\n  Qdrant connection failed: {exc}")

    print()
    # Build return value: drawers/closets may be unbound if Qdrant connection failed
    drawers_info = locals().get("drawers", {})
    closets_info = locals().get("closets", {})
    return {
        "drawers": drawers_info,
        "closets": closets_info,
    }


def repair_health(palace_path: Optional[str] = None) -> dict:
    """Lightweight health summary for automation / monitoring.

    Returns:
        ``{"status": "healthy", "drawers_count": N, "kg_ok": True}``
        or ``{"status": "unhealthy", ...}`` on failure.
    """
    palace_path = palace_path or _get_palace_path()
    result: dict = {"status": "unknown"}

    if not os.path.isdir(palace_path):
        result["status"] = "missing"
        result["message"] = "palace directory not found"
        return result

    # KG SQLite health
    kg_errors = sqlite_integrity_errors(palace_path)
    result["kg_ok"] = len(kg_errors) == 0
    if kg_errors:
        result["kg_errors"] = kg_errors

    # Qdrant collection count
    try:
        client = _get_qdrant_client()
        collection_name = _drawers_collection_name()
        info = client.get_collection(collection_name)
        result["drawers_count"] = info.points_count or 0
        result["status"] = "healthy" if result.get("kg_ok", True) else "degraded"
    except Exception as exc:
        result["status"] = "unreachable"
        result["error"] = str(exc)

    return result


def repair_backup(palace_path: Optional[str] = None) -> dict:
    """Create a Qdrant collection snapshot for backup.

    Uses Qdrant's native ``create_snapshot`` API — no file copies needed.
    Returns the snapshot URL / path on success.

    The Knowledge Graph SQLite file is NOT snapshotted here; back it up
    separately if needed.
    """
    palace_path = palace_path or _get_palace_path()
    collection_name = _drawers_collection_name()

    print(f"\n{'=' * 55}")
    print("  MemPalace Repair — Snapshot Backup")
    print(f"{'=' * 55}\n")
    print(f"  Palace:  {palace_path}")
    print(f"  Qdrant collection: {collection_name}")

    if not os.path.isdir(palace_path):
        print("  No palace found.\n")
        return {"status": "error", "message": "palace directory not found"}

    try:
        client = _get_qdrant_client()

        if not client.collection_exists(collection_name):
            print(f"  Collection {collection_name!r} does not exist.\n")
            return {"status": "error", "message": f"collection {collection_name!r} not found"}

        snapshot = client.create_snapshot(collection_name=collection_name)
        snapshot_url = getattr(snapshot, "url", None) or getattr(
            snapshot, "location", str(snapshot)
        )

        print(f"  Snapshot created: {snapshot_url}")
        print(f"\n{'=' * 55}\n")

        return {"status": "ok", "snapshot_url": snapshot_url}
    except Exception as exc:
        print(f"  Snapshot failed: {exc}\n")
        return {"status": "error", "message": str(exc)}


def repair_rebuild(
    palace_path: Optional[str] = None,
    collection_name: Optional[str] = None,
    confirm_truncation_ok: bool = False,
    **kwargs,
) -> dict:
    """Rebuild the palace — Qdrant handles its own HNSW, so this is
    equivalent to taking a snapshot backup.

    Preserved as a CLI entry point. The old ``rebuild_index`` logic
    (batch-extract, delete, re-upsert) is unnecessary with Qdrant:
    the vector database manages its own index internally.
    """
    # ``confirm_truncation_ok`` and extra kwargs are accepted for
    # backward compatibility with callers that passed them.
    return repair_backup(palace_path)


# ── Legacy signature stubs (imported by cli.py) ─────────────────────────


def repair_max_seq_id(
    palace_path: str,
    *,
    segment: Optional[str] = None,
    from_sidecar: Optional[str] = None,
    threshold: int = 1 << 53,
    backup: bool = True,
    dry_run: bool = False,
    assume_yes: bool = False,
) -> dict:
    """No-op: max_seq_id is a backend-only concept.

    Preserved so cli.py's ``cmd_repair --mode max-seq-id`` doesn't
    break.
    """
    print("\n  max_seq_id repair is not needed with the Qdrant backend.")
    print("  (Backend-only concept; Qdrant manages its own sequence IDs.)\n")
    return {
        "palace_path": palace_path,
        "dry_run": dry_run,
        "aborted": True,
        "reason": "legacy-only-concept",
        "segment_repaired": [],
        "before": {},
        "after": {},
        "backup": None,
    }


class RebuildPartialError(Exception):
    """No-op: kept for backward compatibility with cli.py imports.

    The Qdrant backend does not need multi-collection rebuilds, so
    this exception is never raised.
    """

    def __init__(
        self,
        message: str = "Qdrant backend does not use partial rebuilds",
        *,
        partial_counts: Optional[dict[str, int]] = None,
        failed_collection: Optional[str] = None,
        dest_palace: Optional[str] = None,
        archive_path: Optional[str] = None,
    ):
        super().__init__(message)
        self.message = message
        self.partial_counts = partial_counts or {}
        self.failed_collection = failed_collection or "unknown"
        self.dest_palace = dest_palace or ""
        self.archive_path = archive_path


def rebuild_from_sqlite(
    source_palace: str,
    dest_palace: str,
    *,
    archive_existing_dest: bool = False,
    batch_size: int = 1000,
) -> dict[str, int]:
    """No-op: Qdrant does not store data in a SQLite file.

    Preserved so cli.py's ``cmd_repair --mode from-sqlite`` path
    doesn't break. Qdrant collections are backed up via the snapshot
    API instead.
    """
    print(f"\n{'=' * 55}")
    print("  MemPalace Repair — Rebuild from SQLite (no-op)")
    print(f"{'=' * 55}\n")
    print("  The Qdrant backend does not use SQLite; drawers are")
    print("  stored in Qdrant's own collection. This operation is not needed.")
    print()
    print("  To back up your Qdrant collection, use the snapshot API:")
    print("      mempalace repair-backup  # calls Qdrant create_snapshot()")
    print(f"\n{'=' * 55}\n")
    return {}


# ── CLI entry point ─────────────────────────────────────────────────────

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="MemPalace repair tools (Qdrant)")
    p.add_argument(
        "command",
        choices=["status", "health", "backup", "rebuild"],
    )
    p.add_argument("--palace", default=None, help="Palace directory path")
    args = p.parse_args()

    path = os.path.expanduser(args.palace) if args.palace else None

    if args.command == "status":
        status(palace_path=path)
    elif args.command == "health":
        print(repair_health(palace_path=path))
    elif args.command in ("backup", "rebuild"):
        repair_backup(palace_path=path)
