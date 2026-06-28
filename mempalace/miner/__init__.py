"""miner package — files everything into the palace.

Reads mempalace.yaml from the project directory to know the wing + rooms.
Routes each file to the right room based on content.
Stores verbatim chunks as drawers. No summaries. Ever.

Wing: miner | Topic: package | Updated: 2026-06-28 18:30
"""

# Re-export everything so external callers using ``from mempalace.miner import X``
# keep working after the file-to-package split.

from ._chunking import CHUNK_SIZE, CHUNK_OVERLAP, MIN_CHUNK_SIZE, chunk_text
from ._config import load_config
from ._dates import (
    _extract_content_date,
    _try_content_body_date,
    _try_filename_date,
    _try_frontmatter_date,
    _try_iso_match,
    _try_mtime_date,
    _ISO_DATE_RE,
    _MONTH_NAME,
    _ORDINAL_SUFFIX_RE,
    _SLASH_DATE_RE,
    _VALID_DATE_RE,
)
from ._drawers import _HALL_KEYWORDS_CACHE, _build_drawer_metadata, add_drawer, detect_hall
from ._entities import (
    _ENTITY_EXTRACT_WINDOW,
    _ENTITY_METADATA_LIMIT,
    _ENTITY_REGISTRY_CACHE,
    _ENTITY_REGISTRY_PATH,
    _extract_entities_for_metadata,
    _load_known_entities,
    _load_known_entities_raw,
    _refresh_known_entities_cache,
    _set_wing_topics,
    add_to_known_entities,
    get_topics_by_wing,
)
from ._gitignore import (
    GitignoreMatcher,
    is_exact_force_include,
    is_force_included,
    is_gitignored,
    load_gitignore_matcher,
    normalize_include_paths,
    should_skip_dir,
)
from ._mine import (
    _cleanup_mine_pid_file,
    _compute_entity_tunnels_for_wing,
    _compute_topic_tunnels_for_wing,
    _mine_impl,
    mine,
)
from ._processing import process_file, scan_project
from ._readable import (
    DRAWER_UPSERT_BATCH_SIZE,
    MAX_CHUNKS_PER_FILE,
    MAX_FILE_SIZE,
    PHP_EXTENSIONS,
    READABLE_EXTENSIONS,
    SKIP_FILENAMES,
    _path_within_root,
    _read_text_no_follow,
    _resolve_max_chunks_per_file,
)
from ._rooms import _name_matches, _tokens, detect_room
from ._status import _print_status, status
