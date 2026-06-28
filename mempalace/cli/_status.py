"""_status — `mempalace status`, `check-qdrant`, `repair-status`, `palace set-embedder`.

Wing: mempalace | Topic: cli | Updated: 2026-06-28
"""

import os
import sys

from ..config import MempalaceConfig


def _backend_arg(args):
    """Return a CLI-selected backend from subcommand or global flags."""
    return getattr(args, "backend", None) or getattr(args, "global_backend", None)


def cmd_status(args):
    """Show what's been filed in the palace."""
    from ..miner import status

    palace_path = os.path.expanduser(args.palace) if args.palace else MempalaceConfig().palace_path
    status(palace_path=palace_path)


def cmd_check_qdrant(args):
    """Quick Qdrant connectivity check — calls get_backend("qdrant").health()."""
    from ..backends import get_backend

    try:
        qdrant = get_backend("qdrant")
        status = qdrant.health()
        if status.ok:
            print(f"  Qdrant: OK — {status.detail}" if status.detail else "  Qdrant: OK")
        else:
            print(f"  Qdrant: UNHEALTHY — {status.detail}")
            sys.exit(1)
    except Exception as exc:
        print(f"  Qdrant: ERROR — {exc}", file=sys.stderr)
        sys.exit(1)


def cmd_repair_status(args):
    """Read-only Qdrant collection health check."""
    palace_path = os.path.expanduser(args.palace) if args.palace else MempalaceConfig().palace_path
    from ..repair import status as repair_status

    result = repair_status(palace_path=palace_path)
    if result.get("ok"):
        print("  Palace health: OK")
    else:
        print("  Palace health check completed — see details above.")


def cmd_palace_set_embedder(args):
    """Record (or force-override) a palace's embedder identity (RFC 001).

    Resolves the ``unknown`` state for a legacy palace, or records a specific
    model with ``--model``. It records identity on the palace only; it does not
    change the configured model — when the two differ it prints how to align
    ``MEMPALACE_EMBEDDING_MODEL``. ``--force`` overwrites an existing,
    differently-named identity.
    """
    from ..backends.base import EmbedderIdentityMismatchError
    from ..palace import set_palace_embedder_identity

    config = MempalaceConfig()
    palace_path = os.path.abspath(
        os.path.expanduser(args.palace) if args.palace else config.palace_path
    )
    model = getattr(args, "model", None)
    try:
        old, new = set_palace_embedder_identity(
            palace_path,
            model=model,
            force=getattr(args, "force", False),
            backend=_backend_arg(args),
        )
    except EmbedderIdentityMismatchError as exc:
        print(f"  ✗ {exc}")
        raise SystemExit(2) from exc
    if old is None:
        print(f"  ✓ recorded embedder identity: {new.model_name} (dim={new.dimension})")
    elif old.model_name == new.model_name:
        print(f"  ✓ embedder identity unchanged: {new.model_name} (dim={new.dimension})")
    else:
        print(
            f"  ✓ embedder identity changed: {old.model_name} → {new.model_name} "
            f"(dim={new.dimension})"
        )
    configured = config.embedding_model
    if new.model_name and configured and new.model_name != configured:
        print(
            f"  ⚠ configured model is {configured!r}; set MEMPALACE_EMBEDDING_MODEL="
            f"{new.model_name} (or run onboarding) so normal opens of this palace match."
        )
