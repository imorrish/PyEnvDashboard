from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable, Iterator, Optional

from uv_dash.config import default_scan_roots, load_config
from uv_dash.models import UvProject

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib  # type: ignore
    except ImportError:
        tomllib = None  # type: ignore


def _dir_size(path: Path, max_files: int = 50_000) -> int:
    """Approximate directory size; stops early on huge trees."""
    total = 0
    count = 0
    try:
        for root, dirs, files in os.walk(path, followlinks=False):
            # prune heavy dirs
            dirs[:] = [
                d
                for d in dirs
                if d not in (".git", "__pycache__", "node_modules")
            ]
            for name in files:
                try:
                    total += (Path(root) / name).stat().st_size
                except OSError:
                    pass
                count += 1
                if count >= max_files:
                    return total
    except OSError:
        pass
    return total


def _read_pyproject(path: Path) -> dict:
    if tomllib is None:
        return {}
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError if hasattr(tomllib, "TOMLDecodeError") else Exception):
        return {}


def _python_version_file(project_dir: Path) -> Optional[str]:
    pv = project_dir / ".python-version"
    if not pv.is_file():
        return None
    try:
        text = pv.read_text(encoding="utf-8").strip()
        return text.splitlines()[0].strip() if text else None
    except OSError:
        return None


def _venv_python_version(venv: Path) -> Optional[str]:
    cfg = venv / "pyvenv.cfg"
    if not cfg.is_file():
        return None
    try:
        for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.lower().startswith("version"):
                # version = 3.12.3  or  version_info = ...
                parts = line.split("=", 1)
                if len(parts) == 2:
                    return parts[1].strip()
    except OSError:
        pass
    return None


def _package_count(venv: Path) -> Optional[int]:
    """Count top-level dist-info / egg-info under site-packages."""
    candidates = [
        venv / "Lib" / "site-packages",  # Windows
        venv / "lib",
    ]
    site = None
    for c in candidates:
        if c.is_dir():
            # lib/pythonX.Y/site-packages
            if c.name == "lib":
                for sub in c.iterdir():
                    sp = sub / "site-packages"
                    if sp.is_dir():
                        site = sp
                        break
            else:
                site = c
            break
    if site is None:
        return None
    try:
        n = 0
        for p in site.iterdir():
            if p.suffix in (".dist-info", ".egg-info") or p.name.endswith(".dist-info"):
                n += 1
            elif p.is_dir() and (
                p.name.endswith(".dist-info") or p.name.endswith(".egg-info")
            ):
                n += 1
        return n
    except OSError:
        return None


def parse_project(project_dir: Path) -> UvProject:
    pyproject = project_dir / "pyproject.toml"
    data = _read_pyproject(pyproject) if pyproject.is_file() else {}
    project_table = data.get("project") or {}
    name = project_table.get("name") or project_dir.name
    version = project_table.get("version")
    description = (project_table.get("description") or "") or ""
    requires_python = project_table.get("requires-python")
    deps = list(project_table.get("dependencies") or [])

    has_lock = (project_dir / "uv.lock").is_file()
    venv_path = project_dir / ".venv"
    has_venv = venv_path.is_dir() and (venv_path / "pyvenv.cfg").is_file()

    python_version = _python_version_file(project_dir)
    venv_size = 0
    pkg_count = None
    if has_venv:
        if not python_version:
            python_version = _venv_python_version(venv_path)
        venv_size = _dir_size(venv_path)
        pkg_count = _package_count(venv_path)

    try:
        mtime = pyproject.stat().st_mtime if pyproject.is_file() else None
    except OSError:
        mtime = None

    is_ws = False
    tool_uv = data.get("tool", {}).get("uv", {})
    if isinstance(tool_uv, dict) and "workspace" in tool_uv:
        is_ws = True

    return UvProject(
        path=project_dir.resolve(),
        name=str(name),
        version=str(version) if version else None,
        description=str(description),
        requires_python=str(requires_python) if requires_python else None,
        has_lock=has_lock,
        has_venv=has_venv,
        venv_path=venv_path.resolve() if has_venv else None,
        python_version=python_version,
        venv_size_bytes=venv_size,
        package_count=pkg_count,
        last_modified=mtime,
        dependencies=deps,
        is_workspace_member=is_ws,
    )


def iter_projects(
    roots: Optional[list[Path]] = None,
    max_depth: int = 6,
    skip_dirs: Optional[set[str]] = None,
    uv_only: bool = False,
    on_progress: Optional[Callable[[str], None]] = None,
) -> Iterator[UvProject]:
    """Walk roots and yield UvProject for each directory containing pyproject.toml."""
    cfg = load_config()
    if roots is None:
        configured = cfg.get("scan_roots") or []
        if configured:
            roots = [Path(p).expanduser() for p in configured]
        else:
            roots = default_scan_roots()
    max_depth = int(cfg.get("max_depth", max_depth))
    skip = set(skip_dirs or cfg.get("skip_dirs") or [])
    uv_only = bool(cfg.get("uv_only", uv_only))

    seen: set[Path] = set()

    for root in roots:
        root = root.expanduser().resolve()
        if not root.is_dir():
            continue
        if on_progress:
            on_progress(str(root))

        # If root itself is a project
        if (root / "pyproject.toml").is_file():
            proj = parse_project(root)
            if not uv_only or proj.has_lock or proj.has_venv:
                key = proj.path
                if key not in seen:
                    seen.add(key)
                    yield proj

        for dirpath, dirnames, _filenames in os.walk(root, topdown=True, followlinks=False):
            rel = Path(dirpath).relative_to(root)
            depth = len(rel.parts)
            if depth > max_depth:
                dirnames.clear()
                continue

            # prune: skip listed dirs and hidden dirs (never walk into .venv either)
            dirnames[:] = [
                d
                for d in dirnames
                if d not in skip and not d.startswith(".")
            ]

            # skip hidden top-level dirs except known project markers handled above
            base = Path(dirpath)
            if (base / "pyproject.toml").is_file():
                # don't walk into nested projects as separate roots of walk pruning:
                # still yield this project, then prune children that are also projects? keep simple: yield all
                proj = parse_project(base)
                if uv_only and not (proj.has_lock or proj.has_venv):
                    continue
                key = proj.path
                if key not in seen:
                    seen.add(key)
                    if on_progress:
                        on_progress(str(key))
                    yield proj
                # optional: don't recurse into project (treat as leaf for discovery of *other* projects)
                # For monorepos we *do* want nested pyproject.toml, so keep walking.


def scan_projects(
    roots: Optional[list[Path]] = None,
    **kwargs,
) -> list[UvProject]:
    projects = list(iter_projects(roots=roots, **kwargs))
    projects.sort(key=lambda p: (p.name.lower(), str(p.path)))
    return projects
