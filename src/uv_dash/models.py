from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class UvProject:
    """A discovered uv-managed (or pyproject.toml) project."""

    path: Path
    name: str
    version: Optional[str] = None
    description: str = ""
    requires_python: Optional[str] = None
    has_lock: bool = False
    has_venv: bool = False
    venv_path: Optional[Path] = None
    python_version: Optional[str] = None  # from .python-version or venv
    venv_size_bytes: int = 0
    package_count: Optional[int] = None
    last_modified: Optional[float] = None  # mtime of pyproject.toml
    dependencies: list[str] = field(default_factory=list)
    is_workspace_member: bool = False
    error: Optional[str] = None

    @property
    def venv_size_human(self) -> str:
        return format_bytes(self.venv_size_bytes)

    @property
    def display_path(self) -> str:
        try:
            return str(self.path.relative_to(Path.home()))
        except ValueError:
            return str(self.path)


def format_bytes(n: int) -> str:
    if n <= 0:
        return "—"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    f = float(n)
    while f >= 1024 and i < len(units) - 1:
        f /= 1024
        i += 1
    if i == 0:
        return f"{int(f)} {units[i]}"
    return f"{f:.1f} {units[i]}"
