"""Project configuration and path resolution.

Project config flows from ``colophon.yml`` into a ``ProjectPaths`` value that
downstream build, serve, scaffold, and deploy stages consume explicitly.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .errors import ProjectConfigError
from .models import ProjectPaths
from .utils import deep_merge, mapping, read_yaml
from .vendor import load_vendor_config


DEFAULT_CONFIG_FILE = "colophon.yml"


CONFIG_EXTS = (".yaml", ".yml")


def absolute_project_path(root: Path, value: Any, default: str) -> Path:
    text = (default if value is None else value).strip()
    path = Path(text).expanduser()
    return path if path.is_absolute() else root / path


def load_project_file(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        raise ProjectConfigError(f"missing project config: {config_path}")

    return mapping(read_yaml(config_path), f"project config {config_path}")


def validate_project_keys(raw: Mapping[str, Any]) -> None:
    if "project" in raw:
        raise ProjectConfigError("project config must use 'paths', not legacy 'project'")


def path_overrides(
    *,
    content: str | None,
    templates: str | None,
    static: str | None,
    output: str | None,
) -> dict[str, str]:
    return {
        key: value.strip()
        for key, value in {
            "content": content,
            "templates": templates,
            "static": static,
            "output": output,
        }.items()
        if value is not None
    }


def python_modules_from_config(root: Path, raw_python: Mapping[str, Any]) -> tuple[Path, ...]:
    return tuple(
        absolute_project_path(
            root,
            item.strip(),
            "",
        )
        for item in raw_python.get("modules") or ()
    )


def project_from_config(
    config_path: Path | str = DEFAULT_CONFIG_FILE,
    *,
    content: str | None = None,
    templates: str | None = None,
    static: str | None = None,
    output: str | None = None,
) -> ProjectPaths:
    config_file = Path(config_path).expanduser()
    if not config_file.is_absolute():
        config_file = Path.cwd() / config_file

    root = config_file.parent.resolve()
    raw = load_project_file(config_file)
    validate_project_keys(raw)
    raw_paths = mapping(raw.get("paths"), "paths")
    if "project" in raw_paths:
        raise ProjectConfigError("paths.project is not supported; use the config file location or --project")
    raw_python = mapping(raw.get("python"), "python")
    path_values = deep_merge(
        raw_paths,
        path_overrides(content=content, templates=templates, static=static, output=output),
    )
    content_dir = absolute_project_path(root, path_values.get("content"), "content")
    templates_dir = absolute_project_path(root, path_values.get("templates"), "templates")
    static_dir = absolute_project_path(root, path_values.get("static"), "static")
    output_dir = absolute_project_path(root, path_values.get("output"), "_site")
    if "deploy_config" in path_values:
        raise ProjectConfigError("paths.deploy_config is not supported; use paths.deploy")
    deploy_config = absolute_project_path(
        root,
        path_values.get("deploy"),
        "content/deploy.yaml",
    )
    python_modules = python_modules_from_config(root, raw_python)

    return ProjectPaths(
        root=root,
        content_dir=content_dir,
        posts_dir=content_dir / "posts",
        content_images_dir=content_dir / "images",
        templates_dir=templates_dir,
        static_dir=static_dir,
        output_dir=output_dir,
        deploy_config=deploy_config,
        site_configs=(content_dir / "site.yaml", content_dir / "site.yml"),
        image_configs=(content_dir / "images.yaml", content_dir / "images.yml"),
        post_sidebar_configs=(content_dir / "post-sidebar.yaml", content_dir / "post-sidebar.yml"),
        watched_dirs=(content_dir, templates_dir, static_dir),
        watched_files=(config_file, *python_modules),
        python_modules=python_modules,
        vendor=load_vendor_config(raw.get("vendor")),
    )


def project_from_inputs(
    project_path: Path | str = ".",
    *,
    config: Path | str | None = None,
    content: str | None = None,
    templates: str | None = None,
    static: str | None = None,
    output: str | None = None,
) -> ProjectPaths:
    root = Path(project_path).expanduser().resolve()
    config_file = Path(config or DEFAULT_CONFIG_FILE).expanduser()
    config_path = config_file if config_file.is_absolute() else root / config_file

    return project_from_config(
        config_path,
        content=content,
        templates=templates,
        static=static,
        output=output,
    )
