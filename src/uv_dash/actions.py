from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from uv_dash.models import UvProject


def which_uv() -> Optional[str]:
    return shutil.which("uv")


def open_in_file_manager(path: Path) -> None:
    path = path.resolve()
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def open_terminal(project: UvProject) -> None:
    """Open a terminal in the project directory, activating .venv when present."""
    cwd = str(project.path)
    venv = project.venv_path

    if sys.platform == "win32":
        # Always pass a real -Command string (empty is invalid for PowerShell)
        parts: list[str] = [f'Set-Location -LiteralPath "{cwd}"']
        if venv and (venv / "Scripts" / "Activate.ps1").is_file():
            parts.append(f'& "{venv / "Scripts" / "Activate.ps1"}"')
        ps_command = "; ".join(parts)

        # Prefer Windows Terminal, then Windows PowerShell / pwsh, then cmd
        if shutil.which("wt"):
            subprocess.Popen(
                [
                    "wt",
                    "-d",
                    cwd,
                    "powershell",
                    "-NoExit",
                    "-Command",
                    ps_command,
                ]
            )
            return

        for shell in ("pwsh", "powershell"):
            if shutil.which(shell):
                subprocess.Popen(
                    [shell, "-NoExit", "-Command", ps_command]
                )
                return

        # cmd.exe fallback
        activate_bat = ""
        if venv and (venv / "Scripts" / "activate.bat").is_file():
            activate_bat = f' && "{venv / "Scripts" / "activate.bat"}"'
        subprocess.Popen(
            f'start cmd /K "cd /d "{cwd}"{activate_bat}"',
            shell=True,
        )
        return

    # macOS / Linux
    shell = os.environ.get("SHELL", "/bin/bash")
    activate_cmd = ""
    if venv:
        act = venv / "bin" / "activate"
        if act.is_file():
            activate_cmd = f'source "{act}"; '

    if sys.platform == "darwin":
        # AppleScript Terminal
        script = (
            f'tell application "Terminal" to do script '
            f'"cd \\"{cwd}\\"; {activate_cmd}exec {shell}"'
        )
        subprocess.Popen(["osascript", "-e", script])
        return

    # Linux: try common terminals
    for term in (
        ["gnome-terminal", "--working-directory", cwd, "--", shell, "-c", f"{activate_cmd}exec {shell}"],
        ["konsole", "--workdir", cwd, "-e", shell, "-c", f"{activate_cmd}exec {shell}"],
        ["xfce4-terminal", f"--working-directory={cwd}", "-e", f"{shell} -c '{activate_cmd}exec {shell}'"],
        ["xterm", "-e", f'cd "{cwd}" && {activate_cmd}exec {shell}'],
    ):
        if shutil.which(term[0]):
            try:
                subprocess.Popen(term)
                return
            except OSError:
                continue
    # last resort
    subprocess.Popen([shell], cwd=cwd)


def run_uv(
    project: UvProject,
    args: list[str],
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    uv = which_uv()
    if not uv:
        raise RuntimeError(
            "uv not found on PATH. Install from https://docs.astral.sh/uv/"
        )
    cmd = [uv, *args]
    return subprocess.run(
        cmd,
        cwd=str(project.path),
        capture_output=capture,
        text=True,
        timeout=300,
    )


def uv_sync(project: UvProject) -> str:
    result = run_uv(project, ["sync"])
    out = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        raise RuntimeError(out or f"uv sync failed ({result.returncode})")
    return out or "Synced successfully."


def uv_lock(project: UvProject) -> str:
    result = run_uv(project, ["lock"])
    out = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        raise RuntimeError(out or f"uv lock failed ({result.returncode})")
    return out or "Lock updated."


def delete_venv(project: UvProject) -> None:
    if not project.venv_path or not project.venv_path.is_dir():
        raise RuntimeError("No .venv to delete")
    shutil.rmtree(project.venv_path)


def open_editor(project: UvProject) -> None:
    """Open project in VS Code / Cursor / default editor if available."""
    for editor in ("cursor", "code", "codium"):
        if shutil.which(editor):
            subprocess.Popen([editor, str(project.path)])
            return
    open_in_file_manager(project.path)