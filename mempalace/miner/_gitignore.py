"""Gitignore — .gitignore matching for the miner.

Wing: miner | Topic: gitignore | Updated: 2026-06-28 18:30
"""

import fnmatch
from pathlib import Path
from typing import Optional

from ..palace import SKIP_DIRS


class GitignoreMatcher:
    """Lightweight matcher for one directory's .gitignore patterns."""

    def __init__(self, base_dir: Path, rules: list):
        self.base_dir = base_dir
        self.rules = rules

    @classmethod
    def from_dir(cls, dir_path: Path):
        gitignore_path = dir_path / ".gitignore"
        if not gitignore_path.is_file():
            return None

        try:
            lines = gitignore_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            return None

        rules = []
        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue

            if line.startswith("\\#") or line.startswith("\\!"):
                line = line[1:]
            elif line.startswith("#"):
                continue

            negated = line.startswith("!")
            if negated:
                line = line[1:]

            anchored = line.startswith("/")
            if anchored:
                line = line.lstrip("/")

            dir_only = line.endswith("/")
            if dir_only:
                line = line.rstrip("/")

            if not line:
                continue

            rules.append(
                {
                    "pattern": line,
                    "anchored": anchored,
                    "dir_only": dir_only,
                    "negated": negated,
                }
            )

        if not rules:
            return None

        return cls(dir_path, rules)

    def matches(self, path: Path, is_dir: Optional[bool] = None):
        try:
            relative = path.relative_to(self.base_dir).as_posix().strip("/")
        except ValueError:
            return None

        if not relative:
            return None

        if is_dir is None:
            is_dir = path.is_dir()

        ignored = None
        for rule in self.rules:
            if self._rule_matches(rule, relative, is_dir):
                ignored = not rule["negated"]
        return ignored

    def _rule_matches(self, rule: dict, relative: str, is_dir: bool) -> bool:
        pattern = rule["pattern"]
        parts = relative.split("/")
        pattern_parts = pattern.split("/")

        if rule["dir_only"]:
            target_parts = parts if is_dir else parts[:-1]
            if not target_parts:
                return False
            if rule["anchored"] or len(pattern_parts) > 1:
                return self._match_from_root(target_parts, pattern_parts)
            return any(fnmatch.fnmatch(part, pattern) for part in target_parts)

        if rule["anchored"] or len(pattern_parts) > 1:
            return self._match_from_root(parts, pattern_parts)

        return any(fnmatch.fnmatch(part, pattern) for part in parts)

    def _match_from_root(self, target_parts: list, pattern_parts: list) -> bool:
        def matches(path_index: int, pattern_index: int) -> bool:
            if pattern_index == len(pattern_parts):
                return True

            if path_index == len(target_parts):
                return all(part == "**" for part in pattern_parts[pattern_index:])

            pattern_part = pattern_parts[pattern_index]
            if pattern_part == "**":
                return matches(path_index, pattern_index + 1) or matches(
                    path_index + 1, pattern_index
                )

            if not fnmatch.fnmatch(target_parts[path_index], pattern_part):
                return False

            return matches(path_index + 1, pattern_index + 1)

        return matches(0, 0)


def load_gitignore_matcher(dir_path: Path, cache: dict):
    """Load and cache one directory's .gitignore matcher."""
    if dir_path not in cache:
        cache[dir_path] = GitignoreMatcher.from_dir(dir_path)
    return cache[dir_path]


def is_gitignored(path: Path, matchers: list, is_dir: bool = False) -> bool:
    """Apply active .gitignore matchers in ancestor order; last match wins."""
    ignored = False
    for matcher in matchers:
        decision = matcher.matches(path, is_dir=is_dir)
        if decision is not None:
            ignored = decision
    return ignored


def should_skip_dir(dirname: str) -> bool:
    """Skip known generated/cache directories before gitignore matching."""
    return dirname in SKIP_DIRS or dirname.endswith(".egg-info")


def normalize_include_paths(include_ignored: Optional[list] = None) -> set:
    """Normalize comma-parsed include paths into project-relative POSIX strings."""
    normalized = set()
    for raw_path in include_ignored or []:
        candidate = str(raw_path).strip().strip("/")
        if candidate:
            normalized.add(Path(candidate).as_posix())
    return normalized


def is_exact_force_include(path: Path, project_path: Path, include_paths: set) -> bool:
    """Return True when a path exactly matches an explicit include override."""
    if not include_paths:
        return False

    try:
        relative = path.relative_to(project_path).as_posix().strip("/")
    except ValueError:
        return False

    return relative in include_paths


def is_force_included(path: Path, project_path: Path, include_paths: set) -> bool:
    """Return True when a path or one of its ancestors/descendants was explicitly included."""
    if not include_paths:
        return False

    try:
        relative = path.relative_to(project_path).as_posix().strip("/")
    except ValueError:
        return False

    if not relative:
        return False

    for include_path in include_paths:
        if relative == include_path:
            return True
        if relative.startswith(f"{include_path}/"):
            return True
        if include_path.startswith(f"{relative}/"):
            return True

    return False
