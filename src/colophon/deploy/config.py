"""Deploy configuration loading and validation.

Raw deploy YAML flows through expression resolution, defaults, target validation,
step validation, and secret redaction before pipeline execution.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import partial
from pathlib import Path
from typing import Any

from colophon.errors import DeployConfigError
from colophon.expressions import resolve_yaml_expression_values
from colophon.models import ProjectPaths
from colophon.utils import copy_value, deep_merge, expect, expect_fields, field, read_yaml


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


deploy_value = partial(expect, error=DeployConfigError)
deploy_fields = partial(expect_fields, error=DeployConfigError)


DEPLOY_TARGET_FIELDS = {
    "transport": field("string", DEFAULT_DEPLOY_TARGET["transport"], nonempty=True),
    "host": field("string", nonempty=True),
    "username": field("string", nonempty=True),
    "password": field("string", ""),
    "remote_path": field("string", nonempty=True),
    "purge": field("boolean", True),
}


def load_deploy_steps(value: Any) -> list[str]:
    raw_steps = deploy_value(value, "deploy.steps", "sequence", default=DEFAULT_DEPLOY_STEPS)
    steps = [
        deploy_value(step, "deploy.steps[]", "string", nonempty=True)
        for step in raw_steps
    ]
    unknown = [step for step in steps if step not in DEFAULT_DEPLOY_STEPS]

    if unknown:
        raise DeployConfigError(f"unknown deploy step(s): {', '.join(unknown)}")

    return steps or copy_value(DEFAULT_DEPLOY_STEPS)


def load_deploy_target(raw_target: Any, path: str) -> dict[str, Any]:
    raw = deploy_value(raw_target, path, "mapping")
    target = deep_merge(DEFAULT_DEPLOY_TARGET, raw)
    fields = deploy_fields(raw, path, DEPLOY_TARGET_FIELDS)
    transport = fields["transport"].lower()

    if transport not in DEFAULT_TRANSPORT_PORTS:
        raise DeployConfigError(f"unknown deploy transport {transport!r}")

    normalized = deep_merge(
        target,
        {
            **fields,
            "transport": transport,
            "port": deploy_value(
                raw.get("port"),
                f"{path}.port",
                "integer",
                default=DEFAULT_TRANSPORT_PORTS[transport],
            ),
        },
    )

    return normalized


def validate_deploy_config(raw_config: Any) -> dict[str, Any]:
    raw = deploy_value(raw_config, "deploy config", "mapping")
    if "deploy" not in raw:
        raise DeployConfigError("deploy config must contain a top-level deploy mapping")

    deploy = deploy_value(raw["deploy"], "deploy", "mapping")
    resolved = resolve_yaml_expression_values(deploy, path="deploy")
    resolved = deploy_value(resolved, "deploy", "mapping")
    base = deep_merge(
        DEFAULT_DEPLOY,
        {key: copy_value(value) for key, value in resolved.items() if key != "targets"},
    )
    targets = deploy_value(resolved.get("targets"), "deploy.targets", "mapping")

    if not targets:
        raise DeployConfigError("deploy.targets must contain at least one target")

    normalized_targets = {
        deploy_value(name, "deploy.targets key", "string", nonempty=True): load_deploy_target(
            target,
            f"deploy.targets.{name}",
        )
        for name, target in targets.items()
    }
    default_target = deploy_value(
        base.get("default_target"),
        "deploy.default_target",
        "string",
        default=DEFAULT_DEPLOY["default_target"],
        nonempty=True,
    )

    if default_target not in normalized_targets:
        raise DeployConfigError(f"default deploy target {default_target!r} is not configured")

    return deep_merge(
        base,
        {
            "default_target": default_target,
            "steps": load_deploy_steps(base.get("steps")),
            "post": deep_merge(
                DEFAULT_DEPLOY_POST,
                deploy_value(base.get("post"), "deploy.post", "mapping", default={}),
            ),
            "mastodon": deep_merge(
                DEFAULT_DEPLOY_MASTODON,
                deploy_value(base.get("mastodon"), "deploy.mastodon", "mapping", default={}),
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
