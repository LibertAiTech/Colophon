"""Browser vendor asset registry, resolution, and downloads.

Project vendor config flows into immutable overrides, data-driven asset
dependency expansion, template URL helpers, local preflight checks, and the
explicit download command.
"""

from __future__ import annotations

import io
import tarfile
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.request import urlopen

from .errors import ProjectConfigError
from .models import PageContext, ProjectPaths, SiteConfig, VendorAssetOverride, VendorConfig
from .utils import mapping


VENDOR_MODES = {"auto", "cdn", "local"}


@dataclass(frozen=True)
class VendorAsset:
    name: str
    local_path: str
    required_files: tuple[str, ...]
    cdn_base: str
    license_files: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    cdn_files: tuple[tuple[str, str], ...] = ()
    archive_url: str | None = None
    archive_prefix: str | None = None


BUILTIN_VENDOR_ASSETS = {
    "webawesome": VendorAsset(
        name="webawesome",
        local_path="webawesome/v3.8.0",
        required_files=(
            "webawesome.loader.js",
            "styles/themes/awesome.css",
            "styles/utilities.css",
        ),
        cdn_base="https://ka-f.webawesome.com/webawesome@3.8.0",
        archive_url="https://registry.npmjs.org/@awesome.me/webawesome/-/webawesome-3.8.0.tgz",
        archive_prefix="package/dist/",
    ),
    "dompurify": VendorAsset(
        name="dompurify",
        local_path="dompurify",
        required_files=("purify.min.js",),
        license_files=("LICENSE",),
        cdn_base="https://cdn.jsdelivr.net/npm/dompurify@3.2.6/dist",
        cdn_files=(
            ("LICENSE", "https://cdn.jsdelivr.net/npm/dompurify@3.2.6/LICENSE"),
        ),
    ),
    "font-awesome": VendorAsset(
        name="font-awesome",
        local_path="font-awesome/4.7.0",
        required_files=(
            "css/font-awesome.min.css",
            "fonts/fontawesome-webfont.eot",
            "fonts/fontawesome-webfont.svg",
            "fonts/fontawesome-webfont.ttf",
            "fonts/fontawesome-webfont.woff",
            "fonts/fontawesome-webfont.woff2",
        ),
        license_files=("LICENSE.txt",),
        cdn_base="https://cdn.jsdelivr.net/npm/font-awesome@4.7.0",
    ),
    "mastodon-comments": VendorAsset(
        name="mastodon-comments",
        local_path="mastodon-comments",
        required_files=("mastodon-comments.js",),
        license_files=("LICENSE",),
        dependencies=("dompurify", "font-awesome"),
        cdn_base="https://cdn.jsdelivr.net/gh/dpecos/mastodon-comments@main",
    ),
    "mastodon-embed-timeline": VendorAsset(
        name="mastodon-embed-timeline",
        local_path="mastodon-embed-timeline",
        required_files=("mastodon-timeline.min.css", "mastodon-timeline.umd.js"),
        license_files=("LICENSE",),
        cdn_base="https://cdn.jsdelivr.net/npm/@idotj/mastodon-embed-timeline@4.8.2/dist",
        cdn_files=(
            (
                "LICENSE",
                "https://cdn.jsdelivr.net/npm/@idotj/mastodon-embed-timeline@4.8.2/LICENSE",
            ),
        ),
    ),
}


ByteFetcher = Callable[[str], bytes]


def validate_name(value: Any, path: str) -> str:
    name = value.strip()
    if not name:
        raise ProjectConfigError(f"{path} must not be empty")

    return name


def validate_names(value: Any, path: str) -> tuple[str, ...]:
    values = value or ()
    return tuple(
        dict.fromkeys(
            name
            for name in (validate_name(item, f"{path}[]") for item in values)
        )
    )


def relative_posix_path(value: Any, *, label: str) -> str:
    text = str(value or "").strip().strip("/")
    path = PurePosixPath(text)

    if not text or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ProjectConfigError(f"{label} must be a relative POSIX path: {value!r}")

    return path.as_posix()


