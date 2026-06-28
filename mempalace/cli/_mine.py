"""_mine — `mempalace mine`, `sweep`, `sync`, `daemon` subcommands.

Wing: mempalace | Topic: cli | Updated: 2026-06-28
"""

import os
import sys

from ..config import MempalaceConfig


_EXPLICIT_BACKEND_ENV = "MEMPALACE_BACKEND_EXPLICIT"


def _backend_arg(args):
    """Return a CLI-selected backend from subcommand or global flags."""
    return getattr(args, "backend", None) or getattr(args, "global_backend", None)


def _submit_daemon_cli_job(kind: str, payload: dict, args, *, background: bool) -> None:
    """Submit a job to the local daemon queue and optionally wait for it."""
    palace_path = os.path.expanduser(args.palace) if args.palace else MempalaceConfig().palace_path
    backend = _backend_arg(args)
    from ..daemon import DaemonError, submit_job

    try:
        job = submit_job(
            kind,
            payload,
            palace_path=palace_path,
            backend=backend,
            wait=not background,
            auto_start=True,
        )
    except DaemonError as exc:
        print(f"mempalace: daemon submission failed: {exc}", file=sys.stderr)
        sys.exit(1)

    if background:
        print(f"Submitted daemon job {job['id']} ({kind})")
        return

    result = job.get("result") or {}
    from ..service import print_job_result

    exit_code = print_job_result(result)
    if job.get("state") != "succeeded" and exit_code == 0:
        error = job.get("error") or {}
        print(
            f"mempalace: daemon job failed: {error.get('message', 'unknown error')}",
            file=sys.stderr,
        )
        exit_code = 1
    if exit_code:
        sys.exit(exit_code)


# ── Commands ──────────────────────────────────────────────────────────────


def cmd_mine(args):
    """Run `mempalace mine <dir>` — mine files into the palace."""
    palace_path = os.path.expanduser(args.palace) if args.palace else MempalaceConfig().palace_path
    include_ignored = []
    for raw in args.include_ignored or []:
        include_ignored.extend(part.strip() for part in raw.split(",") if part.strip())

    if getattr(args, "background", False) and not getattr(args, "daemon", False):
        print("mempalace: --background requires --daemon", file=sys.stderr)
        sys.exit(2)

    if getattr(args, "daemon", False):
        payload = {
            "source": args.dir,
            "mode": args.mode,
            "wing": args.wing,
            "agent": args.agent,
            "limit": args.limit,
            "dry_run": args.dry_run,
            "extract": args.extract,
            "no_gitignore": args.no_gitignore,
            "include_ignored": include_ignored,
            "max_chunks_per_file": getattr(args, "max_chunks_per_file", None),
            "redetect_origin": getattr(args, "redetect_origin", False),
        }
        _submit_daemon_cli_job("mine", payload, args, background=getattr(args, "background", False))
        return

    if getattr(args, "redetect_origin", False):
        from ._init import _run_pass_zero

        _run_pass_zero(
            project_dir=args.dir,
            palace_dir=palace_path,
            llm_provider=None,
        )

    from ..palace import MineAlreadyRunning, MineValidationError

    try:
        if args.mode == "convos":
            from ..convo_miner import mine_convos

            mine_convos(
                convo_dir=args.dir,
                palace_path=palace_path,
                wing=args.wing,
                agent=args.agent,
                limit=args.limit,
                dry_run=args.dry_run,
                extract_mode=args.extract,
            )
        elif args.mode == "extract":
            from ..format_miner import mine_formats

            mine_formats(
                format_dir=args.dir,
                palace_path=palace_path,
                wing=args.wing,
                agent=args.agent,
                limit=args.limit,
                dry_run=args.dry_run,
            )
        else:
            from ..miner import mine

            mine(
                project_dir=args.dir,
                palace_path=palace_path,
                wing_override=args.wing,
                agent=args.agent,
                limit=args.limit,
                dry_run=args.dry_run,
                respect_gitignore=not args.no_gitignore,
                include_ignored=include_ignored,
                max_chunks_per_file=getattr(args, "max_chunks_per_file", None),
            )
    except MineAlreadyRunning as exc:
        print(f"mempalace: {exc}", file=sys.stderr)
        sys.exit(1)
    except MineValidationError as exc:
        from ..repair import print_sqlite_integrity_abort

        print_sqlite_integrity_abort(exc.palace_path, list(exc.errors))
        print(
            "\n  PRAGMA quick_check after this mine reported errors (the corruption\n"
            "  may pre-date the mine itself). Drawers may still be intact for direct\n"
            "  lookup; wing-filtered or full-text search will fail until the FTS5\n"
            "  index is rebuilt. `mempalace repair --yes` rebuilds the FTS5 virtual\n"
            "  table automatically (step 6 of the recovery above).",
            file=sys.stderr,
        )
        sys.exit(1)


