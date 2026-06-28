"""Readable — file-level reading and extension/filename constants for the miner.

Wing: miner | Topic: readable | Updated: 2026-06-28 18:30
"""

import os
import stat
import sys
from pathlib import Path
from typing import Optional


PHP_EXTENSIONS = {
    # Compound Blade templates such as ``view.blade.php`` are covered by the
    # final ``.php`` suffix.
    ".php",
    ".php3",
    ".php4",
    ".php5",
    ".php7",
    ".php8",
    ".phtml",
    ".phps",
    ".phpt",
    ".inc",
    ".aw",
    ".fcgi",
    ".ctp",
    ".module",
    ".install",
    ".profile",
    ".theme",
    ".engine",
    ".twig",
    ".blade",
    ".tpl",
    ".latte",
    ".volt",
}

READABLE_EXTENSIONS = {
    ".txt",
    ".md",
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".html",
    ".css",
    ".java",
    ".go",
    ".rs",
    ".swift",
    ".kt",
    ".kts",
    ".rb",
    ".sh",
    ".csv",
    ".sql",
    ".toml",
    # C# / .NET
    ".cs",
    ".csproj",
    ".sln",
    ".razor",
    ".cshtml",
} | PHP_EXTENSIONS

SKIP_FILENAMES = {
    "entities.json",
    "mempalace.yaml",
    "mempalace.yml",
    "mempal.yaml",
    "mempal.yml",
    ".gitignore",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
}

DRAWER_UPSERT_BATCH_SIZE = 1000
# 500 MB — skip files larger than this.
MAX_FILE_SIZE = 500 * 1024 * 1024

# A safety rail against pathological generated artifacts (lockfiles not in
# SKIP_FILENAMES, vendored data dumps, etc.). Originally 500 to bound ONNX
# runtime `bad allocation` errors on Windows (#1296), but at CHUNK_SIZE=800
# that capped legitimate long-form content (#1455: full-text scholarly
# editions, novels) at ~400 KB. The new default leaves two orders of
# magnitude of safety margin against the original lockfile case
# (~1124 chunks for `pnpm-lock.yaml` per #1296) while not touching
# hand-written prose. Per-ONNX-call exposure is bounded by
# `DRAWER_UPSERT_BATCH_SIZE` (1000 chunks/batch) regardless of this cap,
# so the cap is a per-file admission rail, not a per-batch limit. Lower
# this via `MEMPALACE_MAX_CHUNKS_PER_FILE` or
# `mempalace mine --max-chunks-per-file N` if you hit ONNX bad_alloc on
# Windows; set to 0 to disable the cap entirely.
MAX_CHUNKS_PER_FILE = 50_000


def _path_within_root(path: Path, root: Path) -> bool:
    try:
        path.expanduser().resolve().relative_to(root.expanduser().resolve())
        return True
    except (OSError, ValueError):
        return False


def _read_text_no_follow(filepath: Path, root: Path) -> Optional[str]:
    if not _path_within_root(filepath, root):
        return None
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = -1
    try:
        fd = os.open(filepath, flags)
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_FILE_SIZE:
            return None
        with os.fdopen(fd, "r", encoding="utf-8", errors="replace") as f:
            fd = -1
            return f.read()
    except OSError:
        return None
    finally:
        if fd != -1:
            try:
                os.close(fd)
            except OSError:
                pass


def _resolve_max_chunks_per_file(override: Optional[int] = None) -> int:
    """Resolve the effective per-file chunk cap.

    Precedence: ``override`` (CLI flag) > ``MEMPALACE_MAX_CHUNKS_PER_FILE``
    env var > module-level ``MAX_CHUNKS_PER_FILE`` default. A sentinel
    value of ``0`` (from any source) disables the cap entirely. Negative
    values from either source emit a stderr warning and fall back to the
    module default so a misconfigured ``--max-chunks-per-file=-500`` typo
    (meaning "no, don't lower it that much") does not silently disable
    the cap and OOM on a generated artifact.
    """
    if override is not None:
        if override < 0:
            print(
                f"  ! WARNING: --max-chunks-per-file={override} is negative; "
                f"using default {MAX_CHUNKS_PER_FILE}",
                file=sys.stderr,
            )
            return MAX_CHUNKS_PER_FILE
        return override
    raw = os.environ.get("MEMPALACE_MAX_CHUNKS_PER_FILE")
    if raw is None:
        return MAX_CHUNKS_PER_FILE
    try:
        val = int(raw)
    except ValueError:
        print(
            f"  ! WARNING: MEMPALACE_MAX_CHUNKS_PER_FILE={raw!r} is not an integer; "
            f"using default {MAX_CHUNKS_PER_FILE}",
            file=sys.stderr,
        )
        return MAX_CHUNKS_PER_FILE
    if val < 0:
        print(
            f"  ! WARNING: MEMPALACE_MAX_CHUNKS_PER_FILE={val} is negative; "
            f"using default {MAX_CHUNKS_PER_FILE}",
            file=sys.stderr,
        )
        return MAX_CHUNKS_PER_FILE
    return val
