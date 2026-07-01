"""Stable public Colophon entry points.

External callers may import this small surface; implementation dataflow lives in
the build, deploy, project, scaffold, serve, and CLI modules.
"""

from __future__ import annotations

from .build import build_project, build_site
from .cli import main
from .deploy.pipeline import deploy_site
from .errors import (
    AssetError,
    BuildFailure,
    ColophonError,
    ConfigurationError,
    ContentError,
    DeployConfigError,
    DeployError,
    ExpressionResolutionError,
    InternalBuildError,
    ProjectConfigError,
    TemplateBuildError,
)
from .models import BuildManifest, BuildMessage, BuildOptions, BuildResult, ExpressionContext, ManifestEntry
from .project import project_from_config
from .scaffold import scaffold_site
from .serve import serve_site
from .version import __version__

__all__ = [
    "AssetError",
    "BuildFailure",
    "BuildManifest",
    "BuildMessage",
    "BuildOptions",
    "BuildResult",
    "ColophonError",
    "ConfigurationError",
    "ContentError",
    "DeployConfigError",
    "DeployError",
    "ExpressionContext",
    "ExpressionResolutionError",
    "InternalBuildError",
    "ManifestEntry",
    "ProjectConfigError",
    "TemplateBuildError",
    "__version__",
    "build_project",
    "build_site",
    "deploy_site",
    "main",
    "project_from_config",
    "scaffold_site",
    "serve_site",
]


if __name__ == "__main__":
    main()
