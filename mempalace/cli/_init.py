"""_init — `mempalace init` subcommand + corpus-origin detection.

Wing: mempalace | Topic: cli | Updated: 2026-06-28
"""

import os
import sys
import json
import shlex
from datetime import datetime, timezone
from pathlib import Path

from ..config import MempalaceConfig
from ..corpus_origin import detect_origin_heuristic, detect_origin_llm
from ..llm_client import LLMError, get_provider


_MEMPALACE_PROJECT_FILES = ("mempalace.yaml", "entities.json")

_PASS_ZERO_MAX_FILES = 30
_PASS_ZERO_PER_FILE_CAP = 100_000
_PASS_ZERO_TOTAL_CAP = 5_000_000
_PASS_ZERO_LLM_PER_SAMPLE = 2_000
_PASS_ZERO_LLM_MAX_SAMPLES = 20

_EXPLICIT_BACKEND_ENV = "MEMPALACE_BACKEND_EXPLICIT"


# ── Shared helpers imported by _main.py ────────────────────────────────────
# (defined here but also importable from __init__)


def _backend_arg(args):
    """Return a CLI-selected backend from subcommand or global flags."""
    return getattr(args, "backend", None) or getattr(args, "global_backend", None)


# ── Pass 0 helpers ────────────────────────────────────────────────────────


def _gather_origin_samples(project_dir) -> list:
    """Collect Tier-1 samples for corpus-origin detection.

    Reads FULL file content (capped at ``_PASS_ZERO_PER_FILE_CAP`` per file
    and ``_PASS_ZERO_TOTAL_CAP`` overall). No front-bias sampling — AI
    signal that lives past the first N chars of a file must still trip
    detection, so we read the whole file up to the cap.

    Skips mempalace's own per-project artifacts (``entities.json``,
    ``mempalace.yaml``) so a re-run of ``mempalace init`` produces the
    same classification result it did on the first run. Without this
    filter, the first run writes entities.json into the corpus, the
    second run picks it up as a sample, and the Tier-1 density math
    drifts (different total_chars). That makes init non-idempotent.

    Returns a list of strings (one per readable file). Empty list when
    the project has no readable text.
    """
    from ..entity_detector import scan_for_detection

    files = scan_for_detection(project_dir, max_files=_PASS_ZERO_MAX_FILES)
    samples: list = []
    total_chars = 0
    for filepath in files:
        if filepath.name in _MEMPALACE_PROJECT_FILES:
            continue
        if total_chars >= _PASS_ZERO_TOTAL_CAP:
            break
        try:
            with open(filepath, encoding="utf-8", errors="replace") as f:
                content = f.read(_PASS_ZERO_PER_FILE_CAP)
        except OSError:
            continue
        if not content:
            continue
        samples.append(content)
        total_chars += len(content)
    return samples


def _trim_samples_for_llm(samples: list) -> list:
    """Reduce Tier-1 full-content samples to LLM-friendly size.

    Tier 2 hits an LLM with a finite context window — we trim each sample
    to ``_PASS_ZERO_LLM_PER_SAMPLE`` chars and cap the overall sample
    count at ``_PASS_ZERO_LLM_MAX_SAMPLES``.
    """
    return [s[:_PASS_ZERO_LLM_PER_SAMPLE] for s in samples[:_PASS_ZERO_LLM_MAX_SAMPLES]]


def _run_pass_zero(project_dir, palace_dir, llm_provider) -> dict | None:
    """Pass 0: detect whether the corpus is AI-dialogue and persist the
    result to ``<palace>/.mempalace/origin.json``.

    Returns the wrapped result dict (same shape as origin.json) on success,
    or ``None`` when there are no readable samples to detect from. The
    return value is what cmd_init forwards to ``discover_entities`` via
    the ``corpus_origin`` kwarg.

    File-write failures (e.g. read-only palace) are caught and reported on
    stderr; init never blocks on them.
    """
    samples = _gather_origin_samples(project_dir)
    if not samples:
        print("  Skipping corpus-origin detection — no readable samples.")
        return None

    # Tier 1 — always runs. Cheap regex grep, no API.
    result = detect_origin_heuristic(samples)

    # Tier 2 — runs only when an LLM provider is available.
    if llm_provider is not None:
        try:
            llm_result = detect_origin_llm(_trim_samples_for_llm(samples), llm_provider)
            if llm_result.primary_platform:
                result.primary_platform = llm_result.primary_platform
            if llm_result.user_name:
                result.user_name = llm_result.user_name
            if llm_result.agent_persona_names:
                result.agent_persona_names = list(llm_result.agent_persona_names)
            tier1_prefix = "Tier-1 heuristic: "
            tier2_prefix = "Tier-2 LLM: "
            heuristic_evidence = [
                s if s.startswith(tier1_prefix) else f"{tier1_prefix}{s}"
                for s in (str(e) for e in result.evidence)
            ]
            llm_evidence = [
                s if s.startswith(tier2_prefix) else f"{tier2_prefix}{s}"
                for s in (str(e) for e in llm_result.evidence)
            ]
            result.evidence = heuristic_evidence + llm_evidence
        except Exception as exc:  # noqa: BLE001 — never block init on LLM failure
            print(f"  LLM corpus-origin tier failed ({exc}); using heuristic only.")

    wrapped = {
        "schema_version": 1,
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "result": result.to_dict(),
    }

    origin_path = Path(palace_dir).expanduser() / ".mempalace" / "origin.json"
    try:
        origin_path.parent.mkdir(parents=True, exist_ok=True)
        with open(origin_path, "w", encoding="utf-8") as f:
            json.dump(wrapped, f, indent=2, ensure_ascii=False)
    except OSError as exc:
        print(f"  Could not write {origin_path}: {exc}", file=sys.stderr)
        return wrapped

    res = result
    if res.likely_ai_dialogue:
        platform = res.primary_platform or "AI dialogue (platform unidentified)"
        user = res.user_name or "—"
        agents = ", ".join(res.agent_persona_names) if res.agent_persona_names else "—"
        print(f"  Detected: {platform} (user: {user}, agents: {agents})")
    else:
        print(f"  Corpus origin: not AI-dialogue (confidence: {res.confidence:.2f})")

    return wrapped


