"""Dates — content-date extraction for the miner (Tier 6a).

Wing: miner | Topic: dates | Updated: 2026-06-28 18:30
"""

import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional


# Tier 6a content-date extraction
#
# Hierarchy (first match wins):
#   1. Filename — ISO regex on stem, then dateutil fuzzy parse for natural-
#      language formats (handles "April-6th-2011-notes", "Nov-8-2024", etc.)
#   2. YAML frontmatter — date / created / published field
#   3. Content body, first ~10 lines:
#        a. ISO regex (YYYY-MM-DD / YYYY/MM/DD / YYYY.MM.DD)
#        b. Slash dates with locale auto-disambiguation
#           (if any day > 12 appears in the file, lock locale to DD/MM)
#        c. dateutil fuzzy parse for natural-language ("November 8, 2024",
#           "April 6th 2011", "8 Nov 2024", etc.)
#   4. Filesystem mtime (os.path.getmtime)
#   5. None — caller falls back to filed_at
#
# The "approximate locator" philosophy applies: this is a metadata enrichment
# that makes closet pointers honest for content with embedded dates, NOT a
# bulletproof timeline-reconstruction tool. Files with no date markers
# anywhere and no filesystem mtime return None (caller uses filed_at).

_ORDINAL_SUFFIX_RE = re.compile(r"\b(\d+)(st|nd|rd|th)\b", re.IGNORECASE)
_ISO_DATE_RE = re.compile(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b")
_SLASH_DATE_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b")

# Gate for dateutil fallback. A candidate string must match ONE of these
# patterns to be considered a real date — otherwise dateutil's fuzzy mode
# would hallucinate dates from any digit-bearing text (Igor's reproductions
# on PR #1584: "tmp_random_file_5" → 2026-05-05, "Version 3.3.6" → 2006-03-03,
# "Tested with 1000 drawers" → 1000-05-22, etc.). The fuzzy=True flag is
# never set — dateutil only runs in strict mode on a substring we've
# already validated.
#
# Three accepted shapes (all require a 4-digit year explicitly):
#   1. Numeric: 4-digit year + separator + 1-2 digit month + separator + 1-2 digit day
#      ("2024-11-08", "2024 11 08", "2024/06/15", "2024.11.08")
#   2. Month-name + day + year: "November 8 2024", "Nov 8 2024", "Apr 6 2011"
#   3. Day + month-name + year: "8 November 2024", "8 Nov 2024", "6 April 2011"
#
# Partial dates ("2024-06", "notes.2024", "Nov 8", "April 6") are
# DELIBERATELY rejected — without all three components we'd fall back to
# padding from today's date, which is hallucination, not extraction.
_MONTH_NAME = (
    r"(?:january|february|march|april|may|june|july|august|"
    r"september|october|november|december|"
    r"jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)"
)
_VALID_DATE_RE = re.compile(
    r"(?:"
    # Shape 1: YYYY sep MM sep DD (sep = - / . or whitespace)
    r"\b\d{4}[-/.\s]+\d{1,2}[-/.\s]+\d{1,2}\b"
    r"|"
    # Shape 2: month-name + day + year
    r"\b" + _MONTH_NAME + r"\.?[-\s]+\d{1,2}(?:st|nd|rd|th)?[,\s-]+\d{4}\b"
    r"|"
    # Shape 3: day + month-name + year
    r"\b\d{1,2}(?:st|nd|rd|th)?[-\s]+" + _MONTH_NAME + r"\.?[,\s-]+\d{4}\b"
    r")",
    re.IGNORECASE,
)


def _try_iso_match(text: str) -> Optional[str]:
    """Try to extract YYYY-MM-DD from text via the ISO regex. Returns ISO string or None."""
    m = _ISO_DATE_RE.search(text)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
    except (ValueError, TypeError):
        return None


def _try_filename_date(source_file: str) -> Optional[str]:
    """Extract date from filename stem.

    ISO regex first (catches the canonical ``2024-11-08*`` diary pattern).
    Then a strict regex gate (``_VALID_DATE_RE``) screens for complete
    natural-language dates before invoking dateutil. ``fuzzy=True`` is
    NOT used — it hallucinates dates on any digit-bearing input. Junk
    filenames like ``tmp_random_file_5`` or ``notes.2024`` return None
    so the caller falls through to frontmatter / content / mtime.
    """
    try:
        stem = Path(source_file).stem
    except (TypeError, ValueError):
        return None
    if not stem:
        return None

    # ISO direct: "2024-11-08", "2024-11-08-notes", etc.
    iso = _try_iso_match(stem)
    if iso:
        return iso

    # Natural language: "April-6th-2011-notes", "Nov-8-2024", etc.
    # Preprocess: strip ordinals, dashes/underscores -> spaces.
    normalized = _ORDINAL_SUFFIX_RE.sub(r"\1", stem).replace("-", " ").replace("_", " ")

    # Gate: require a complete date pattern. Without this, dateutil would
    # accept any digit-bearing junk and fabricate a date.
    m = _VALID_DATE_RE.search(normalized)
    if not m:
        return None

    try:
        from dateutil import parser as dateutil_parser

        # Parse the matched substring only, no fuzzy mode.
        dt = dateutil_parser.parse(m.group(0))
        return dt.strftime("%Y-%m-%d")
    except (ValueError, OverflowError, ImportError):
        return None
    except Exception:
        # dateutil can raise unexpected exceptions on weird input; treat as no match.
        return None


def _try_frontmatter_date(content: str) -> Optional[str]:
    """Extract date from YAML frontmatter date / created / published field.

    Uses ``str.find`` to locate the closing ``\\n---`` delimiter and slices
    the frontmatter directly. The earlier implementation split the entire
    file into lines just to scan the first handful — wasteful on large
    files. Per PR #1579 review (gemini-code-assist, medium priority).
    """
    if not content:
        return None
    stripped = content.lstrip()
    if not stripped.startswith("---"):
        return None

    # Locate the closing "\n---" without materializing a line-list.
    end_pos = stripped.find("\n---", 3)
    if end_pos == -1:
        return None

    frontmatter_text = stripped[3:end_pos].strip()
    if not frontmatter_text:
        return None

    try:
        import yaml

        data = yaml.safe_load(frontmatter_text)
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    for field in ("date", "created", "published"):
        value = data.get(field)
        if value is None:
            continue
        # yaml.safe_load may parse ISO dates as datetime.date/datetime objects directly.
        if hasattr(value, "strftime"):
            return value.strftime("%Y-%m-%d")
        # Otherwise parse via dateutil.
        try:
            from dateutil import parser as dateutil_parser

            dt = dateutil_parser.parse(str(value))
            return dt.strftime("%Y-%m-%d")
        except (ValueError, OverflowError, ImportError):
            continue
        except Exception:
            continue
    return None


def _try_content_body_date(content: str) -> Optional[str]:
    """Scan first ~10 lines of content body for a date.

    Order within the scan:
      1. ISO regex (highest signal)
      2. Slash dates with locale auto-disambiguation (DD/MM vs MM/DD)
      3. dateutil fuzzy for natural-language ("November 8, 2024" etc.)

    Uses ``str.find`` to skip frontmatter and bounded ``str.split(..., 10)``
    to bound the head extraction — never materializes a full line-list on a
    large file. Per PR #1579 review (gemini-code-assist, medium priority).
    """
    if not content:
        return None

    stripped = content.lstrip()

    # Skip frontmatter if present, using ``find`` instead of full split.
    if stripped.startswith("---"):
        end_fm = stripped.find("\n---", 3)
        if end_fm != -1:
            eol = stripped.find("\n", end_fm + 1)
            if eol != -1:
                stripped = stripped[eol + 1:]

    # Bounded split — maxsplit=10 caps the work to 10 newline scans rather
    # than splitting the entire file just to look at the first 10 lines.
    head = "\n".join(stripped.split("\n", 10)[:10])
    if not head:
        return None

    # 1. ISO regex — explicit, highest confidence.
    iso = _try_iso_match(head)
    if iso:
        return iso

    # 2. Slash dates with locale auto-disambiguation.
    slash_matches = _SLASH_DATE_RE.findall(head)
    if slash_matches:
        # If any first-number > 12, the locale MUST be DD/MM (otherwise that
        # number couldn't be a month). Lock it for ALL dates in this file.
        try:
            is_dd_mm = any(int(m[0]) > 12 for m in slash_matches)
            first = slash_matches[0]
            a, b, y = int(first[0]), int(first[1]), int(first[2])
            if y < 100:
                # Two-digit year — stdlib convention: 70-99 -> 19xx, 00-69 -> 20xx.
                y = 1900 + y if y >= 70 else 2000 + y
            try:
                if is_dd_mm:
                    return date(y, b, a).isoformat()
                return date(y, a, b).isoformat()
            except (ValueError, TypeError):
                pass  # Fall through to dateutil fuzzy.
        except (ValueError, TypeError):
            pass  # Fall through to dateutil fuzzy.

    # 3. dateutil natural-language fallback. Strict regex gate first
    # (no fuzzy=True) — without it, dateutil hallucinates dates from any
    # digit-bearing text. The gate requires a complete year+month+day
    # pattern OR a month-name + day + year combination.
    m = _VALID_DATE_RE.search(head)
    if not m:
        return None
    try:
        from dateutil import parser as dateutil_parser

        dt = dateutil_parser.parse(m.group(0))
        return dt.strftime("%Y-%m-%d")
    except (ValueError, OverflowError, ImportError):
        return None
    except Exception:
        return None


def _try_mtime_date(source_file: str) -> Optional[str]:
    """Filesystem mtime -> ISO date."""
    try:
        mtime = os.path.getmtime(source_file)
    except (OSError, TypeError):
        return None
    try:
        return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
    except (OSError, ValueError, OverflowError):
        return None


def _extract_content_date(source_file: str, content: str) -> Optional[str]:
    """Extract a content date from source_file or content.

    Returns ISO 'YYYY-MM-DD' string, or None if no date can be determined.
    See module-level comment block for the full hierarchy + design rationale.
    """
    # 1. Filename
    result = _try_filename_date(source_file)
    if result:
        return result

    # 2. YAML frontmatter
    result = _try_frontmatter_date(content)
    if result:
        return result

    # 3. Content body
    result = _try_content_body_date(content)
    if result:
        return result

    # 4. Filesystem mtime
    result = _try_mtime_date(source_file)
    if result:
        return result

    # 5. Nothing found — caller falls back to filed_at.
    return None
