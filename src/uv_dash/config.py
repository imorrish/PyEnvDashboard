from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def config_dir() -> Path:
    """Platform config directory for uv-dash."""
    import sys

    if sys.platform == "win32":
        base = Path.home() / "AppData" / "Local" / "uv-dash"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "uv-dash"
    else:
        base = Path.home() / ".config" / "uv-dash"
    base.mkdir(parents=True, exist_ok=True)
    return base


def config_path() -> Path:
    return config_dir() / "config.json"


DEFAULT_CONFIG: dict[str, Any] = {
    # Roots to scan for projects (empty = use home + common project dirs)
    "scan_roots": [],
    # Max directory depth when scanning
    "max_depth": 6,
    # Directory names to skip entirely
    "skip_dirs": [
        ".git",
        "node_modules",
        "__pycache__",
        ".tox",
        ".nox",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        "dist",
        "build",
        ".eggs",
        "site-packages",
        "Library",
        "AppData",
        ".cache",
        ".local",
        ".cargo",
        ".rustup",
        "target",
    ],
    # Prefer only projects that look uv-managed (have uv.lock or .venv created by uv)
    "uv_only": False,
    # Theme: "system" | "light" | "dark"
    "theme": "system",
}


def load_config() -> dict[str, Any]:
    path = config_path()
    if not path.exists():
        return dict(DEFAULT_CONFIG)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        merged = dict(DEFAULT_CONFIG)
        merged.update(data)
        return merged
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULT_CONFIG)


def save_config(cfg: dict[str, Any]) -> None:
    path = config_path()
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def default_scan_roots() -> list[Path]:
    """Sensible defaults when user has not configured roots."""
    home = Path.home()
    candidates = [
        home / "Projects",
        home / "projects",
        home / "src",
        home / "code",
        home / "dev",
        home / "Dev",
        home / "Documents" / "Projects",
        home / "workspace",
        home / "repos",
    ]
    roots = [p for p in candidates if p.is_dir()]
    # Always include home at shallow depth if nothing else found
    if not roots:
        roots = [home]
    return roots
