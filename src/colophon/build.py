"""Build orchestration for a Colophon site.

Data flows from ``ProjectPaths`` through config/content loading, context
enrichment, asset copying, image resolution, template rendering, manifest
collection, and final output publication.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import shutil
import time
import uuid
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from slugify import slugify

from .collections import (
    attach_page_graph,
    enrich_post_context,
    is_post_context,
    should_list_page,
    sorted_pages,
    summarize_page,
)
from .content import (
    build_page_context,
    build_source_chain,
    discover_routes,
    load_post_sidebar,
    load_site_config,
    scan_content_tree,
)
from .errors import ColophonError, InternalBuildError, ProjectConfigError
from .expressions import expression_registry, resolve_page_context_expressions
from .images import copy_content_images, copy_referenced_assets, load_images, make_image_resolver
from .models import (
    BuildManifest,
    BuildMessage,
    BuildOptions,
    BuildResult,
    ManifestEntry,
    PageContext,
    ProjectPaths,
    RenderJob,
    SiteConfig,
    SourceFiles,
)
from .project import project_from_inputs
from .render import (
    make_environment,
    render_auxiliary_pages,
    render_template,
    route_to_output_path,
    select_template,
    tag_groups,
)
from .vendor import required_vendor_assets, validate_local_vendor_assets
from .version import __version__


MANIFEST_SCHEMA_VERSION = "1.0"


def reset_output(project: ProjectPaths) -> None:
    resolved_project = project

    remove_path(resolved_project.output_dir)
    resolved_project.output_dir.mkdir(parents=True)


def remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
        return

    if path.exists():
        path.unlink()


def normalize_build_time(value: dt.datetime | str | int | float | None = None) -> dt.datetime:
    if value is None:
        epoch = os.environ.get("SOURCE_DATE_EPOCH")
        return normalize_build_time(epoch) if epoch else dt.datetime.now(dt.UTC)

    if isinstance(value, dt.datetime):
        timestamp = value if value.tzinfo else value.replace(tzinfo=dt.UTC)
        return timestamp.astimezone(dt.UTC)

    if isinstance(value, int | float):
        return dt.datetime.fromtimestamp(value, dt.UTC)

    text = str(value).strip()

    if not text:
        raise ProjectConfigError("build_time must not be empty")

    try:
        return dt.datetime.fromtimestamp(float(text), dt.UTC)
    except ValueError:
        pass

    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProjectConfigError(f"invalid build_time {value!r}") from exc

    timestamp = parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.UTC)
    return timestamp.astimezone(dt.UTC)


def relative_to_or_absolute(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def output_relative(path: Path, project: ProjectPaths) -> str:
    return relative_to_or_absolute(path, project.output_dir)


def source_relative(path: Path | None, project: ProjectPaths) -> str | None:
    return relative_to_or_absolute(path, project.root) if path else None


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def file_entry(
    kind: str,
    output_path: Path,
    project: ProjectPaths,
    *,
    source_path: Path | None = None,
    url_path: str | None = None,
    route: str | None = None,
    template: str | None = None,
    source_chain: tuple[str, ...] = (),
    metadata: Mapping[str, Any] | None = None,
) -> ManifestEntry:
    return ManifestEntry(
        kind=kind,
        output_path=output_relative(output_path, project),
        source_path=source_relative(source_path, project),
        url_path=url_path,
        route=route,
        template=template,
        source_chain=source_chain,
        size=output_path.stat().st_size if output_path.exists() else 0,
        sha256=file_sha256(output_path) if output_path.exists() else "",
        metadata=dict(metadata or {}),
    )


def skipped_entry(path: str, reason: str) -> ManifestEntry:
    return ManifestEntry(
        kind="skipped",
        output_path=path,
        source_path=path,
        metadata={"reason": reason},
    )


def skipped_warning(path: str, reason: str) -> BuildMessage:
    return BuildMessage(
        level="warning",
        category="asset",
        message=f"skipped {path}: {reason}",
        path=path,
    )


def copied_entries(
    kind: str,
    copied: tuple[tuple[Path, Path], ...],
    project: ProjectPaths,
) -> tuple[ManifestEntry, ...]:
    return tuple(
        file_entry(kind, destination, project, source_path=source)
        for source, destination in copied
    )


def page_entry(job: RenderJob, project: ProjectPaths) -> ManifestEntry:
    kind = "post" if is_post_context(job.page_context) else "page"
    source_chain = tuple(
        source_relative(source.absolute_path, project) or source.content_path
        for source in job.page_context.source_chain
    )
    source_path = job.page_context.source_chain[-1].absolute_path if job.page_context.source_chain else None

    return file_entry(
        kind,
        job.output_path,
        project,
        source_path=source_path,
        url_path=job.route.url_path,
        route=job.route.url_path,
        template=job.template_file,
        source_chain=source_chain,
        metadata={
            "title": str(job.page_context.data.get("title") or ""),
            "slug": str(job.page_context.data.get("slug") or ""),
        },
    )


def auxiliary_entries(
    post_summaries: list[dict[str, Any]],
    project: ProjectPaths,
) -> dict[str, tuple[ManifestEntry, ...]]:
    posts_by_date = sorted_pages(post_summaries, "date desc")
    tags = tag_groups(posts_by_date)
    archive = (
        file_entry(
            "archive_page",
            project.output_dir / "archive" / "index.html",
            project,
            url_path="/archive/",
            route="/archive/",
            template="archive.html",
        ),
    )
    tag_pages = tuple(
        file_entry(
            "tag_page",
            project.output_dir / "tags" / slugify(tag) / "index.html",
            project,
            url_path=f"/tags/{slugify(tag)}/",
            route=f"/tags/{slugify(tag)}/",
            template="tag.html",
            metadata={"tag": tag, "post_count": len(posts)},
        )
        for tag, posts in sorted(tags.items())
    )
    feeds = (
        file_entry(
            "feed",
            project.output_dir / "feed.xml",
            project,
            url_path="/feed.xml",
            route="/feed.xml",
            template="feed.xml",
        ),
    )

    return {
        "archive_pages": archive,
        "tag_pages": tag_pages,
        "feeds": feeds,
    }


def generated_image_entries(project: ProjectPaths) -> tuple[ManifestEntry, ...]:
    root = project.output_dir / "images" / "generated"

    if not root.exists():
        return ()

    return tuple(
        file_entry(
            "generated_image",
            path,
            project,
            url_path=f"/images/generated/{path.name}",
        )
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )


def manifest_counts(manifest: BuildManifest) -> dict[str, int]:
    groups = (
        "pages",
        "posts",
        "archive_pages",
        "tag_pages",
        "feeds",
        "static_assets",
        "content_assets",
        "generated_images",
        "copied_files",
        "skipped_files",
        "warnings",
    )
    return {group: len(getattr(manifest, group)) for group in groups}


def copy_static_assets(project: ProjectPaths) -> tuple[tuple[Path, Path], ...]:
    resolved_project = project

    if not resolved_project.static_dir.exists():
        return ()

    copied: list[tuple[Path, Path]] = []

    for source in sorted(resolved_project.static_dir.rglob("*")):
        if not source.is_file():
            continue

        destination = resolved_project.output_dir / source.relative_to(resolved_project.static_dir)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append((source, destination))

    return tuple(copied)


def build_contexts(
    site_config: SiteConfig,
    content_index: SourceFiles,
    post_sidebar: Mapping[str, Any],
    project: ProjectPaths,
) -> list[PageContext]:
    registry = expression_registry(project)
    initial_contexts = [
        resolve_page_context_expressions(
            build_page_context(route, build_source_chain(route, content_index), site_config, project),
            project=project,
            registry=registry,
        )
        for route in discover_routes(content_index)
    ]
    page_summaries = [
        summarize_page(context)
        for context in initial_contexts
        if should_list_page(context)
    ]
    graph_contexts = [
        attach_page_graph(context, page_summaries)
        for context in initial_contexts
    ]
    post_summaries = [
        summarize_page(context)
        for context in graph_contexts
        if is_post_context(context) and should_list_page(context)
    ]

    return [
        enrich_post_context(context, post_sidebar, post_summaries, project, registry)
        for context in graph_contexts
    ]


def build_render_jobs(
    contexts: list[PageContext],
    site_config: SiteConfig,
    project: ProjectPaths,
) -> list[RenderJob]:
    return [
        RenderJob(
            route=context.route,
            template_file=select_template(context.route, context, site_config),
            page_context=context,
            output_path=route_to_output_path(context.route, project),
        )
        for context in contexts
    ]


def load_project_contexts(project: ProjectPaths) -> tuple[SiteConfig, list[PageContext]]:
    resolved_project = project
    site_config = load_site_config(resolved_project)
    post_sidebar = load_post_sidebar(resolved_project)
    content_index = scan_content_tree(resolved_project.content_dir)
    contexts = build_contexts(site_config, content_index, post_sidebar, resolved_project)
    return site_config, contexts


def resolve_required_vendor_assets(project: ProjectPaths) -> tuple[str, ...]:
    resolved_project = project
    site_config, contexts = load_project_contexts(resolved_project)
    return required_vendor_assets(resolved_project, site_config, contexts)


def temporary_output_project(project: ProjectPaths) -> ProjectPaths:
    project.output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir = (
        project.output_dir.parent
        / f".{project.output_dir.name}.tmp-{os.getpid()}-{uuid.uuid4().hex}"
    )
    remove_path(output_dir)
    output_dir.mkdir(parents=True)
    return replace(project, output_dir=output_dir)


def publish_output(build_project: ProjectPaths, final_project: ProjectPaths) -> None:
    if build_project.output_dir == final_project.output_dir:
        return

    remove_path(final_project.output_dir)
    shutil.move(build_project.output_dir.as_posix(), final_project.output_dir.as_posix())


def build_manifest(
    project: ProjectPaths,
    build_project: ProjectPaths,
    build_time: dt.datetime,
    render_jobs: list[RenderJob],
    post_summaries: list[dict[str, Any]],
    static_copied: tuple[tuple[Path, Path], ...],
    content_image_copied: tuple[tuple[Path, Path], ...],
    referenced_copied: tuple[tuple[Path, Path], ...],
    skipped_assets: tuple[str, ...],
) -> BuildManifest:
    rendered = tuple(page_entry(job, build_project) for job in render_jobs)
    pages = tuple(entry for entry in rendered if entry.kind == "page")
    posts = tuple(entry for entry in rendered if entry.kind == "post")
    static_assets = copied_entries("static_asset", static_copied, build_project)
    content_assets = (
        *copied_entries("content_image", content_image_copied, build_project),
        *copied_entries("content_asset", referenced_copied, build_project),
    )
    copied_files = (*static_assets, *content_assets)
    skipped_files = tuple(
        skipped_entry(asset, "source file does not exist")
        for asset in skipped_assets
    )
    warnings = tuple(
        skipped_warning(asset, "source file does not exist")
        for asset in skipped_assets
    )
    auxiliary = auxiliary_entries(post_summaries, build_project)

    return BuildManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        colophon_version=__version__,
        project_root=project.root.as_posix(),
        output_dir=project.output_dir.as_posix(),
        build_time=build_time.isoformat(),
        pages=pages,
        posts=posts,
        archive_pages=auxiliary["archive_pages"],
        tag_pages=auxiliary["tag_pages"],
        feeds=auxiliary["feeds"],
        static_assets=static_assets,
        content_assets=content_assets,
        generated_images=generated_image_entries(build_project),
        copied_files=copied_files,
        skipped_files=skipped_files,
        warnings=warnings,
        metadata={
            "content_dir": source_relative(project.content_dir, project),
            "templates_dir": source_relative(project.templates_dir, project),
            "static_dir": source_relative(project.static_dir, project),
        },
    )


def build_site(
    project: ProjectPaths,
    *,
    options: BuildOptions | None = None,
) -> BuildResult:
    started = time.perf_counter()
    resolved_project = project
    build_options = options or BuildOptions()
    build_time = normalize_build_time(build_options.build_time)
    build_project = temporary_output_project(resolved_project) if build_options.atomic else resolved_project
    manifest_path = Path(build_options.manifest_path) if build_options.manifest_path else None

    try:
        site_config, contexts = load_project_contexts(resolved_project)
        images = load_images(resolved_project)
        render_jobs = build_render_jobs(contexts, site_config, build_project)
        vendor_assets = required_vendor_assets(resolved_project, site_config, contexts)
        post_summaries = [
            summarize_page(context)
            for context in contexts
            if is_post_context(context) and should_list_page(context)
        ]

        validate_local_vendor_assets(resolved_project, vendor_assets)

        if not build_options.atomic:
            reset_output(build_project)

        static_copied = copy_static_assets(build_project)
        content_image_copied = copy_content_images(build_project)
        referenced_copied, skipped_assets = copy_referenced_assets(render_jobs, build_project)

        env = make_environment(
            site_config.data["site"],
            make_image_resolver(images, build_project),
            build_project,
            vendor_assets=vendor_assets,
        )

        for job in render_jobs:
            render_template(env, job)

        render_auxiliary_pages(
            env,
            site_config.data["site"],
            post_summaries,
            build_project,
            build_time=build_time,
        )

        manifest = build_manifest(
            resolved_project,
            build_project,
            build_time,
            render_jobs,
            post_summaries,
            static_copied,
            content_image_copied,
            referenced_copied,
            skipped_assets,
        )
        publish_output(build_project, resolved_project)
        result = BuildResult(
            project=resolved_project,
            output_dir=resolved_project.output_dir,
            manifest=manifest,
            warnings=manifest.warnings,
            duration_seconds=time.perf_counter() - started,
            counts=manifest_counts(manifest),
            manifest_path=manifest_path,
        )

        if manifest_path is not None:
            result.write_manifest(manifest_path)

        return result
    except ColophonError:
        if build_project.output_dir != resolved_project.output_dir:
            remove_path(build_project.output_dir)
        raise
    except Exception as exc:
        if build_project.output_dir != resolved_project.output_dir:
            remove_path(build_project.output_dir)
        raise InternalBuildError(f"unexpected build failure: {exc}") from exc


def build_project(
    project_path: Path | str = ".",
    *,
    config: Path | str | None = None,
    content: str | None = None,
    templates: str | None = None,
    static: str | None = None,
    output: str | None = None,
    manifest_path: Path | str | None = None,
    build_time: dt.datetime | str | int | float | None = None,
) -> BuildResult:
    project = project_from_inputs(
        project_path,
        config=config,
        content=content,
        templates=templates,
        static=static,
        output=output,
    )
    return build_site(
        project,
        options=BuildOptions(
            manifest_path=manifest_path,
            build_time=build_time,
        ),
    )
