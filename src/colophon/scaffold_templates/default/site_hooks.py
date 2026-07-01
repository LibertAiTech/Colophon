"""Example trusted hook module copied into scaffolded sites.

The scaffold config loads ``YAML_FUNCTIONS`` for site-level expressions and
``YAML_CONTEXT_FUNCTIONS`` for page/frontmatter expressions that need the
current route, source file, rendered article, or project paths.
"""

from __future__ import annotations

import datetime as dt
import os
import re
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from colophon import ExpressionContext


def build_revision() -> str:
    return os.environ.get("COLOPHON_BUILD_REVISION") or os.environ.get("GITHUB_SHA", "local")


def blogroll_links() -> list[dict[str, str]]:
    return [
        {"label": "Project repository", "href": "https://github.com/AeonCypher/Colophon"},
        {"label": "Archive", "href": "/archive/"},
        {"label": "Template variables", "href": "/template-variables/"},
        {"label": "Deploy dry-run", "href": "/deploy/"},
    ]


def deploy_password() -> str:
    return os.environ.get("EXAMPLE_FTP_PASSWORD", "")


def source_mtime(path: Path | None) -> dt.date:
    if path is None or not path.exists():
        return dt.date.today()

    return dt.datetime.fromtimestamp(path.stat().st_mtime).date()


def article_text(context: ExpressionContext) -> str:
    return BeautifulSoup(context.article, "html.parser").get_text(" ", strip=True)


def first_paragraph(context: ExpressionContext) -> str:
    soup = BeautifulSoup(context.article, "html.parser")
    paragraph = next(
        (
            tag.get_text(" ", strip=True)
            for tag in soup.find_all("p")
            if tag.get_text(" ", strip=True)
        ),
        "",
    )
    return paragraph or article_text(context)


def get_date(context: ExpressionContext) -> str:
    return source_mtime(context.source_file.absolute_path if context.source_file else None).isoformat()


def last_updated(context: ExpressionContext) -> str:
    dates = [
        source_mtime(source.absolute_path)
        for source in context.source_chain
    ]
    return max(dates or [dt.date.today()]).isoformat()


def read_time(context: ExpressionContext) -> int:
    words = re.findall(r"\w+", article_text(context))
    return max(1, round(len(words) / 225)) if words else 1


def routable_content_files(context: ExpressionContext) -> tuple[Path, ...]:
    exts = {".md", ".yaml", ".yml", ".json"}
    ignored = {"site", "images", "post-sidebar", "deploy"}
    return tuple(
        path
        for path in sorted(context.project.content_dir.rglob("*"))
        if path.is_file()
        and path.suffix.lower() in exts
        and path.stem not in ignored
        and "images" not in path.relative_to(context.project.content_dir).parts
    )


def site_stats(context: ExpressionContext) -> dict[str, Any]:
    files = routable_content_files(context)
    posts = [
        path
        for path in files
        if "posts" in path.relative_to(context.project.content_dir).parts
    ]
    return {"content_files": len(files), "posts": len(posts)}


def recently_changed_pages(context: ExpressionContext) -> list[dict[str, str]]:
    return [
        {
            "path": path.relative_to(context.project.content_dir).as_posix(),
            "updated": source_mtime(path).isoformat(),
        }
        for path in sorted(routable_content_files(context), key=lambda item: item.stat().st_mtime, reverse=True)[:5]
    ]


YAML_FUNCTIONS = {
    "build_revision": build_revision,
    "blogroll_links": blogroll_links,
    "deploy_password": deploy_password,
}


YAML_CONTEXT_FUNCTIONS = {
    "first_paragraph": first_paragraph,
    "get_date": get_date,
    "last_updated": last_updated,
    "read_time": read_time,
    "recently_changed_pages": recently_changed_pages,
    "site_stats": site_stats,
}
