"""Page summary, collection, and post-enrichment helpers.

Page contexts flow in after content loading; this module derives listing data,
page graphs, related posts, and post-only extras before rendering.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Any

from .expressions import resolve_page_context_expressions
from .mastodon import load_mastodon_comments
from .models import ExpressionFunction, PageContext, ProjectPaths
from .utils import copy_value, deep_merge, normalize_route, route_parts


DEFAULT_COLLECTIONS = {
    "posts": {
        "under": "/posts/",
        "sort": "date desc",
    },
}


def route_section(route: str) -> str:
    parts = route_parts(route)
    return parts[0] if parts else ""


def summarize_page(context: PageContext) -> dict[str, Any]:
    data = context.data
    route = context.route.url_path
    parts = route_parts(route)
    source = context.source_chain[-1].content_path if context.source_chain else ""

    return {
        "route": route,
        "url": route,
        "source_path": source,
        "section": route_section(route),
        "depth": len(parts),
        "slug": data.get("slug") or (parts[-1] if parts else ""),
        "title": data.get("title") or data.get("meta", {}).get("title") or route,
        "date": data.get("date"),
        "summary": data.get("summary") or data.get("description") or data.get("meta", {}).get("description") or "",
        "tags": data.get("tags") or [],
        "template": data.get("template") or context.template,
        "reading_minutes": data.get("reading_minutes"),
        "cover": data.get("cover") or data.get("cover_image") or "",
        "cover_image": data.get("cover_image") or data.get("cover") or "",
        "sidebar_image": data.get("sidebar_image") or "",
        "image": data.get("image") or data.get("cover") or data.get("cover_image") or "",
        "data": copy_value(data),
    }


def should_list_page(context: PageContext) -> bool:
    return context.data.get("draft") is not True and context.data.get("listed", True) is not False


def page_is_under(page: Mapping[str, Any], prefix: str) -> bool:
    normalized = normalize_route(prefix)
    route = str(page["route"])
    return route.startswith(normalized) and route != normalized


def collection_sort_key(page: Mapping[str, Any], sort: str) -> Any:
    if sort.startswith("date"):
        return page.get("date") or dt.date.min

    if sort.startswith("title"):
        return str(page.get("title") or "").lower()

    return page.get("route") or ""


def sorted_pages(pages: list[dict[str, Any]], sort: str) -> list[dict[str, Any]]:
    return sorted(
        pages,
        key=lambda page: collection_sort_key(page, sort),
        reverse=sort.endswith("desc"),
    )


def build_collections(
    definitions: Mapping[str, Any],
    all_pages: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    merged_definitions = deep_merge(DEFAULT_COLLECTIONS, definitions)

    def select_items(query: Mapping[str, Any]) -> list[dict[str, Any]]:
        items = list(all_pages)

        if "under" in query:
            items = [page for page in items if page_is_under(page, str(query["under"]))]

        if "template" in query:
            items = [page for page in items if page.get("template") == query["template"]]

        if "tag" in query:
            items = [page for page in items if query["tag"] in page.get("tags", [])]

        sort = str(query.get("sort") or "")

        if sort:
            items = sorted_pages(items, sort)

        if "limit" in query:
            items = items[: int(query["limit"])]

        return [copy_value(item) for item in items]

    return {
        name: select_items(query if isinstance(query, Mapping) else {})
        for name, query in merged_definitions.items()
    }


def child_pages(route: str, all_pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    parent_parts = route_parts(route)

    return [
        copy_value(page)
        for page in all_pages
        if route_parts(page["route"])[: len(parent_parts)] == parent_parts
        and len(route_parts(page["route"])) == len(parent_parts) + 1
    ]


def attach_page_graph(
    context: PageContext,
    all_pages: list[dict[str, Any]],
) -> PageContext:
    route = context.route.url_path
    section = route_section(route)
    page_graph = {
        "all": [copy_value(page) for page in all_pages],
        "children": child_pages(route, all_pages),
        "section": [
            copy_value(page)
            for page in all_pages
            if page.get("section") == section and page["route"] != route
        ],
    }
    collections = build_collections(context.data.get("collections") or {}, all_pages)

    return PageContext(
        route=context.route,
        data=deep_merge(context.data, {"pages": page_graph, "collections": collections}),
        slots=context.slots,
        assets=context.assets,
        template=context.template,
        source_chain=context.source_chain,
    )


def is_post_context(context: PageContext) -> bool:
    parts = route_parts(context.route.url_path)
    return len(parts) >= 2 and parts[0] == "posts"


def related_posts_for(
    context: PageContext,
    post_summaries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    current_slug = context.data.get("slug")
    current_tags = set(context.data.get("tags") or [])
    requested = context.data.get("related") or []

    if requested:
        requested_slugs = [str(slug) for slug in requested]
        by_slug = {post["slug"]: post for post in post_summaries}
        return [copy_value(by_slug[slug]) for slug in requested_slugs if slug in by_slug]

    return [
        copy_value(post)
        for post in post_summaries
        if post.get("slug") != current_slug and current_tags.intersection(post.get("tags") or [])
    ][:3]


def enrich_post_context(
    context: PageContext,
    post_sidebar: Mapping[str, Any],
    post_summaries: list[dict[str, Any]],
    project: ProjectPaths | None = None,
    registry: Mapping[str, ExpressionFunction] | None = None,
) -> PageContext:
    if not is_post_context(context):
        return context

    sidebar = context.data.get("sidebar") or copy_value(post_sidebar)
    site_mastodon = (context.data.get("site") or {}).get("mastodon") or {}
    data = deep_merge(
        context.data,
        {
            "sidebar": sidebar,
            "related": related_posts_for(context, post_summaries),
            "mastodon_comments": load_mastodon_comments(
                context.data.get("mastodon_comments"),
                site_mastodon,
            ),
        },
    )

    return resolve_page_context_expressions(
        PageContext(
            route=context.route,
            data=data,
            slots=context.slots,
            assets=context.assets,
            template=context.template,
            source_chain=context.source_chain,
        ),
        project=project,
        registry=registry,
    )
