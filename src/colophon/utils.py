"""Small pure helpers shared by Colophon subsystems.

Values flow through copy-on-write merges, strict schema checks, YAML loading,
date parsing, route normalization, and URL helpers without subsystem-specific
side effects.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import dateparser
import yaml

from .errors import ProjectConfigError


MISSING = object()


SCHEMA_CHECKS = {
    "mapping": lambda item: isinstance(item, Mapping),
    "sequence": lambda item: isinstance(item, list | tuple),
    "string": lambda item: isinstance(item, str),
    "boolean": lambda item: isinstance(item, bool),
    "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
}


SCHEMA_MESSAGES = {
    "mapping": "must be a mapping",
    "sequence": "must be a sequence",
    "string": "must be a string",
    "boolean": "must be a boolean",
    "integer": "must be an integer",
}


def expect(
    value: Any,
    path: str,
    kind: str,
    *,
    default: Any = MISSING,
    error: type[Exception] = ProjectConfigError,
    nonempty: bool = False,
) -> Any:
    if value is None:
        if default is MISSING:
            raise error(f"{path} {SCHEMA_MESSAGES[kind]}")

        return copy_value(default)

    if not SCHEMA_CHECKS[kind](value):
        raise error(f"{path} {SCHEMA_MESSAGES[kind]}")

    if kind == "mapping":
        return dict(value)

    if kind == "sequence":
        return tuple(value)

    if kind == "string":
        text = value.strip()

        if nonempty and not text:
            raise error(f"{path} must not be empty")

        return text

    return value


def field(kind: str, default: Any = MISSING, *, nonempty: bool = False) -> tuple[str, Any, bool]:
    return kind, default, nonempty


def expect_fields(
    raw: Mapping[str, Any],
    path: str,
    fields: Mapping[str, tuple[str, Any, bool]],
    *,
    error: type[Exception] = ProjectConfigError,
) -> dict[str, Any]:
    return {
        name: expect(
            raw.get(name),
            f"{path}.{name}",
            kind,
            default=default,
            error=error,
            nonempty=nonempty,
        )
        for name, (kind, default, nonempty) in fields.items()
    }


def copy_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: copy_value(item) for key, item in value.items()}

    if isinstance(value, list):
        return [copy_value(item) for item in value]

    if isinstance(value, tuple):
        return tuple(copy_value(item) for item in value)

    if isinstance(value, set):
        return {copy_value(item) for item in value}

    return value


def deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Merge mappings immutably; lists and scalar values replace."""
    keys = set(base) | set(override)

    return {
        key: (
            deep_merge(base[key], override[key])
            if isinstance(base.get(key), Mapping) and isinstance(override.get(key), Mapping)
            else copy_value(override[key])
            if key in override
            else copy_value(base[key])
        )
        for key in keys
    }


def read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_first_yaml(paths: list[Path]) -> dict[str, Any]:
    return next((read_yaml(path) for path in paths if path.exists()), {})


def load_wrapped_yaml(paths: list[Path], *, unwrap: str | None = None) -> dict[str, Any]:
    data = load_first_yaml(paths)

    if unwrap and unwrap in data:
        nested = data[unwrap]

        return expect(nested, f"{unwrap!r}", "mapping")

    return data


def parse_date(value: Any) -> dt.date | None:
    if value in (None, ""):
        return None

    if isinstance(value, dt.datetime):
        return value.date()

    if isinstance(value, dt.date):
        return value

    parsed = dateparser.parse(str(value))
    return parsed.date() if parsed else None


def trim_url(value: Any) -> str:
    return str(value or "").strip().rstrip("/")


def route_parts(route: str) -> list[str]:
    return [part for part in route.strip("/").split("/") if part]


def normalize_route(value: str) -> str:
    route = str(value or "/").strip()

    if not route.startswith("/"):
        route = f"/{route}"

    if not route.endswith("/"):
        route = f"{route}/"

    return route


def public_url(site: Mapping[str, Any], path: str) -> str:
    base = str(site.get("url") or "").rstrip("/")
    return f"{base}{path}" if base else path
