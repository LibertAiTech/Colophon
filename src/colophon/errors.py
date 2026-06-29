"""Domain-specific exception types used across Colophon.

Errors flow up from focused subsystems as typed failures so CLI and Python
callers can distinguish configuration, content, template, asset, deploy, build,
and unexpected internal failures without scraping terminal output.
"""

from __future__ import annotations


class ColophonError(Exception):
    """Base class for user-facing Colophon failures."""

    category = "error"
    exit_code = 1


class ConfigurationError(ColophonError):
    """Raised when configuration cannot be loaded or normalized."""

    category = "configuration"
    exit_code = 2


class ContentError(ColophonError):
    """Raised when content cannot be interpreted."""

    category = "content"
    exit_code = 3


class TemplateBuildError(ColophonError):
    """Raised when template loading or rendering fails."""

    category = "template"
    exit_code = 4


class AssetError(ColophonError):
    """Raised when static, content, image, or vendor assets fail."""

    category = "asset"
    exit_code = 5


class BuildFailure(ColophonError):
    """Raised when the build pipeline cannot complete."""

    category = "build"
    exit_code = 6


class InternalBuildError(ColophonError):
    """Raised for unexpected internal build failures."""

    category = "internal"
    exit_code = 70


class ExpressionResolutionError(ValueError, ContentError):
    """Raised when a YAML expression cannot be resolved during build."""


class DeployConfigError(ValueError, ConfigurationError):
    """Raised when deployment configuration is missing or invalid."""


class DeployError(RuntimeError, ColophonError):
    """Raised when a deployment side effect fails."""

    category = "deploy"
    exit_code = 7


class ProjectConfigError(ValueError, ConfigurationError):
    """Raised when project configuration is missing or invalid."""
