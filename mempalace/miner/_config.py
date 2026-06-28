"""Config — YAML configuration loading for the miner.

Wing: miner | Topic: config | Updated: 2026-06-28 18:30
"""

from pathlib import Path


def load_config(project_dir: str) -> dict:
    """Load mempalace.yaml from project directory (falls back to mempal.yaml)."""
    import yaml

    resolved_project_dir = Path(project_dir).expanduser().resolve()
    config_path = resolved_project_dir / "mempalace.yaml"
    if not config_path.exists():
        # Fallback to legacy name
        legacy_path = resolved_project_dir / "mempal.yaml"
        if legacy_path.exists():
            config_path = legacy_path
        else:
            from ..config import normalize_wing_name

            # Normalize the dirname-derived fallback wing the same way
            # ``cmd_init`` and ``room_detector_local`` do — otherwise a
            # hyphenated project mined without a yaml file lands under a
            # raw-name wing while ``topics_by_wing`` was keyed under the
            # normalized slug, silently dropping every topic tunnel
            # (the no-yaml branch of issue #1194).
            wing_name = normalize_wing_name(resolved_project_dir.name)
            print(
                f"  No mempalace.yaml found in {resolved_project_dir} "
                f"— using auto-detected defaults (wing='{wing_name}'). "
                "Directories with the same basename will share a wing; "
                "add mempalace.yaml to disambiguate.",
                file=__import__("sys").stderr,
            )
            return {
                "wing": wing_name,
                "rooms": [
                    {
                        "name": "general",
                        "description": "All project files",
                        "keywords": ["general"],
                    }
                ],
            }
    try:
        with open(config_path) as f:
            return yaml.safe_load(f)
    except (FileNotFoundError, OSError):
        wing_name = Path(project_dir).expanduser().resolve().name
        from ..config import normalize_wing_name

        wing_name = normalize_wing_name(wing_name)
        print(
            f"  Config file {config_path} could not be read "
            f"— using auto-detected defaults (wing='{wing_name}').",
            file=__import__("sys").stderr,
        )
        return {
            "wing": wing_name,
            "rooms": [
                {
                    "name": "general",
                    "description": "All project files",
                    "keywords": ["general"],
                }
            ],
        }
