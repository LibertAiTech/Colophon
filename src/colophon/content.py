"""Content discovery and page-context construction.

Content files flow from filesystem scans into routes, source chains, normalized
layers, and initial ``PageContext`` values for collection and render stages.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import frontmatter

from .expressions import expression_registry, resolve_site_expressions, resolve_yaml_expression_values
from .markdown import estimate_reading_minutes, render_markdown
from .mastodon import DEFAULT_MASTODON, load_mastodon_site_config
from .models import ContentLayer, PageContext, ProjectPaths, Route, SiteConfig, SourceFile, SourceFiles
from .utils import copy_value, deep_merge, load_first_yaml, load_wrapped_yaml, mapping, parse_date, read_yaml, route_parts


YAML_EXTS = {".yaml", ".yml", ".json"}

MARKDOWN_EXTS = {".md"}

CONFIG_NAMES = {
    "site",
    "images",
    "post-sidebar",
    "deploy",
}
STATIC_PAGE_DIR = "pages"

SUPPORT_CONFIGS = {f"{name}{ext}" for name in CONFIG_NAMES for ext in YAML_EXTS}
INDEX_NAMES = {f"index{ext}" for ext in YAML_EXTS | MARKDOWN_EXTS}

DEFAULT_SITE = {
    "title": "COLOPHON",
    "subtitle": "",
    "description": "",
    "url": "",
    "author": "Your Name",
    "signal_line": "",
    "mastodon": DEFAULT_MASTODON,
    "nav": [],
    "sections": {},
    "footer": {},
}


DEFAULT_TEMPLATES = {
    "default": "index.html",
    "page": "index.html",
    "post": "post.html",
    "static": "simple.html",
}

DEFAULT_ROUTES = [
    {"match": "/posts/**", "template": "post"},
    {"match": "/**", "template": "page"},
]

def content_kind(path: Path) -> str:
    suffix = path.suffix.lower()

    if suffix in YAML_EXTS:
        return "yaml"

    if suffix in MARKDOWN_EXTS:
        return "markdown"

    return "asset"


def is_support_config(source_file: SourceFile) -> bool:
    return source_file.content_path in SUPPORT_CONFIGS


def is_static_page_source(source_file: SourceFile) -> bool:
    parts = Path(source_file.content_path).parts
    return bool(parts) and parts[0] == STATIC_PAGE_DIR


def routable_content_path(source_file: SourceFile) -> Path:
    path = Path(source_file.content_path)
    parts = path.parts

    if parts and parts[0] == STATIC_PAGE_DIR:
        return Path(*parts[1:])

    return path


def read_source_data(source_file: SourceFile) -> dict[str, Any]:
    if source_file.kind == "markdown":
        return frontmatter.load(source_file.absolute_path.as_posix()).metadata

    if source_file.kind == "yaml":
        return read_yaml(source_file.absolute_path)

    return {}


def route_for_content_file(source_file: SourceFile) -> Route | None:
    if source_file.kind not in {"yaml", "markdown"} or is_support_config(source_file):
        return None

    path = routable_content_path(source_file)

    if path.name in INDEX_NAMES:
        parent = path.parent.as_posix()
        return Route("/") if parent == "." else Route(f"/{parent}/")

    return Route(f"/{path.with_suffix('').as_posix()}/")


def source_file_wants_route(source_file: SourceFile) -> bool:
    if source_file.kind not in {"yaml", "markdown"} or is_support_config(source_file):
        return False

    data = read_source_data(source_file)
    parts = Path(source_file.content_path).parts

    if parts and parts[0] == "images":
        return data.get("render") is True

    if data.get("render") is False:
        return False

    if is_static_page_source(source_file):
        return True

    if source_file.kind == "markdown":
        return True

    return Path(source_file.content_path).name in INDEX_NAMES or bool(
        data.get("render") is True or data.get("template")
    )


def scan_content_tree(root: Path | None = None) -> SourceFiles:
    root = root or CONTENT
    source_files = [
        SourceFile(
            absolute_path=path,
            content_path=path.relative_to(root).as_posix(),
            kind=content_kind(path),
        )
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.name.startswith(".")
    ]

    return SourceFiles.from_files(source_files)


def discover_routes(content_index: SourceFiles) -> list[Route]:
    routes = {
        route
        for source_file in content_index.by_kind("yaml") + content_index.by_kind("markdown")
        if source_file_wants_route(source_file)
        for route in [route_for_content_file(source_file)]
        if route is not None
    }

    return sorted(routes, key=lambda route: route.url_path)


def add_existing(
    content_index: SourceFiles,
    candidates: list[SourceFile],
    content_path: str,
) -> None:
    source = content_index.by_content_path(content_path)

    if source is not None and route_for_content_file(source) is not None:
        candidates.append(source)


def build_source_chain(route: Route, content_index: SourceFiles) -> tuple[SourceFile, ...]:
    candidates: list[SourceFile] = []
    parts = route_parts(route.url_path)

    def add_index(prefix: str) -> None:
        prefix = prefix.rstrip("/") or ""
        paths = [f"{prefix}/{name}" for name in INDEX_NAMES] if prefix else INDEX_NAMES

        for path in paths:
            add_existing(content_index, candidates, path)

    def add_direct(prefix: str) -> None:
        for suffix in [".yaml", ".yml", ".md"]:
            add_existing(content_index, candidates, f"{prefix}{suffix}")

    def add_static_page_index(prefix: str) -> None:
        prefix = prefix.rstrip("/") or ""
        paths = [f"{STATIC_PAGE_DIR}/{prefix}/{name}" for name in INDEX_NAMES] if prefix else [f"{STATIC_PAGE_DIR}/{name}" for name in INDEX_NAMES]

        for path in paths:
            add_existing(content_index, candidates, path)

    def add_static_page_direct(prefix: str) -> None:
        if not prefix:
            return

        for suffix in [".yaml", ".yml", ".md"]:
            add_existing(content_index, candidates, f"{STATIC_PAGE_DIR}/{prefix}{suffix}")

    if not parts:
        add_index("")
        add_static_page_index("")
        return tuple(candidates)

    for index in range(len(parts)):
        prefix = "/".join(parts[: index + 1])
        add_direct(prefix)
        add_index(prefix)
        add_static_page_direct(prefix)
        add_static_page_index(prefix)

    return tuple(candidates)


def discover_colocated_assets(source_file: SourceFile, project: ProjectPaths) -> frozenset[str]:
    resolved_project = project
    assets = {
        path.relative_to(resolved_project.content_dir).as_posix()
        for path in source_file.absolute_path.parent.iterdir()
        if path.is_file() and content_kind(path) == "asset"
    }

    return frozenset(assets)


def fallback_title(source_file: SourceFile, route: Route) -> str:
    if route.url_path == "/":
        return "Home"

    parts = route_parts(route.url_path)
    stem = parts[-1] if parts else Path(source_file.content_path).stem
    return stem.replace("-", " ").title()


def default_template_for_source(source_file: SourceFile) -> str | None:
    return "static" if is_static_page_source(source_file) else None


def normalize_layer_data(
    raw_data: Mapping[str, Any],
    source_file: SourceFile,
    route: Route,
    article_html: str | None = None,
    toc: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    reserved = {"references", "bindings", "slot", "render"}
    data = {key: copy_value(value) for key, value in raw_data.items() if key not in reserved}
    parsed_date = parse_date(data.get("date"))

    if parsed_date:
        data["date"] = parsed_date

    if source_file.kind == "markdown" or is_static_page_source(source_file):
        title = data.get("title") or fallback_title(source_file, route)
        parts = route_parts(route.url_path)
        defaults = {
            "title": title,
            "slug": parts[-1] if parts else "",
            "url": route.url_path,
            "summary": "",
            "tags": [],
            "toc": toc or [],
        }
        markdown_defaults = (
            {"reading_minutes": estimate_reading_minutes(article_html or "")}
            if source_file.kind == "markdown"
            else {}
        )
        data = deep_merge(deep_merge(defaults, markdown_defaults), data)

    return data


def load_content_layer(
    source_file: SourceFile,
    target_route: Route,
    project: ProjectPaths,
) -> ContentLayer:
    route = route_for_content_file(source_file)

    if route is None:
        raise ValueError(f"{source_file.content_path} is not routable")

    if source_file.kind == "yaml":
        raw_data = read_yaml(source_file.absolute_path)
        bindings = raw_data.get("bindings") if isinstance(raw_data.get("bindings"), Mapping) else {}
        template = (
            str(
                bindings.get("template")
                or raw_data.get("template")
                or default_template_for_source(source_file)
                or ""
            )
            or None
        )

        return ContentLayer(
            source_file=source_file,
            route=route,
            data=normalize_layer_data(raw_data, source_file, route),
            assets=discover_colocated_assets(source_file, project),
            template=template,
        )

    post = frontmatter.loads(source_file.absolute_path.read_text(encoding="utf-8"))
    metadata = post.metadata
    markdown_body = post.content
    article_html, toc = render_markdown(markdown_body)
    slot_name = str(metadata.get("slot") or "article")
    bindings = metadata.get("bindings") if isinstance(metadata.get("bindings"), Mapping) else {}
    template = (
        str(
            bindings.get("template")
            or metadata.get("template")
            or default_template_for_source(source_file)
            or ""
        )
        or None
    )

    return ContentLayer(
        source_file=source_file,
        route=route,
        data=normalize_layer_data(metadata, source_file, route, article_html, toc),
        slots={slot_name: article_html},
        assets=discover_colocated_assets(source_file, project),
        template=template,
    )


def merge_layer_into_page(page_context: PageContext, layer: ContentLayer) -> PageContext:
    return PageContext(
        route=page_context.route,
        data=deep_merge(page_context.data, layer.data),
        slots=(
            deep_merge(page_context.slots, layer.slots)
            if layer.route == page_context.route
            else copy_value(page_context.slots)
        ),
        assets=frozenset(set(page_context.assets) | set(layer.assets)),
        template=layer.template or page_context.template,
        source_chain=page_context.source_chain,
    )


def build_page_context(
    route: Route,
    source_chain: tuple[SourceFile, ...],
    site_config: SiteConfig,
    project: ProjectPaths,
) -> PageContext:
    page_context = PageContext(
        route=route,
        data=copy_value(site_config.data),
        slots={},
        assets=frozenset(),
        template=None,
        source_chain=source_chain,
    )

    for source_file in source_chain:
        page_context = merge_layer_into_page(
            page_context,
            load_content_layer(source_file, route, project),
        )

    return page_context


def load_site_config(project: ProjectPaths) -> SiteConfig:
    resolved_project = project
    registry = expression_registry(resolved_project)
    raw = resolve_yaml_expression_values(
        load_first_yaml(list(resolved_project.site_configs)),
        registry=registry,
        path="site",
    )
    raw_site = mapping(raw.get("site"), "site")
    site = deep_merge(DEFAULT_SITE, raw_site)
    site = deep_merge(
        site,
        {"mastodon": load_mastodon_site_config(raw_site.get("mastodon"))},
    )
    site = resolve_site_expressions(site, registry=registry)

    return SiteConfig(
        data={"site": site},
        templates=deep_merge(
            DEFAULT_TEMPLATES,
            raw.get("templates") or {},
        ),
        routes=copy_value(raw.get("routes") or DEFAULT_ROUTES),
    )


def load_post_sidebar(project: ProjectPaths) -> dict[str, Any]:
    resolved_project = project
    return deep_merge(
        {"cards": []},
        mapping(
            resolve_yaml_expression_values(
                load_wrapped_yaml(list(resolved_project.post_sidebar_configs)),
                registry=expression_registry(resolved_project),
                path="post_sidebar",
            ),
            "post_sidebar",
        ),
    )