def cmd_sweep(args):
    """Sweep a transcript file or directory.

    The sweeper deduplicates against its own prior writes via
    deterministic drawer IDs + a timestamp cursor. It does NOT currently
    coordinate with the file-level miners (miner.py / convo_miner.py) —
    those produce char-chunked drawers without compatible message
    metadata, so running both miners may store overlapping content under
    different IDs.
    """
    from ..sweeper import sweep, sweep_directory

    palace_path = os.path.expanduser(args.palace) if args.palace else MempalaceConfig().palace_path
    target = os.path.expanduser(args.target)

    if os.path.isfile(target):
        result = sweep(target, palace_path)
        print(
            f"  Swept {target}: +{result['drawers_added']} new, "
            f"{result['drawers_already_present']} already present, "
            f"{result['drawers_skipped']} skipped (< cursor)."
        )
    elif os.path.isdir(target):
        result = sweep_directory(target, palace_path)
        print(
            f"  Swept {result['files_succeeded']}/{result['files_attempted']} "
            f"files from {target}: +{result['drawers_added']} new, "
            f"{result['drawers_already_present']} already present, "
            f"{result['drawers_skipped']} skipped (< cursor)."
        )
        failures = result.get("failures") or []
        if failures:
            print(
                f"  WARNING: {len(failures)} file(s) failed to sweep - see stderr / logs for details.",
                file=sys.stderr,
            )
            sys.exit(2)
    else:
        print(f"  ERROR: Not a file or directory: {target}", file=sys.stderr)
        sys.exit(1)


def cmd_sync(args):
    """Prune drawers whose source files are gitignored, deleted, or moved (#1252)."""
    palace_path = os.path.expanduser(args.palace) if args.palace else MempalaceConfig().palace_path

    if getattr(args, "background", False) and not getattr(args, "daemon", False):
        print("mempalace: --background requires --daemon", file=sys.stderr)
        sys.exit(2)

    if getattr(args, "daemon", False):
        payload = {
            "dir": args.dir,
            "root": list(args.root or []),
            "wing": args.wing,
            "dry_run": args.dry_run,
        }
        _submit_daemon_cli_job("sync", payload, args, background=getattr(args, "background", False))
        return

    from ..palace import MineAlreadyRunning
    from ..wal import _wal_log
    from ..backends import detect_backend_for_path
    from ..palace import _backend_artifact_label, resolve_backend_name
    from ..sync import sync_palace

    if not os.path.isdir(palace_path):
        print(f"\n  No palace found at {palace_path}")
        return
    try:
        backend_name = resolve_backend_name(palace_path)
    except Exception as exc:  # noqa: BLE001 - user-facing CLI guard
        print(f"\n  Could not resolve palace backend: {exc}", file=sys.stderr)
        return
    if detect_backend_for_path(palace_path) is None:
        print(
            f"\n  Palace dir at {palace_path} exists but has no "
            f"{_backend_artifact_label(backend_name)} yet."
        )
        print("  Run: mempalace mine <dir>")
        return

    project_dirs = []
    if args.dir:
        project_dirs.append(os.path.expanduser(args.dir))
    project_dirs.extend(os.path.expanduser(r) for r in args.root)
    project_dirs = project_dirs or None

    print(f"\n{'=' * 55}")
    print("  MemPalace Sync — Gitignore-aware drawer prune")
    print(f"{'=' * 55}")
    print(f"  Palace:   {palace_path}")
    if args.wing:
        print(f"  Wing:     {args.wing}")
    if project_dirs:
        for p in project_dirs:
            print(f"  Project:  {p}")
    if args.dry_run:
        print("  Mode:     DRY RUN (no deletions)")
    else:
        print("  Mode:     APPLY (deleting drawers)")
    print(f"{'-' * 55}\n")

    try:
        report = sync_palace(
            palace_path=palace_path,
            project_dirs=project_dirs,
            wing=args.wing,
            dry_run=args.dry_run,
            wal_log=_wal_log,
        )
    except MineAlreadyRunning as exc:
        print(f"mempalace: {exc}", file=sys.stderr)
        sys.exit(1)
    except ValueError as exc:
        print(f"mempalace: {exc}", file=sys.stderr)
        sys.exit(2)
    except Exception as exc:
        print(f"mempalace: sync failed: {exc}", file=sys.stderr)
        sys.exit(1)

    removed_suffix = "(would remove)" if args.dry_run else "(removed)"
    print(f"  Scanned:        {report['scanned']}")
    print(f"  Kept:           {report['kept']}")
    print(f"  Gitignored:     {report['gitignored']}  {removed_suffix}")
    print(f"  Missing:        {report['missing']}  {removed_suffix}")
    print(f"  No source:      {report['no_source']}  (kept)")
    print(f"  Out of scope:   {report['out_of_scope']}  (kept)")

    by_source = report.get("by_source") or {}
    if by_source:
        top = sorted(by_source.items(), key=lambda kv: -kv[1])[:5]
        label = "Top sources to remove" if args.dry_run else "Top sources removed"
        print(f"\n  {label}:")
        for src, n in top:
            print(f"    {src}  ({n})")

    if args.dry_run:
        if report["gitignored"] + report["missing"] > 0:
            print("\n  Re-run with --apply to commit these deletions.")
    else:
        print(
            f"\n  Removed {report['removed_drawers']} drawers, {report['removed_closets']} closets."
        )

    print(f"\n{'=' * 55}\n")


