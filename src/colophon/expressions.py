"""YAML expression and trusted Python-hook resolution.

Config and page data flow through ``python::`` calls, ``env::`` references, and
Jinja template strings before downstream content, image, and deploy stages use it.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import os
import random
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from jinja2 import Environment, StrictUndefined, TemplateError
from slugify import slugify

from .errors import ExpressionResolutionError, ProjectConfigError
from .models import ExpressionFunction, PageContext, ProjectPaths
from .utils import copy_value, deep_merge, require_mapping

# TODO: Make expression prefixes configurable, and allow for custom prefixes to be registered with the expression resolver.

ENV_EXPRESSION_PREFIX = "env::"
PYTHON_EXPRESSION_PREFIX = "python::"
SIGNAL_LINE_SEPARATOR = " // "


def generate_random_color() -> str:
    return random.choice(
        [
            "amber",
            "cyan",
            "green",
            "magenta",
            "violet",
        ]
    )


def generate_random_temperature() -> str:
    return f"{random.randint(-20, 42)}C"


def get_moon_phase() -> str:
    phases = (
        "new",
        "waxing crescent",
        "first quarter",
        "waxing gibbous",
        "full",
        "waning gibbous",
        "last quarter",
        "waning crescent",
    )
    return phases[dt.date.today().toordinal() % len(phases)]


YAML_FUNCTIONS: dict[str, ExpressionFunction] = {
    "generate_random_color": generate_random_color,
    "generate_random_temperature": generate_random_temperature,
    "get_moon_phase": get_moon_phase,
}


def import_python_module(path: Path) -> Any:
    if not path.exists():
        raise ProjectConfigError(f"missing Python extension module: {path}")

    module_name = f"_colophon_site_{slugify(path.stem).replace('-', '_')}_{abs(hash(path))}"
    spec = importlib.util.spec_from_file_location(module_name, path)

    if spec is None or spec.loader is None:
        raise ProjectConfigError(f"cannot import Python extension module: {path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module

    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise ProjectConfigError(f"failed to import Python extension module {path}: {exc}") from exc

    return module


def module_yaml_functions(path: Path) -> dict[str, ExpressionFunction]:
    module = import_python_module(path)
    registry = getattr(module, "YAML_FUNCTIONS", None)

    if callable(registry):
        registry = registry()

    if not isinstance(registry, Mapping):
        raise ProjectConfigError(f"{path}: YAML_FUNCTIONS must be a mapping or zero-argument function")

    invalid = [name for name, function in registry.items() if not callable(function)]

    if invalid:
        raise ProjectConfigError(f"{path}: YAML function(s) are not callable: {', '.join(map(str, invalid))}")

    return {str(name): function for name, function in registry.items()}


def merge_function_registries(registries: list[Mapping[str, ExpressionFunction]]) -> dict[str, ExpressionFunction]:
    merged: dict[str, ExpressionFunction] = {}

    for registry in registries:
        duplicates = sorted(set(merged).intersection(registry))

        if duplicates:
            raise ProjectConfigError(f"duplicate YAML function name(s): {', '.join(duplicates)}")

        merged = {**merged, **dict(registry)}

    return merged


def expression_registry(project: ProjectPaths) -> dict[str, ExpressionFunction]:
    resolved_project = project
    custom = [module_yaml_functions(path) for path in resolved_project.python_modules]
    return merge_function_registries([YAML_FUNCTIONS, *custom])


def expression_child_path(path: str, key: Any) -> str:
    key_text = str(key)

    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key_text):
        return f"{path}.{key_text}" if path else key_text

    return f"{path}[{key_text!r}]" if path else f"[{key_text!r}]"


def expression_index_path(path: str, index: int) -> str:
    return f"{path}[{index}]" if path else f"[{index}]"


def make_expression_environment() -> Environment:
    env = Environment(autoescape=False, undefined=StrictUndefined)
    env.filters["slugify"] = slugify
    return env


def call_expression_function(
    value: str,
    registry: Mapping[str, ExpressionFunction],
    path: str,
) -> Any:
    name = value.removeprefix(PYTHON_EXPRESSION_PREFIX).strip()

    if not name:
        raise ExpressionResolutionError(f"{path or 'value'}: missing YAML function name")

    function = registry.get(name)

    if function is None:
        raise ExpressionResolutionError(
            f"{path or 'value'}: unknown YAML function {name!r}"
        )

    try:
        return copy_value(function())
    except Exception as exc:
        raise ExpressionResolutionError(
            f"{path or 'value'}: YAML function {name!r} failed: {exc}"
        ) from exc


def read_env_reference(value: str, path: str) -> str:
    name = value.removeprefix(ENV_EXPRESSION_PREFIX).strip()

    if not name:
        raise ExpressionResolutionError(f"{path or 'value'}: missing environment variable name")

    if name not in os.environ:
        raise ExpressionResolutionError(
            f"{path or 'value'}: missing environment variable {name!r}"
        )

    return os.environ[name]


def resolve_env_references(value: Any, path: str = "") -> Any:
    if isinstance(value, Mapping):
        return {
            key: resolve_env_references(item, expression_child_path(path, key))
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [
            resolve_env_references(item, expression_index_path(path, index))
            for index, item in enumerate(value)
        ]

    if isinstance(value, tuple):
        return tuple(
            resolve_env_references(item, expression_index_path(path, index))
            for index, item in enumerate(value)
        )

    if isinstance(value, str) and value.strip().startswith(ENV_EXPRESSION_PREFIX):
        return read_env_reference(value.strip(), path)

    return copy_value(value)


def resolve_python_function_calls(
    value: Any,
    registry: Mapping[str, ExpressionFunction],
    path: str = "",
) -> Any:
    if isinstance(value, Mapping):
        return {
            key: resolve_python_function_calls(
                item,
                registry,
                expression_child_path(path, key),
            )
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [
            resolve_python_function_calls(
                item,
                registry,
                expression_index_path(path, index),
            )
            for index, item in enumerate(value)
        ]

    if isinstance(value, tuple):
        return tuple(
            resolve_python_function_calls(
                item,
                registry,
                expression_index_path(path, index),
            )
            for index, item in enumerate(value)
        )

    if isinstance(value, str) and value.strip().startswith(PYTHON_EXPRESSION_PREFIX):
        return call_expression_function(value.strip(), registry, path)

    return copy_value(value)


def render_expression_template(value: str, context: Mapping[str, Any], path: str) -> str:
    try:
        return make_expression_environment().from_string(value).render(**context)
    except TemplateError as exc:
        raise ExpressionResolutionError(
            f"{path or 'value'}: failed to render YAML template: {exc}"
        ) from exc


def resolve_template_strings(
    value: Any,
    context: Mapping[str, Any],
    path: str = "",
) -> Any:
    if isinstance(value, Mapping):
        return {
            key: resolve_template_strings(item, context, expression_child_path(path, key))
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [
            resolve_template_strings(
                item,
                context,
                expression_index_path(path, index),
            )
            for index, item in enumerate(value)
        ]

    if isinstance(value, tuple):
        return tuple(
            resolve_template_strings(
                item,
                context,
                expression_index_path(path, index),
            )
            for index, item in enumerate(value)
        )

    if isinstance(value, str) and "{{" in value:
        return render_expression_template(value, context, path)

    return copy_value(value)


def resolve_yaml_expressions(
    value: Any,
    *,
    registry: Mapping[str, ExpressionFunction] | None = None,
    path: str = "value",
) -> Any:
    value_resolved = resolve_yaml_expression_values(value, registry=registry, path=path)
    template_context = value_resolved if isinstance(value_resolved, Mapping) else {}
    return resolve_template_strings(value_resolved, template_context, path)


def resolve_yaml_expression_values(
    value: Any,
    *,
    registry: Mapping[str, ExpressionFunction] | None = None,
    path: str = "value",
) -> Any:
    functions = YAML_FUNCTIONS if registry is None else registry
    function_resolved = resolve_python_function_calls(value, functions, path)
    return resolve_env_references(function_resolved, path)


def format_signal_line(value: Any) -> Any:
    if not isinstance(value, Mapping):
        return copy_value(value)

    return SIGNAL_LINE_SEPARATOR.join(
        f"{key}: {'' if item is None else item}"
        for key, item in value.items()
    )


def normalize_resolved_site_fields(site: Mapping[str, Any]) -> dict[str, Any]:
    return deep_merge(
        site,
        {"signal_line": format_signal_line(site.get("signal_line"))},
    )


def resolve_site_expressions(
    site: Mapping[str, Any],
    *,
    registry: Mapping[str, ExpressionFunction] | None = None,
) -> dict[str, Any]:
    resolved = resolve_yaml_expressions({"site": site}, registry=registry, path="")
    return normalize_resolved_site_fields(require_mapping(resolved.get("site"), "site"))


def resolve_page_context_expressions(
    context: PageContext,
    *,
    registry: Mapping[str, ExpressionFunction] | None = None,
) -> PageContext:
    resolved_data = resolve_yaml_expressions(
        context.data,
        registry=registry,
        path=f"page:{context.route.url_path}",
    )
    data = (
        deep_merge(
            resolved_data,
            {"site": normalize_resolved_site_fields(resolved_data["site"])},
        )
        if isinstance(resolved_data, Mapping)
        and isinstance(resolved_data.get("site"), Mapping)
        else resolved_data
    )

    return PageContext(
        route=context.route,
        data=data,
        slots=copy_value(context.slots),
        assets=context.assets,
        template=context.template,
        source_chain=context.source_chain,
    )
