"""Shared dataclasses and callable type aliases.

Subsystems pass immutable ``ProjectPaths``, content contexts, render jobs, and
deploy state through the pipeline instead of mutating global state.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any


MastodonPoster = Callable[[Mapping[str, Any], str, bool], dict[str, Any]]


TransportUploader = Callable[[Mapping[str, Any], Path, bool], list[str]]


@dataclass(frozen=True)
class VendorAssetOverride:
    enabled: bool | None = None
    local_path: str | None = None
    cdn_base: str | None = None
    required_files: tuple[str, ...] = ()
    cdn_files: tuple[tuple[str, str], ...] = ()
    dependencies: tuple[str, ...] = ()
    archive_url: str | None = None
    archive_prefix: str | None = None


@dataclass(frozen=True)
class VendorConfig:
    mode: str = "auto"
    local_dir: str = "vendor"
    required: tuple[str, ...] = ()
    assets: tuple[tuple[str, VendorAssetOverride], ...] = ()


@dataclass(frozen=True)
class ProjectPaths:
    root: Path
    content_dir: Path
    posts_dir: Path
    content_images_dir: Path
    templates_dir: Path
    static_dir: Path
    output_dir: Path
    deploy_config: Path
    site_configs: tuple[Path, ...]
    image_configs: tuple[Path, ...]
    post_sidebar_configs: tuple[Path, ...]
    watched_dirs: tuple[Path, ...]
    watched_files: tuple[Path, ...]
    python_modules: tuple[Path, ...] = ()
    vendor: VendorConfig = field(default_factory=VendorConfig)


def serializable_value(value: Any) -> Any:
    if isinstance(value, Path):
        return value.as_posix()

    if isinstance(value, dt.datetime):
        return value.isoformat()

    if is_dataclass(value):
        return {
            item.name: serializable_value(getattr(value, item.name))
            for item in fields(value)
        }

    if isinstance(value, Mapping):
        return {
            str(key): serializable_value(item)
            for key, item in value.items()
        }

    if isinstance(value, tuple | list):
        return [serializable_value(item) for item in value]

    if isinstance(value, frozenset | set):
        return [serializable_value(item) for item in sorted(value, key=str)]

    return value


@dataclass(frozen=True)
class BuildOptions:
    manifest_path: Path | str | None = None
    build_time: dt.datetime | str | int | float | None = None
    atomic: bool = True


@dataclass(frozen=True)
class BuildMessage:
    level: str
    category: str
    message: str
    path: str | None = None
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return serializable_value(self)


@dataclass(frozen=True)
class ManifestEntry:
    kind: str
    output_path: str
    source_path: str | None = None
    url_path: str | None = None
    route: str | None = None
    template: str | None = None
    source_chain: tuple[str, ...] = ()
    size: int = 0
    sha256: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return serializable_value(self)


@dataclass(frozen=True)
class BuildManifest:
    schema_version: str
    colophon_version: str
    project_root: str
    output_dir: str
    build_time: str
    pages: tuple[ManifestEntry, ...] = ()
    posts: tuple[ManifestEntry, ...] = ()
    archive_pages: tuple[ManifestEntry, ...] = ()
    tag_pages: tuple[ManifestEntry, ...] = ()
    feeds: tuple[ManifestEntry, ...] = ()
    static_assets: tuple[ManifestEntry, ...] = ()
    content_assets: tuple[ManifestEntry, ...] = ()
    generated_images: tuple[ManifestEntry, ...] = ()
    copied_files: tuple[ManifestEntry, ...] = ()
    skipped_files: tuple[ManifestEntry, ...] = ()
    warnings: tuple[BuildMessage, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return serializable_value(self)


@dataclass(frozen=True)
class BuildResult:
    project: ProjectPaths
    output_dir: Path
    manifest: BuildManifest
    warnings: tuple[BuildMessage, ...] = ()
    duration_seconds: float = 0.0
    counts: Mapping[str, int] = field(default_factory=dict)
    manifest_path: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_root": self.project.root.as_posix(),
            "output_dir": self.output_dir.as_posix(),
            "manifest": self.manifest.to_dict(),
            "warnings": [warning.to_dict() for warning in self.warnings],
            "duration_seconds": self.duration_seconds,
            "counts": dict(self.counts),
            "manifest_path": self.manifest_path.as_posix() if self.manifest_path else None,
        }

    def write_manifest(self, path: Path | str | None = None) -> Path:
        target = Path(path or self.manifest_path) if path or self.manifest_path else None

        if target is None:
            raise ValueError("manifest path is required")

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.manifest.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return target


@dataclass(frozen=True)
class SiteConfig:
    data: dict[str, Any]
    templates: dict[str, str]
    routes: list[dict[str, Any]]


@dataclass(frozen=True)
class Route:
    url_path: str


@dataclass(frozen=True)
class SourceFile:
    absolute_path: Path
    content_path: str
    kind: str


@dataclass(frozen=True)
class ExpressionContext:
    project: ProjectPaths
    route: "Route"
    source_file: SourceFile | None
    source_chain: tuple[SourceFile, ...]
    data: Mapping[str, Any]
    site: Mapping[str, Any]
    slots: Mapping[str, Any]
    article: str


ExpressionFunction = Callable[[], Any]


ExpressionContextFunction = Callable[[ExpressionContext], Any]


@dataclass(frozen=True)
class SourceFiles:
    source_files: tuple[SourceFile, ...]
    path_map: dict[str, SourceFile]

    @classmethod
    def from_files(cls, source_files: list[SourceFile]) -> "SourceFiles":
        return cls(
            source_files=tuple(source_files),
            path_map={source.content_path: source for source in source_files},
        )

    def by_content_path(self, content_path: str) -> SourceFile | None:
        return self.path_map.get(content_path)

    def by_kind(self, kind: str) -> list[SourceFile]:
        return [source for source in self.source_files if source.kind == kind]


@dataclass(frozen=True)
class ContentLayer:
    source_file: SourceFile
    route: Route
    data: dict[str, Any] = field(default_factory=dict)
    slots: dict[str, str] = field(default_factory=dict)
    assets: frozenset[str] = field(default_factory=frozenset)
    template: str | None = None


@dataclass(frozen=True)
class PageContext:
    route: Route
    data: dict[str, Any]
    slots: dict[str, str]
    assets: frozenset[str]
    template: str | None
    source_chain: tuple[SourceFile, ...]


@dataclass(frozen=True)
class RenderJob:
    route: Route
    template_file: str
    page_context: PageContext
    output_path: Path


@dataclass(frozen=True)
class DeployPostSelection:
    context: PageContext
    summary: dict[str, Any]
    source_file: SourceFile


@dataclass(frozen=True)
class DeployState:
    project: ProjectPaths
    config: dict[str, Any]
    target_name: str
    target_config: dict[str, Any]
    post_id: str | None
    dry_run: bool
    force_post: bool
    mastodon_poster: MastodonPoster
    transport_uploaders: Mapping[str, TransportUploader]
    site_config: SiteConfig | None = None
    contexts: tuple[PageContext, ...] = ()
    selection: DeployPostSelection | None = None
    status_text: str = ""
    status_url: str = ""
    posted: bool = False
    uploaded: bool = False
    upload_actions: tuple[str, ...] = ()