def _ensure_mempalace_files_gitignored(project_dir) -> bool:
    """If project_dir is a git repo, ensure MemPalace's per-project files
    are listed in .gitignore so they don't get committed by accident.

    Returns True if .gitignore was updated, False otherwise. Issue #185:
    ``mempalace init`` writes mempalace.yaml + entities.json into the
    project root, where they previously had no protection against being
    staged into git.
    """
    project_path = Path(project_dir).expanduser().resolve()
    if not (project_path / ".git").exists():
        return False
    gitignore = project_path / ".gitignore"
    existing = gitignore.read_text() if gitignore.exists() else ""
    existing_lines = {line.strip() for line in existing.splitlines()}
    missing = [p for p in _MEMPALACE_PROJECT_FILES if p not in existing_lines]
    if not missing:
        return False
    prefix = "" if not existing or existing.endswith("\n") else "\n"
    block = prefix + "\n# MemPalace per-project files (issue #185)\n" + "\n".join(missing) + "\n"
    with open(gitignore, "a", encoding="utf-8") as f:
        f.write(block)
    print(f"  Added {', '.join(missing)} to {gitignore.name}")
    return True


def _format_size_mb(num_bytes: int) -> str:
    """Render a byte count as a human-readable size for the mine estimate.

    < 1 MB rounds up to ``<1 MB`` so users never see a misleading ``0 MB``
    on small projects. Otherwise reports an integer megabyte count.
    """
    if num_bytes <= 0:
        return "<1 MB"
    mb = num_bytes / (1024 * 1024)
    if mb < 1:
        return "<1 MB"
    return f"{mb:.0f} MB"


def _maybe_run_mine_after_init(args, cfg) -> None:
    """Prompt the user to mine the directory just initialised, or auto-mine
    when ``--auto-mine`` was passed. Extracted so the prompt path is
    unit-testable.

    Behaviour matrix:

    - default (no flags) — prompt, default Yes, mine in-process if accepted
    - ``--yes`` — entity auto-accept only; STILL prompts for the mine step
    - ``--auto-mine`` — skip the mine prompt and mine directly
    - ``--yes --auto-mine`` — fully non-interactive

    Mine errors are surfaced (not swallowed): a failing mine exits with a
    non-zero status via :func:`sys.exit` so downstream scripts can see it.
    The pre-scan that produces the file-count estimate is reused as the
    mine input so we never walk the corpus twice.
    """
    from ..miner import mine, scan_project

    project_dir = args.dir
    auto_mine = bool(getattr(args, "auto_mine", False))

    try:
        scanned_files = scan_project(project_dir)
        file_count = len(scanned_files)
        total_bytes = 0
        for fp in scanned_files:
            try:
                total_bytes += fp.stat().st_size
            except OSError:
                continue
        size_str = _format_size_mb(total_bytes)
    except Exception:
        scanned_files = None
        file_count = None
        size_str = None

    if isinstance(file_count, int):
        if size_str:
            print(f"  ~{file_count} files (~{size_str}) would be mined into this palace.\n")
        else:
            print(f"  ~{file_count} files would be mined into this palace.\n")

    if not auto_mine:
        try:
            answer = input("  Mine this directory now? [Y/n] ").strip().lower()
        except EOFError:
            answer = "n"
        if answer not in ("", "y", "yes"):
            print(f"\n  Skipped. Run `mempalace mine {shlex.quote(project_dir)}` when ready.")
            return

    palace_path = cfg.palace_path
    if scanned_files is None:
        print("  Skipping mine — could not scan project directory.", file=sys.stderr)
        return
    try:
        mine(
            project_dir=project_dir,
            palace_path=palace_path,
            files=scanned_files,
        )
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(f"\n  ERROR: mine failed: {e}", file=sys.stderr)
        sys.exit(1)


