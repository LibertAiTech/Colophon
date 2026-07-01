"""Local HTTP serving and watch-mode rebuilds.

Project paths flow into filesystem snapshots; changed inputs trigger rebuilds
before the generated output directory is served.
"""

from __future__ import annotations

import datetime as dt
import functools
import threading
import time
from pathlib import Path

from .build import build_site
from .errors import ColophonError
from .models import ProjectPaths


def snapshot_inputs(project: ProjectPaths) -> dict[str, tuple[int, int]]:
    resolved_project = project
    snapshot: dict[str, tuple[int, int]] = {}

    def add(path: Path) -> None:
        if (
            not path.exists()
            or path.name.startswith(".")
            or "__pycache__" in path.parts
            or not path.is_file()
        ):
            return

        try:
            stat = path.stat()
        except FileNotFoundError:
            return

        snapshot[str(path)] = (stat.st_mtime_ns, stat.st_size)

    for path in resolved_project.watched_files:
        add(path)

    for directory in resolved_project.watched_dirs:
        if directory.exists():
            for path in directory.rglob("*"):
                add(path)

    return snapshot


def watch_and_rebuild(project: ProjectPaths, interval: float = 0.4) -> None:
    resolved_project = project
    previous = snapshot_inputs(resolved_project)

    while True:
        time.sleep(interval)
        current = snapshot_inputs(resolved_project)

        if current == previous:
            continue

        sample = sorted(set(current) ^ set(previous))[:3]

        if sample:
            pretty = ", ".join(
                path.relative_to(resolved_project.root).as_posix()
                if (path := Path(item)).is_relative_to(resolved_project.root)
                else path.as_posix()
                for item in sample
            )
            print(f"change detected: {pretty}")

        try:
            result = build_site(resolved_project)
            page_count = sum(
                result.counts.get(key, 0)
                for key in ("pages", "posts", "archive_pages", "tag_pages", "feeds")
            )
            print(
                f"rebuilt {resolved_project.output_dir.name}/ with "
                f"{page_count} output page(s) at {dt.datetime.now().strftime('%H:%M:%S')}"
            )
            previous = snapshot_inputs(resolved_project)
        except ColophonError as exc:
            print(f"build failed ({exc.category}): {exc}")
            previous = current
        except Exception as exc:
            print(f"build failed: {exc}")
            previous = current


def serve_site(
    port: int,
    *,
    project: ProjectPaths,
    watch: bool = False,
    test: bool = False,
) -> None:
    resolved_project = project
    import http.server
    import socketserver

    class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
        def end_headers(self) -> None:
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True

    handler = functools.partial(NoCacheHandler, directory=str(resolved_project.output_dir))

    if watch:
        threading.Thread(target=watch_and_rebuild, args=(resolved_project,), daemon=True).start()
        print(
            f"watching {resolved_project.content_dir}, "
            f"{resolved_project.templates_dir}, and {resolved_project.static_dir}"
        )

    with Server(("", port), handler) as httpd:
        print(f"serving {resolved_project.output_dir}/ at http://localhost:{port}")

        if test:
            threading.Timer(2.0, httpd.shutdown).start()

        httpd.serve_forever()
