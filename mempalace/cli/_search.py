"""_search — `mempalace search` subcommand.

Wing: mempalace | Topic: cli | Updated: 2026-06-28
"""

import os
import sys

from ..config import MempalaceConfig


def cmd_search(args):
    """Run `mempalace search <query>` — semantic search across the palace."""
    from ..searcher import search, SearchError

    palace_path = os.path.expanduser(args.palace) if args.palace else MempalaceConfig().palace_path
    try:
        search(
            query=args.query,
            palace_path=palace_path,
            wing=args.wing,
            room=args.room,
            n_results=args.results,
        )
    except SearchError:
        sys.exit(1)
