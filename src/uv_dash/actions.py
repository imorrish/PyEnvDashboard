from __future__ import annotations

import base64
import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from uv_dash.models import UvProject


def which_uv() -> Optional[str]:
    return shutil.which("uv")


def uv_version() -> Optional[str]:
    """Return the installed uv version, or None when uv cannot be queried."""
    uv = which_uv()
    if not uv:
        return None
    try:
        result = subprocess.run(
            [uv, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    output = (result.stdout or result.stderr).strip()
    if not output:
        return None
    return output.removeprefix("uv ").strip()


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

        # Prefer Windows Terminal with PowerShell 7, then pwsh, then cmd
        wt = shutil.which("wt")
        pwsh = shutil.which("pwsh")
        if wt and pwsh:
            encoded_command = base64.b64encode(
                ps_command.encode("utf-16le")
            ).decode("ascii")
            subprocess.Popen(
                [
                    wt,
                    "-d",
                    cwd,
                    pwsh,
                    "-NoExit",
                    "-EncodedCommand",
                    encoded_command,
                ]
            )
            return

        if pwsh:
            subprocess.Popen([pwsh, "-NoExit", "-Command", ps_command])
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
    """Open a project in the first available code editor."""
    for editor in ("vscode", "pycharm", "neovim"):
        try:
            open_with_editor(project, editor)
            return
        except RuntimeError:
            continue
    raise RuntimeError("No configured editor was found on PATH")


EDITOR_LABELS = {
    "vscode": "VSCode",
    "marimo": "Marimo",
    "pycharm": "PyCharm",
    "jupyter": "Jupyter",
    "neovim": "neovim",
}


def open_with_editor(
    project: UvProject,
    editor: str,
    marimo_url: str = "http://localhost",
) -> None:
    """Open a project with a configured editor."""
    if editor == "vscode":
        _launch_vscode(project.path)
        return
    if editor == "pycharm":
        _launch_command(("pycharm", "pycharm64", "pycharm64.exe"), [str(project.path)])
        return
    if editor == "jupyter":
        _launch_command(("jupyter",), ["lab", str(project.path)], cwd=project.path)
        return
    if editor == "neovim":
        _launch_command(("nvim", "neovim"), [str(project.path)])
        return
    if editor == "marimo":
        _launch_marimo(project, marimo_url)
        return
    raise RuntimeError(f"Unknown editor: {editor}")


def _launch_vscode(project_path: Path) -> None:
    """Open a project folder in VSCode using the platform's native launcher."""
    project_path = project_path.resolve()

    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        program_files = os.environ.get("ProgramFiles")
        program_files_x86 = os.environ.get("ProgramFiles(x86)")
        candidates = [
            shutil.which("code"),
            shutil.which("code.cmd"),
            str(Path(local_app_data) / "Programs" / "Microsoft VS Code" / "Code.exe")
            if local_app_data
            else None,
            str(Path(program_files) / "Microsoft VS Code" / "Code.exe")
            if program_files
            else None,
            str(Path(program_files_x86) / "Microsoft VS Code" / "Code.exe")
            if program_files_x86
            else None,
        ]
        executable = next(
            (candidate for candidate in candidates if candidate and Path(candidate).is_file()),
            None,
        )
        if not executable:
            raise RuntimeError(
                "VSCode was not found. Install VSCode or add its command to PATH."
            )
        _launch_command((executable,), ["--new-window", str(project_path)])
        return

    if sys.platform == "darwin":
        try:
            subprocess.Popen(
                [
                    "open",
                    "-a",
                    "Visual Studio Code",
                    "--args",
                    "--new-window",
                    str(project_path),
                ]
            )
        except OSError as exc:
            raise RuntimeError(f"Could not start VSCode: {exc}") from exc
        return

    _launch_command(("code",), ["--new-window", str(project_path)])


def _launch_command(
    executables: tuple[str, ...],
    args: list[str],
    cwd: Optional[Path] = None,
) -> None:
    executable = next((candidate for candidate in executables if shutil.which(candidate)), None)
    if not executable:
        raise RuntimeError(f"{executables[0]} was not found on PATH")
    try:
        command = [executable, *args]
        if sys.platform == "win32" and executable.lower().endswith((".cmd", ".bat")):
            subprocess.Popen(
                subprocess.list2cmdline(command),
                cwd=str(cwd) if cwd else None,
                shell=True,
            )
        else:
            subprocess.Popen(command, cwd=str(cwd) if cwd else None)
    except OSError as exc:
        raise RuntimeError(f"Could not start {executables[0]}: {exc}") from exc


def _launch_marimo(project: UvProject, url: str) -> None:
    parsed = urlparse(url.strip() or "http://localhost")
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise RuntimeError("Marimo URL must be an http:// or https:// URL")
    port = parsed.port or 2718
    host = parsed.hostname
    _launch_command(
        ("marimo",),
        ["edit", "--headless", "--host", host, "--port", str(port)],
        cwd=project.path,
    )
    launch_url = url.rstrip("/")
    if not parsed.port:
        launch_url = f"{launch_url}:{port}"
    webbrowser.open(launch_url)