def validate_file_urls(value: Any, path: str) -> tuple[tuple[str, str], ...]:
    raw = mapping(value, path)
    return tuple(
        sorted(
            (
                relative_posix_path(relative_path, label="vendor asset file"),
                validate_name(url, f"{path}.{relative_path}"),
            )
            for relative_path, url in raw.items()
        )
    )


def load_vendor_asset_override(value: Any, path: str) -> VendorAssetOverride:
    raw = mapping(value, path)
    cdn_files = (
        validate_file_urls(raw.get("cdn_files"), f"{path}.cdn_files")
        + validate_file_urls(raw.get("files"), f"{path}.files")
    )
    required_files = validate_names(raw.get("required_files"), f"{path}.required_files")
    local_path = raw.get("local_path") or ""
    cdn_base = raw.get("cdn_base") or ""
    archive_prefix = raw.get("archive_prefix") or ""

    return VendorAssetOverride(
        enabled=raw.get("enabled"),
        local_path=(
            relative_posix_path(local_path, label="vendor asset local_path")
            if local_path
            else None
        ),
        cdn_base=cdn_base.rstrip("/") if cdn_base else None,
        required_files=tuple(
            relative_posix_path(path, label="vendor asset required file")
            for path in required_files
        ),
        cdn_files=tuple(dict(cdn_files).items()),
        dependencies=validate_names(raw.get("dependencies"), f"{path}.dependencies"),
        archive_url=raw.get("archive_url") or None,
        archive_prefix=(
            archive_prefix.lstrip("/")
            if archive_prefix
            else None
        ),
    )


def load_vendor_config(raw_config: Any) -> VendorConfig:
    raw = mapping(raw_config, "vendor")
    if "require" in raw:
        raise ProjectConfigError("vendor.require is not supported; use vendor.required")

    mode = (raw.get("mode") or "auto").strip().lower()

    if mode not in VENDOR_MODES:
        raise ProjectConfigError(
            f"vendor.mode must be one of {', '.join(sorted(VENDOR_MODES))}: {mode}"
        )

    raw_assets = mapping(raw.get("assets"), "vendor.assets")
    assets = tuple(
        sorted(
            (
                validate_name(name, "vendor.assets key"),
                load_vendor_asset_override(value, f"vendor.assets.{name}"),
            )
            for name, value in raw_assets.items()
        )
    )

    return VendorConfig(
        mode=mode,
        local_dir=relative_posix_path(
            raw.get("local_dir") or "vendor",
            label="vendor.local_dir",
        ),
        required=validate_names(raw.get("required"), "vendor.required"),
        assets=assets,
    )


def vendor_override_map(config: VendorConfig) -> dict[str, VendorAssetOverride]:
    return dict(config.assets)


def configured_vendor_asset(config: VendorConfig, name: str) -> VendorAsset:
    overrides = vendor_override_map(config)
    override = overrides.get(name, VendorAssetOverride())
    base = BUILTIN_VENDOR_ASSETS.get(
        name,
        VendorAsset(
            name=name,
            local_path=override.local_path or name,
            required_files=override.required_files,
            cdn_base=override.cdn_base or "",
            dependencies=override.dependencies,
            cdn_files=override.cdn_files,
            archive_url=override.archive_url,
            archive_prefix=override.archive_prefix,
        ),
    )

    return replace(
        base,
        local_path=override.local_path or base.local_path,
        required_files=override.required_files or base.required_files,
        cdn_base=(override.cdn_base or base.cdn_base).rstrip("/"),
        dependencies=override.dependencies or base.dependencies,
        cdn_files=tuple(dict(base.cdn_files + override.cdn_files).items()),
        archive_url=override.archive_url or base.archive_url,
        archive_prefix=override.archive_prefix or base.archive_prefix,
    )


def vendor_asset_enabled(config: VendorConfig, name: str) -> bool:
    override = vendor_override_map(config).get(name)
    return override.enabled is not False if override else True


def explicitly_required_vendor_assets(config: VendorConfig) -> tuple[str, ...]:
    enabled_overrides = (
        name
        for name, override in config.assets
        if override.enabled is True
    )
    return tuple(dict.fromkeys((*config.required, *enabled_overrides)))


