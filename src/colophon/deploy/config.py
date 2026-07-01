"""Deploy configuration loading and validation.

Raw deploy YAML flows through expression resolution, defaults, target validation,
step validation, and secret redaction before pipeline execution.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from colophon.errors import DeployConfigError
from colophon.expressions import expression_registry, resolve_yaml_expression_values
from colophon.models import ProjectPaths
from colophon.utils import copy_value, deep_merge, mapping, read_yaml


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


def load_deploy_steps(value: Any) -> list[str]:
    steps = list(value or DEFAULT_DEPLOY_STEPS)
    unknown = [step for step in steps if step not in DEFAULT_DEPLOY_STEPS]

    if unknown:
        raise DeployConfigError(f"unknown deploy step(s): {', '.join(map(str, unknown))}")

    return steps or copy_value(DEFAULT_DEPLOY_STEPS)


def load_deploy_target(raw_target: Any, path: str) -> dict[str, Any]:
    raw = mapping(raw_target, path, error=DeployConfigError)
    target = deep_merge(DEFAULT_DEPLOY_TARGET, raw)
    transport = str(target["transport"]).strip().lower()

    if transport not in DEFAULT_TRANSPORT_PORTS:
        raise DeployConfigError(f"unknown deploy transport {transport!r}")

    missing = [key for key in ("host", "username", "remote_path") if not target.get(key)]
    if missing:
        raise DeployConfigError(f"{path} missing required key(s): {', '.join(missing)}")

    return deep_merge(
        target,
        {
            "transport": transport,
            "port": target.get("port") or DEFAULT_TRANSPORT_PORTS[transport],
        },
    )


def validate_deploy_config(raw_config: Any, registry: Any = None) -> dict[str, Any]:
    raw = mapping(raw_config, "deploy config", error=DeployConfigError)
    if "deploy" not in raw:
        raise DeployConfigError("deploy config must contain a top-level deploy mapping")

    deploy = mapping(raw["deploy"], "deploy", error=DeployConfigError)
    resolved = resolve_yaml_expression_values(deploy, registry=registry, path="deploy")
    resolved = mapping(resolved, "deploy", error=DeployConfigError)
    base = deep_merge(
        DEFAULT_DEPLOY,
        {key: copy_value(value) for key, value in resolved.items() if key != "targets"},
    )
    targets = mapping(resolved.get("targets"), "deploy.targets", error=DeployConfigError)

    if not targets:
        raise DeployConfigError("deploy.targets must contain at least one target")

    normalized_targets = {
        str(name).strip(): load_deploy_target(target, f"deploy.targets.{name}")
        for name, target in targets.items()
    }
    default_target = str(base.get("default_target") or DEFAULT_DEPLOY["default_target"]).strip()

    if default_target not in normalized_targets:
        raise DeployConfigError(f"default deploy target {default_target!r} is not configured")

    return deep_merge(
        base,
        {
            "default_target": default_target,
            "steps": load_deploy_steps(base.get("steps")),
            "post": deep_merge(
                DEFAULT_DEPLOY_POST,
                mapping(base.get("post"), "deploy.post", error=DeployConfigError),
            ),
            "mastodon": deep_merge(
                DEFAULT_DEPLOY_MASTODON,
                mapping(base.get("mastodon"), "deploy.mastodon", error=DeployConfigError),
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

    return validate_deploy_config(raw, registry=expression_registry(resolved_project))


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
