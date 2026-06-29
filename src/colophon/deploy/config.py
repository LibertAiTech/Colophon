"""Deploy configuration loading and validation.

Raw deploy YAML flows through expression resolution, defaults, target validation,
step validation, and secret redaction before pipeline execution.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from colophon.errors import DeployConfigError
from colophon.expressions import resolve_yaml_expression_values
from colophon.models import ProjectPaths
from colophon.utils import copy_value, deep_merge, read_yaml


DEFAULT_DEPLOY_STEPS = [
    "preflight_build",
    "mastodon_post",
    "enable_comments",
    "build",
    "upload",
]


DEFAULT_DEPLOY_POST = {
    "select": "latest_published",
}


DEFAULT_DEPLOY_MASTODON = {
    "access_token": "",
    "post_text": "Hey, check out my new blog post. {{ post.summary }} {{ post.url }}",
}


DEFAULT_DEPLOY_TARGET = {
    "transport": "ftps",
    "host": "",
    "port": 0,
    "username": "",
    "password": "",
    "remote_path": "",
    "purge": True,
}


DEFAULT_DEPLOY = {
    "default_target": "production",
    "steps": DEFAULT_DEPLOY_STEPS,
    "post": DEFAULT_DEPLOY_POST,
    "mastodon": DEFAULT_DEPLOY_MASTODON,
    "targets": {},
}


DEFAULT_TRANSPORT_PORTS = {
    "ftp": 21,
    "ftps": 21,
    "sftp": 22,
    "sshfs": 22,
}


def require_deploy_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise DeployConfigError(f"{path} must be a mapping")

    return dict(value)


def optional_deploy_mapping(value: Any, path: str) -> dict[str, Any]:
    return {} if value is None else require_deploy_mapping(value, path)


def require_deploy_sequence(value: Any, path: str) -> tuple[Any, ...]:
    if not isinstance(value, list | tuple):
        raise DeployConfigError(f"{path} must be a sequence")

    return tuple(value)


def optional_deploy_sequence(value: Any, path: str) -> tuple[Any, ...]:
    return () if value is None else require_deploy_sequence(value, path)


def require_deploy_string(value: Any, path: str) -> str:
    if not isinstance(value, str):
        raise DeployConfigError(f"{path} must be a string")

    if not value.strip():
        raise DeployConfigError(f"{path} must not be empty")

    return value


def optional_deploy_string(value: Any, path: str, default: str = "") -> str:
    return default if value is None else require_deploy_string(value, path)


def optional_deploy_bool(value: Any, path: str, default: bool) -> bool:
    if value is None:
        return default

    if not isinstance(value, bool):
        raise DeployConfigError(f"{path} must be a boolean")

    return value


def optional_deploy_int(value: Any, path: str, default: int) -> int:
    if value is None:
        return default

    if not isinstance(value, int) or isinstance(value, bool):
        raise DeployConfigError(f"{path} must be an integer")

    return value


def load_deploy_steps(value: Any) -> list[str]:
    raw_steps = DEFAULT_DEPLOY_STEPS if value is None else require_deploy_sequence(value, "deploy.steps")
    steps = [require_deploy_string(step, "deploy.steps[]").strip() for step in raw_steps]
    unknown = [step for step in steps if step not in DEFAULT_DEPLOY_STEPS]

    if unknown:
        raise DeployConfigError(f"unknown deploy step(s): {', '.join(unknown)}")

    return steps or copy_value(DEFAULT_DEPLOY_STEPS)


def load_deploy_target(raw_target: Any, path: str) -> dict[str, Any]:
    raw = require_deploy_mapping(raw_target, path)
    target = deep_merge(DEFAULT_DEPLOY_TARGET, raw)
    transport = optional_deploy_string(
        raw.get("transport"),
        f"{path}.transport",
        DEFAULT_DEPLOY_TARGET["transport"],
    ).lower()

    if transport not in DEFAULT_TRANSPORT_PORTS:
        raise DeployConfigError(f"unknown deploy transport {transport!r}")

    normalized = deep_merge(
        target,
        {
            "transport": transport,
            "port": optional_deploy_int(raw.get("port"), f"{path}.port", DEFAULT_TRANSPORT_PORTS[transport]),
            "host": require_deploy_string(raw.get("host"), f"{path}.host").strip(),
            "username": require_deploy_string(raw.get("username"), f"{path}.username").strip(),
            "password": optional_deploy_string(raw.get("password"), f"{path}.password", ""),
            "remote_path": require_deploy_string(raw.get("remote_path"), f"{path}.remote_path").strip(),
            "purge": optional_deploy_bool(raw.get("purge"), f"{path}.purge", True),
        },
    )

    if normalized["password"] and not isinstance(normalized["password"], str):
        raise DeployConfigError(f"{path}.password must be a string")

    return normalized


def validate_deploy_config(raw_config: Any) -> dict[str, Any]:
    raw = require_deploy_mapping(raw_config, "deploy config")
    if "deploy" not in raw:
        raise DeployConfigError("deploy config must contain a top-level deploy mapping")

    deploy = require_deploy_mapping(raw["deploy"], "deploy")
    resolved = resolve_yaml_expression_values(deploy, path="deploy")
    resolved = require_deploy_mapping(resolved, "deploy")
    base = deep_merge(
        DEFAULT_DEPLOY,
        {key: copy_value(value) for key, value in resolved.items() if key != "targets"},
    )
    targets = require_deploy_mapping(resolved.get("targets"), "deploy.targets")

    if not targets:
        raise DeployConfigError("deploy.targets must contain at least one target")

    normalized_targets = {
        require_deploy_string(name, "deploy.targets key"): load_deploy_target(target, f"deploy.targets.{name}")
        for name, target in targets.items()
    }
    default_target = optional_deploy_string(
        base.get("default_target"),
        "deploy.default_target",
        DEFAULT_DEPLOY["default_target"],
    )

    if default_target not in normalized_targets:
        raise DeployConfigError(f"default deploy target {default_target!r} is not configured")

    return deep_merge(
        base,
        {
            "default_target": default_target,
            "steps": load_deploy_steps(base.get("steps")),
            "post": deep_merge(DEFAULT_DEPLOY_POST, optional_deploy_mapping(base.get("post"), "deploy.post")),
            "mastodon": deep_merge(
                DEFAULT_DEPLOY_MASTODON,
                optional_deploy_mapping(base.get("mastodon"), "deploy.mastodon"),
            ),
            "targets": normalized_targets,
        },
    )


def load_deploy_config(
    project: ProjectPaths,
    config_path: Path | None = None,
) -> dict[str, Any]:
    resolved_project = project
    path = resolved_project.deploy_config if config_path is None else config_path
    raw = read_yaml(path)

    if not raw:
        raise DeployConfigError(f"missing deploy config: {path}")

    return validate_deploy_config(raw)


def redact_secrets(value: Any, parent_key: str = "") -> Any:
    secret_fragments = ("password", "token", "secret")

    if isinstance(value, Mapping):
        return {
            key: (
                "[redacted]"
                if any(fragment in str(key).lower() for fragment in secret_fragments)
                and item not in (None, "")
                else redact_secrets(item, str(key))
            )
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [redact_secrets(item, parent_key) for item in value]

    if isinstance(value, tuple):
        return tuple(redact_secrets(item, parent_key) for item in value)

    return copy_value(value)