def expand_vendor_assets(names: Iterable[str], config: VendorConfig) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []

    def visit(name: str) -> None:
        if name in seen or not vendor_asset_enabled(config, name):
            return

        seen.add(name)
        asset = configured_vendor_asset(config, name)
        for dependency in asset.dependencies:
            visit(dependency)
        ordered.append(name)

    for name in names:
        visit(name)

    return tuple(ordered)


def page_uses_mastodon_timeline_data(context: Mapping[str, Any]) -> bool:
    mastodon = context["site"].get("mastodon") or {}
    timeline = mastodon.get("timeline") or {}
    sidebar = context.get("sidebar") or {}
    cards = sidebar.get("cards") or ()

    return bool(timeline.get("enabled")) and any(
        isinstance(card, Mapping) and card.get("type") == "mastodon_timeline"
        for card in cards
    )


def content_required_vendor_assets(
    site_config: SiteConfig,
    contexts: Iterable[PageContext],
) -> tuple[str, ...]:
    context_names = tuple(
        name
        for context in contexts
        for name in (
            ("mastodon-comments",)
            if (context.data.get("mastodon_comments") or {}).get("enabled")
            else ()
        )
        + (
            ("mastodon-embed-timeline",)
            if page_uses_mastodon_timeline_data(context.data)
            else ()
        )
    )
    site_vendor = site_config.data["site"].get("vendor") or {}
    site_required = validate_names(site_vendor.get("required"), "site.vendor.required")

    return tuple(dict.fromkeys((*site_required, *context_names)))


def required_vendor_assets(
    project: ProjectPaths,
    site_config: SiteConfig,
    contexts: Iterable[PageContext],
) -> tuple[str, ...]:
    requested = (
        *explicitly_required_vendor_assets(project.vendor),
        *content_required_vendor_assets(site_config, contexts),
    )
    return expand_vendor_assets(requested, project.vendor)


def vendor_local_root(project: ProjectPaths, asset: VendorAsset) -> Path:
    return project.static_dir / project.vendor.local_dir / asset.local_path


def vendor_local_file(project: ProjectPaths, asset: VendorAsset, relative_path: str) -> Path:
    return vendor_local_root(project, asset) / relative_posix_path(
        relative_path,
        label="vendor file",
    )


def vendor_asset_has_required_files(project: ProjectPaths, name: str) -> bool:
    asset = configured_vendor_asset(project.vendor, name)
    return all(
        vendor_local_file(project, asset, path).exists()
        for path in asset.required_files
    )


def missing_vendor_files(project: ProjectPaths, names: Iterable[str]) -> tuple[Path, ...]:
    return tuple(
        path
        for name in names
        for asset in [configured_vendor_asset(project.vendor, name)]
        for relative_path in asset.required_files
        for path in [vendor_local_file(project, asset, relative_path)]
        if not path.exists()
    )


def validate_local_vendor_assets(project: ProjectPaths, names: Iterable[str]) -> None:
    missing = missing_vendor_files(project, names)

    if project.vendor.mode == "local" and missing:
        preview = ", ".join(path.as_posix() for path in missing[:5])
        suffix = " ..." if len(missing) > 5 else ""
        raise ProjectConfigError(
            "missing local vendor assets: "
            f"{preview}{suffix}; run `colophon vendor download --config colophon.yml`"
        )


def cdn_file_url(asset: VendorAsset, relative_path: str) -> str:
    path = relative_posix_path(relative_path, label="vendor CDN file")
    explicit = dict(asset.cdn_files).get(path)

    if explicit:
        return explicit

    if not asset.cdn_base:
        raise ProjectConfigError(f"vendor asset has no CDN base: {asset.name}")

    return f"{asset.cdn_base}/{path}"


def local_vendor_url(project: ProjectPaths, asset: VendorAsset, relative_path: str = "") -> str:
    parts = [project.vendor.local_dir, asset.local_path]
    if relative_path:
        parts.append(relative_posix_path(relative_path, label="vendor URL path"))

    return "/" + "/".join(part.strip("/") for part in parts if part)


