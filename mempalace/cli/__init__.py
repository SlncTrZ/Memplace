"""MemPalace CLI Package — split monolith into sub-modules.

Re-exports the primary CLI entry point and internal helpers needed by
downstream modules (daemon service, __main__).

Wing: mempalace | Topic: cli | Updated: 2026-06-28
"""

from ._main import main

# Internal helpers imported by service.py, __main__.py
from ._init import _run_pass_zero

__all__ = ["main", "_run_pass_zero"]
