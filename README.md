# UV-Dash

Solves the the “I lose track of all my uv projects” problem.

Every web search for an existing UI based tool to manage my UV environments suggest PyEnvManager, alas it appears to be no more (not that I even know what it looks like).

So I used Grok to scafold a project, worked on the windows version, then had to lean hevily on Copilot to get the build process working.

Result: Flet/flutter-based uv project dashboard — pure Python, cross-platform.

 ![UV-Dash app screen shot](screenshot.png) 

## Features

| Area | Behaviour |
| --- | --- |
| **Discovery** | Walks configurable roots for `pyproject.toml` |
| **Info** | Name, path, Python version, lock, `.venv` size, package count |
| **Actions** | Terminal (venv activated), folder, editor (Cursor/VS Code), `uv sync`, delete `.venv` only |
| **Settings** | Scan roots, max depth, optional uv\-only filter |
| **Platform** | Windows / macOS / Linux |

## Requirements

-   Python (obviously)
-   UV (obviously)
-   uv must be on PATH for uv sync (and any future uv actions).

## Development

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```shell
uv sync
uv run uv-dash
```

The dashboard searches common project directories in the user’s home folder  
(`Projects`, `src`, `code`, and `dev`) for `pyproject.toml` files. It displays  
lockfile and Python-version information and can open a terminal, run `uv sync`,  
or delete a selected project.

To package the application or launch it from another directory:

```shell
uv run python -m uv_dash.main
```

Build local standalone runtime  
Windows

```
uv run flet build windows -o ../artifacts/uv-dash-windows --product "uv-dash" --yes
```

macOS

```
uv run flet build macos -o ../artifacts/uv-dash-macos --product "uv-dash" --yes
```

Linux

```
uv run flet build linux -o ../artifacts/uv-dash-linux --product "uv-dash" --yes
```