def cmd_daemon(args):
    """Manage the opt-in long-lived daemon."""
    palace_path = os.path.expanduser(args.palace) if args.palace else MempalaceConfig().palace_path
    backend = _backend_arg(args)
    from ..daemon import (
        TERMINAL_STATES,
        DaemonError,
        QueueStore,
        get_client_if_running,
        job_to_dict,
        queue_path,
        start_daemon,
        stop_daemon,
    )

    action = getattr(args, "daemon_action", None)
    try:
        if action == "start":
            if args.foreground:
                start_daemon(palace_path, backend=backend, foreground=True)
                return
            client = start_daemon(palace_path, backend=backend, foreground=False)
            health = client.health()
            print(f"MemPalace daemon running on 127.0.0.1:{client.port}")
            print(f"  Palace: {health.get('palace_path')}")
            print(f"  PID:    {health.get('pid')}")
            return

        if action == "stop":
            if stop_daemon(palace_path):
                print("MemPalace daemon stopping")
            else:
                print("MemPalace daemon is not running")
            return

        if action == "status":
            client = get_client_if_running(palace_path)
            if client is None:
                print("MemPalace daemon is not running")
                sys.exit(1)
            health = client.health()
            print("MemPalace daemon is running")
            print(f"  Palace: {health.get('palace_path')}")
            print(f"  PID:    {health.get('pid')}")
            print(f"  Active: {health.get('active_job_id') or '-'}")
            print(f"  Jobs:   {health.get('counts') or {}}")
            return

        if action == "jobs":
            client = get_client_if_running(palace_path)
            if client is not None:
                jobs = client.list_jobs(limit=args.limit)
            else:
                qpath = queue_path(palace_path)
                if not qpath.exists():
                    jobs = []
                else:
                    jobs = [
                        job_to_dict(job, include_payload=False)
                        for job in QueueStore(qpath).list(args.limit)
                    ]
            for job in jobs:
                print(f"{job['id']}  {job['state']:<9}  {job['kind']:<10}  {job['created_at']}")
            return

        if action == "wait":
            client = get_client_if_running(palace_path)
            if client is not None:
                job = client.wait(args.job_id)
            else:
                qpath = queue_path(palace_path)
                if not qpath.exists():
                    raise DaemonError("daemon is not running")
                job = job_to_dict(QueueStore(qpath).get(args.job_id))
                if job.get("state") not in TERMINAL_STATES:
                    raise DaemonError(f"daemon is not running; job {args.job_id} is {job['state']}")
            result = job.get("result") or {}
            from ..service import print_job_result

            exit_code = print_job_result(result)
            if job.get("state") != "succeeded" and exit_code == 0:
                print(f"mempalace: daemon job failed: {job.get('error')}", file=sys.stderr)
                exit_code = 1
            if exit_code:
                sys.exit(exit_code)
            return
    except DaemonError as exc:
        print(f"mempalace: daemon error: {exc}", file=sys.stderr)
        sys.exit(1)
