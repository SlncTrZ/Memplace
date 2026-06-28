"""_repair — `mempalace repair` subcommand.

Wing: mempalace | Topic: cli | Updated: 2026-06-28
"""

import os

from ..config import MempalaceConfig


def cmd_repair(args):
    """Run Qdrant-based palace repair — health check, backup, and rebuild."""
    config = MempalaceConfig()
    palace_path = os.path.abspath(
        os.path.expanduser(args.palace) if args.palace else config.palace_path
    )
    from ..repair import repair_health, repair_backup, repair_rebuild

    mode = getattr(args, "mode", "legacy")
    if mode != "legacy":
        print(f"  Mode {mode!r} is only supported via direct API; falling back to health check.")
        mode = "legacy"

    print(f"\n{'=' * 55}")
    print(" MemPalace Repair (Qdrant)")
    print(f"{'=' * 55}\n")
    print(f"  Palace: {palace_path}")

    health = repair_health(palace_path=palace_path)
    if not health.get("ok"):
        print("  Error during health check — see details above.")
        return

    bkp = repair_backup(palace_path=palace_path)
    if bkp.get("backup_path"):
        print(f"  Backup saved at {bkp['backup_path']}")

    result = repair_rebuild(
        palace_path=palace_path,
        collection_name=config.collection_name,
    )
    if result.get("ok"):
        print("\n  Repair complete.")
    else:
        print("\n  Repair encountered issues — see details above.")
    print(f"\n{'=' * 55}\n")