def cdn_vendor_url(asset: VendorAsset, relative_path: str = "") -> str:
    return cdn_file_url(asset, relative_path) if relative_path else asset.cdn_base


def vendor_url_for(
    project: ProjectPaths,
    active_names: Iterable[str],
    name: str,
    relative_path: str = "",
) -> str:
    asset = configured_vendor_asset(project.vendor, name)
    use_local = project.vendor.mode == "local" or (
        project.vendor.mode == "auto"
        and vendor_asset_has_required_files(project, name)
    )

    return (
        local_vendor_url(project, asset, relative_path)
        if use_local
        else cdn_vendor_url(asset, relative_path)
    )


def default_fetch_bytes(url: str) -> bytes:
    with urlopen(url) as response:
        return response.read()


def unique_paths(*groups: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(path for group in groups for path in group))


def download_file_entries(asset: VendorAsset) -> tuple[tuple[str, str], ...]:
    paths = unique_paths(asset.required_files, asset.license_files, dict(asset.cdn_files))
    return tuple((path, cdn_file_url(asset, path)) for path in paths)


def safe_archive_member_path(name: str, prefix: str) -> Path | None:
    if not name.startswith(prefix):
        return None

    relative = PurePosixPath(name.removeprefix(prefix))
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        return None

    return Path(*relative.parts)


def write_bytes_if_needed(path: Path, data: bytes, *, force: bool) -> bool:
    if path.exists() and not force:
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return True


def download_archive_asset(
    project: ProjectPaths,
    asset: VendorAsset,
    *,
    force: bool,
    fetch_bytes: ByteFetcher,
) -> tuple[str, ...]:
    if not asset.archive_url or not asset.archive_prefix:
        return ()

    target_root = vendor_local_root(project, asset)
    data = fetch_bytes(asset.archive_url)
    actions: list[str] = []

    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        for member in archive.getmembers():
            relative = safe_archive_member_path(member.name, asset.archive_prefix)
            if not member.isfile() or relative is None:
                continue

            source = archive.extractfile(member)
            if source is None:
                continue

            target = target_root / relative
            if write_bytes_if_needed(target, source.read(), force=force):
                actions.append(target.as_posix())

    return tuple(actions)


def download_file_asset(
    project: ProjectPaths,
    asset: VendorAsset,
    *,
    force: bool,
    fetch_bytes: ByteFetcher,
) -> tuple[str, ...]:
    return tuple(
        target.as_posix()
        for relative_path, url in download_file_entries(asset)
        for target in [vendor_local_file(project, asset, relative_path)]
        if write_bytes_if_needed(target, fetch_bytes(url), force=force)
    )


def planned_download_actions(project: ProjectPaths, names: Iterable[str]) -> tuple[str, ...]:
    return tuple(
        (
            f"{vendor_local_root(project, asset).as_posix()} <- {asset.archive_url}"
            if asset.archive_url
            else f"{vendor_local_file(project, asset, relative_path).as_posix()} <- {url}"
        )
        for name in expand_vendor_assets(names, project.vendor)
        for asset in [configured_vendor_asset(project.vendor, name)]
        for relative_path, url in (
            ((asset.local_path, asset.archive_url),)
            if asset.archive_url
            else download_file_entries(asset)
        )
    )


def download_vendor_assets(
    project: ProjectPaths,
    names: Iterable[str],
    *,
    force: bool = False,
    dry_run: bool = False,
    fetch_bytes: ByteFetcher = default_fetch_bytes,
) -> tuple[str, ...]:
    expanded = expand_vendor_assets(names, project.vendor)

    if dry_run:
        return planned_download_actions(project, expanded)

    return tuple(
        path
        for name in expanded
        for asset in [configured_vendor_asset(project.vendor, name)]
        for path in (
            download_archive_asset(
                project,
                asset,
                force=force,
                fetch_bytes=fetch_bytes,
            )
            if asset.archive_url
            else download_file_asset(
                project,
                asset,
                force=force,
                fetch_bytes=fetch_bytes,
            )
        )
    )
