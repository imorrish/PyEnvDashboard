from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

import flet as ft

from uv_dash import __version__
from uv_dash.actions import (
    delete_venv,
    open_editor,
    open_in_file_manager,
    open_terminal,
    uv_sync,
    which_uv,
)
from uv_dash.config import (
    default_scan_roots,
    load_config,
    save_config,
)
from uv_dash.models import UvProject, format_bytes
from uv_dash.scanner import parse_project, scan_projects


class AppState:
    def __init__(self) -> None:
        self.projects: list[UvProject] = []
        self.filter_text: str = ""
        self.show_only_with_venv: bool = False
        self.scanning: bool = False
        self.status: str = "Ready"
        self.selected: Optional[UvProject] = None


def main() -> None:
    # Flet 1.0+: ft.run() replaces ft.app(target=...)
    ft.run(build_app)


def build_app(page: ft.Page) -> None:
    page.title = f"uv-dash {__version__}"
    page.theme_mode = ft.ThemeMode.SYSTEM
    page.padding = 0
    try:
        page.window.width = 1100
        page.window.height = 720
        page.window.min_width = 800
        page.window.min_height = 500
    except Exception:
        pass

    state = AppState()
    cfg = load_config()
    theme = cfg.get("theme", "system")
    if theme == "dark":
        page.theme_mode = ft.ThemeMode.DARK
    elif theme == "light":
        page.theme_mode = ft.ThemeMode.LIGHT

    project_list = ft.ListView(expand=True, spacing=4, padding=8)
    detail_panel = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=8)
    status_text = ft.Text("Ready", size=12, color=ft.Colors.ON_SURFACE_VARIANT)
    search_field = ft.TextField(
        hint_text="Filter by name or path…",
        prefix_icon=ft.Icons.SEARCH,
        dense=True,
        expand=True,
        on_change=lambda e: on_filter_change(e.control.value or ""),
    )
    progress = ft.ProgressBar(visible=False, width=200)
    stats_text = ft.Text("", size=12, color=ft.Colors.ON_SURFACE_VARIANT)

    def set_status(msg: str) -> None:
        state.status = msg
        status_text.value = msg
        status_text.update()

    def filtered_projects() -> list[UvProject]:
        q = state.filter_text.strip().lower()
        out = state.projects
        if state.show_only_with_venv:
            out = [p for p in out if p.has_venv]
        if q:
            out = [
                p
                for p in out
                if q in p.name.lower()
                or q in str(p.path).lower()
                or q in (p.description or "").lower()
            ]
        return out

    def project_tile(p: UvProject) -> ft.Control:
        badges: list[ft.Control] = []
        if p.has_lock:
            badges.append(
                ft.Container(
                    content=ft.Text("lock", size=10, weight=ft.FontWeight.BOLD),
                    bgcolor=ft.Colors.GREEN_700,
                    padding=ft.Padding.symmetric(vertical=2, horizontal=4),
                    border_radius=4,
                )
            )
        if p.has_venv:
            badges.append(
                ft.Container(
                    content=ft.Text("venv", size=10, weight=ft.FontWeight.BOLD),
                    bgcolor=ft.Colors.BLUE_700,
                    padding=ft.Padding.symmetric(vertical=2, horizontal=4),
                    border_radius=4,
                )
            )
        else:
            badges.append(
                ft.Container(
                    content=ft.Text("no venv", size=10),
                    bgcolor=ft.Colors.GREY_700,
                    padding=ft.Padding.symmetric(vertical=2, horizontal=4),
                    border_radius=4,
                )
            )

        subtitle_parts = [p.display_path]
        if p.python_version:
            subtitle_parts.append(f"Py {p.python_version}")
        if p.has_venv:
            subtitle_parts.append(p.venv_size_human)

        selected = state.selected is not None and state.selected.path == p.path

        return ft.Container(
            content=ft.ListTile(
                title=ft.Row(
                    [
                        ft.Text(p.name, weight=ft.FontWeight.W_600, expand=True),
                        *badges,
                    ],
                    spacing=6,
                ),
                subtitle=ft.Text(" · ".join(subtitle_parts), size=11),
                dense=True,
                on_click=lambda e, proj=p: select_project(proj),
            ),
            bgcolor=ft.Colors.PRIMARY_CONTAINER if selected else None,
            border_radius=8,
        )

    def refresh_list() -> None:
        items = filtered_projects()
        project_list.controls = [project_tile(p) for p in items]
        total_size = sum(p.venv_size_bytes for p in state.projects if p.has_venv)
        stats_text.value = (
            f"{len(items)} shown / {len(state.projects)} total · "
            f"venvs {format_bytes(total_size)}"
        )
        project_list.update()
        stats_text.update()

    def render_detail(p: Optional[UvProject]) -> None:
        detail_panel.controls.clear()
        if p is None:
            detail_panel.controls.append(
                ft.Container(
                    content=ft.Text(
                        "Select a project",
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    padding=24,
                )
            )
            detail_panel.update()
            return

        def action_btn(label: str, icon, handler, danger: bool = False):
            return ft.Button(
                content=label,
                icon=icon,
                on_click=handler,
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.ERROR_CONTAINER if danger else None,
                ),
            )

        meta_rows = [
            ("Path", str(p.path)),
            ("Version", p.version or "—"),
            ("Requires Python", p.requires_python or "—"),
            ("Interpreter", p.python_version or "—"),
            ("uv.lock", "yes" if p.has_lock else "no"),
            (".venv", str(p.venv_path) if p.has_venv else "missing"),
            ("Venv size", p.venv_size_human if p.has_venv else "—"),
            (
                "Packages",
                str(p.package_count) if p.package_count is not None else "—",
            ),
            (
                "Modified",
                datetime.fromtimestamp(p.last_modified).strftime("%Y-%m-%d %H:%M")
                if p.last_modified
                else "—",
            ),
        ]

        async def do_sync(e=None) -> None:
            set_status(f"Running uv sync in {p.name}…")
            progress.visible = True
            progress.update()
            try:
                msg = await asyncio.to_thread(uv_sync, p)
                updated = await asyncio.to_thread(parse_project, p.path)
                for i, existing in enumerate(state.projects):
                    if existing.path == updated.path:
                        state.projects[i] = updated
                        state.selected = updated
                        break
                set_status("OK: " + (msg[:200] if msg else "synced"))
            except Exception as ex:
                set_status(f"Error: {ex}")
            finally:
                progress.visible = False
                progress.update()
                refresh_list()
                render_detail(state.selected)

        def do_terminal(e=None) -> None:
            try:
                open_terminal(p)
                set_status(f"Opened terminal in {p.name}")
            except Exception as ex:
                set_status(f"Terminal error: {ex}")

        def confirm_delete_venv(e=None) -> None:
            if not p.has_venv:
                set_status("No .venv to delete")
                return

            def on_yes(ev) -> None:
                dlg.open = False
                page.update()
                try:
                    delete_venv(p)
                    updated = parse_project(p.path)
                    for i, existing in enumerate(state.projects):
                        if existing.path == updated.path:
                            state.projects[i] = updated
                            state.selected = updated
                            break
                    set_status(f"Deleted .venv for {p.name}")
                    refresh_list()
                    render_detail(state.selected)
                except Exception as ex:
                    set_status(f"Delete failed: {ex}")

            def on_no(ev) -> None:
                dlg.open = False
                page.update()

            dlg = ft.AlertDialog(
                title=ft.Text("Delete virtual environment?"),
                content=ft.Text(
                    f"This will permanently delete:\n{p.venv_path}\n\n"
                    f"Size: {p.venv_size_human}\nProject files are kept."
                ),
                actions=[
                    ft.TextButton("Cancel", on_click=on_no),
                    ft.TextButton("Delete", on_click=on_yes),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            page.overlay.append(dlg)
            dlg.open = True
            page.update()

        detail_panel.controls.extend(
            [
                ft.Text(p.name, size=22, weight=ft.FontWeight.BOLD),
                ft.Text(
                    p.description or "No description",
                    size=13,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Divider(),
                ft.Row(
                    [
                        action_btn("Terminal", ft.Icons.TERMINAL, do_terminal),
                        action_btn(
                            "Open folder",
                            ft.Icons.FOLDER_OPEN,
                            lambda e: open_in_file_manager(p.path),
                        ),
                        action_btn(
                            "Editor",
                            ft.Icons.CODE,
                            lambda e: open_editor(p),
                        ),
                        action_btn("uv sync", ft.Icons.SYNC, do_sync),
                        action_btn(
                            "Delete .venv",
                            ft.Icons.DELETE_OUTLINE,
                            confirm_delete_venv,
                            danger=True,
                        ),
                    ],
                    wrap=True,
                    spacing=8,
                ),
                ft.Divider(),
                ft.DataTable(
                    columns=[
                        ft.DataColumn(ft.Text("Field")),
                        ft.DataColumn(ft.Text("Value")),
                    ],
                    rows=[
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Text(k, weight=ft.FontWeight.W_500)),
                                ft.DataCell(
                                    ft.Text(
                                        v,
                                        selectable=True,
                                        max_lines=2,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    )
                                ),
                            ]
                        )
                        for k, v in meta_rows
                    ],
                    column_spacing=16,
                ),
            ]
        )

        if p.dependencies:
            detail_panel.controls.append(
                ft.Text("Dependencies", weight=ft.FontWeight.W_600)
            )
            detail_panel.controls.append(
                ft.Text(
                    ", ".join(p.dependencies[:40])
                    + ("…" if len(p.dependencies) > 40 else ""),
                    size=12,
                    selectable=True,
                )
            )

        detail_panel.update()

    def select_project(p: UvProject) -> None:
        state.selected = p
        refresh_list()
        render_detail(p)

    def on_filter_change(text: str) -> None:
        state.filter_text = text
        refresh_list()

    async def do_scan(e=None) -> None:
        if state.scanning:
            return
        state.scanning = True
        progress.visible = True
        progress.update()
        set_status("Scanning…")

        try:
            projects = await asyncio.to_thread(scan_projects)
            state.projects = projects
            set_status(f"Found {len(projects)} projects")
            if state.selected:
                for p in projects:
                    if p.path == state.selected.path:
                        state.selected = p
                        break
                else:
                    state.selected = None
            refresh_list()
            render_detail(state.selected)
        except Exception as ex:
            set_status(f"Scan error: {ex}")
        finally:
            state.scanning = False
            progress.visible = False
            progress.update()

    def open_settings(e=None) -> None:
        cfg = load_config()
        roots = cfg.get("scan_roots") or [str(p) for p in default_scan_roots()]
        roots_field = ft.TextField(
            label="Scan roots (one path per line)",
            value="\n".join(roots),
            multiline=True,
            min_lines=4,
            max_lines=10,
            expand=True,
        )
        depth_field = ft.TextField(
            label="Max depth",
            value=str(cfg.get("max_depth", 6)),
            width=120,
        )
        uv_only_sw = ft.Switch(
            label="Only show projects with uv.lock or .venv",
            value=bool(cfg.get("uv_only", False)),
        )

        def save(ev) -> None:
            lines = [
                ln.strip()
                for ln in (roots_field.value or "").splitlines()
                if ln.strip()
            ]
            cfg["scan_roots"] = lines
            try:
                cfg["max_depth"] = max(1, int(depth_field.value or "6"))
            except ValueError:
                cfg["max_depth"] = 6
            cfg["uv_only"] = bool(uv_only_sw.value)
            save_config(cfg)
            dlg.open = False
            page.update()
            set_status("Settings saved — rescanning…")
            page.run_task(do_scan)

        def cancel(ev) -> None:
            dlg.open = False
            page.update()

        dlg = ft.AlertDialog(
            title=ft.Text("Settings"),
            content=ft.Container(
                content=ft.Column(
                    [roots_field, depth_field, uv_only_sw],
                    tight=True,
                    spacing=12,
                ),
                width=480,
            ),
            actions=[
                ft.TextButton("Cancel", on_click=cancel),
                ft.TextButton("Save", on_click=save),
            ],
        )
        page.overlay.append(dlg)
        dlg.open = True
        page.update()

    toolbar = ft.Container(
        content=ft.Row(
            [
                ft.Text("uv-dash", size=18, weight=ft.FontWeight.BOLD),
                ft.Container(width=12),
                search_field,
                ft.IconButton(
                    icon=ft.Icons.REFRESH,
                    tooltip="Rescan",
                    on_click=lambda e: page.run_task(do_scan),
                ),
                ft.IconButton(
                    icon=ft.Icons.SETTINGS,
                    tooltip="Settings",
                    on_click=open_settings,
                ),
            ],
            alignment=ft.MainAxisAlignment.START,
        ),
        padding=ft.Padding.symmetric(vertical=8, horizontal=12),
        border=ft.Border.only(bottom=ft.BorderSide(width=1, color=ft.Colors.OUTLINE_VARIANT)),
    )

    left = ft.Container(
        content=ft.Column(
            [
                ft.Container(
                    content=stats_text,
                    padding=ft.Padding.only(left=12, top=4),
                ),
                project_list,
            ],
            expand=True,
            spacing=0,
        ),
        width=380,
        border=ft.Border.only(right=ft.BorderSide(width=1, color=ft.Colors.OUTLINE_VARIANT)),
    )

    right = ft.Container(
        content=detail_panel,
        expand=True,
        padding=16,
    )

    body = ft.Row([left, right], expand=True, spacing=0)

    footer = ft.Container(
        content=ft.Row(
            [
                status_text,
                progress,
                ft.Text(
                    f"uv: {'found' if which_uv() else 'NOT ON PATH'}",
                    size=11,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        ),
        padding=ft.Padding.symmetric(vertical=6, horizontal=12),
        border=ft.Border.only(top=ft.BorderSide(width=1, color=ft.Colors.OUTLINE_VARIANT)),
    )

    page.add(
        ft.Column(
            [toolbar, body, footer],
            expand=True,
            spacing=0,
        )
    )

    render_detail(None)
    page.run_task(do_scan)


if __name__ == "__main__":
    main()