# ── Command ───────────────────────────────────────────────────────────────


def cmd_init(args):
    """Run `mempalace init <dir>` — set up a palace for a project."""
    import json
    from pathlib import Path
    from ..entity_detector import confirm_entities
    from ..project_scanner import discover_entities
    from ..room_detector_local import detect_rooms_local

    if getattr(args, "palace", None):
        os.environ["MEMPALACE_PALACE_PATH"] = os.path.abspath(os.path.expanduser(args.palace))

    cfg = MempalaceConfig()

    lang_arg = getattr(args, "lang", None)
    if lang_arg:
        languages = [s.strip() for s in lang_arg.split(",") if s.strip()] or ["en"]
        cfg.set_entity_languages(languages)
    else:
        languages = cfg.entity_languages
    languages_tuple = tuple(languages)

    llm_provider = None
    if not getattr(args, "no_llm", False):
        provider_name = getattr(args, "llm_provider", "ollama") or "ollama"
        provider_model = getattr(args, "llm_model", "gemma4:e4b") or "gemma4:e4b"
        try:
            candidate = get_provider(
                name=provider_name,
                model=provider_model,
                endpoint=getattr(args, "llm_endpoint", None),
                api_key=getattr(args, "llm_api_key", None),
            )
            if (
                provider_name == "openai-compat"
                and getattr(candidate, "api_key_source", None) == "env"
                and candidate.is_external_service
            ):
                ok = False
                msg = "external openai-compat init requires explicit --llm-api-key"
                print(f"  LLM skipped: {msg}")
            else:
                ok, msg = candidate.check_available()
            if ok:
                llm_provider = candidate
                print(f"  LLM enabled: {provider_name}/{provider_model}")
                if candidate.is_external_service:
                    print(
                        f"  ⚠ {provider_name} is an EXTERNAL API. Your folder "
                        f"content will be sent to the provider during init. "
                        f"MemPalace does not control how the provider logs, "
                        f"retains, or uses your data. Pass --no-llm to keep "
                        f"init fully local."
                    )
                    api_key_source = getattr(candidate, "api_key_source", None)
                    accept_flag = getattr(args, "accept_external_llm", False)
                    if api_key_source == "env" and not accept_flag:
                        try:
                            answer = (
                                input(
                                    "  Your API key was loaded from the environment "
                                    "(not passed via --llm-api-key). Continue with "
                                    "external LLM? [y/N] "
                                )
                                .strip()
                                .lower()
                            )
                        except (EOFError, OSError):
                            answer = ""
                        if answer != "y":
                            print(
                                "  Declined — falling back to heuristics-only. "
                                "Pass --llm-api-key explicitly or "
                                "--accept-external-llm to skip this prompt."
                            )
                            llm_provider = None
            else:
                print(
                    f"  No LLM provider reachable ({msg}). "
                    f"Running heuristics-only — pass --no-llm to silence this."
                )
        except LLMError as e:
            print(
                f"  LLM init failed ({e}). Running heuristics-only — pass --no-llm to silence this."
            )

    corpus_origin = _run_pass_zero(
        project_dir=args.dir,
        palace_dir=cfg.palace_path,
        llm_provider=llm_provider,
    )

    print(f"\n  Scanning for entities in: {args.dir}")
    if languages_tuple != ("en",):
        print(f"  Languages: {', '.join(languages_tuple)}")
    detected = discover_entities(
        args.dir,
        languages=languages_tuple,
        llm_provider=llm_provider,
        corpus_origin=corpus_origin,
    )
    total = (
        len(detected["people"])
        + len(detected["projects"])
        + len(detected.get("topics", []))
        + len(detected["uncertain"])
    )
    if total > 0:
        confirmed = confirm_entities(detected, yes=getattr(args, "yes", False))
        if confirmed["people"] or confirmed["projects"] or confirmed.get("topics"):
            project_path = Path(args.dir).expanduser().resolve()
            entities_path = project_path / "entities.json"
            try:
                with open(entities_path, "w", encoding="utf-8") as f:
                    json.dump(confirmed, f, indent=2, ensure_ascii=False)
                print(f"  Entities saved: {entities_path}")
            except OSError as exc:
                print(f"  Could not write {entities_path}: {exc}", file=sys.stderr)

            from ..config import normalize_wing_name
            from ..miner import add_to_known_entities

            wing = normalize_wing_name(project_path.name)
            registry_path = add_to_known_entities(confirmed, wing=wing)
            print(f"  Registry updated: {registry_path}")
    else:
        print("  No entities detected — proceeding with directory-based rooms.")

    detect_rooms_local(project_dir=args.dir, yes=getattr(args, "yes", False))
    cfg.init()
    backend = _backend_arg(args)
    if backend:
        cfg.set_backend(backend)

    _ensure_mempalace_files_gitignored(args.dir)
    _maybe_run_mine_after_init(args, cfg)
