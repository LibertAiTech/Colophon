"""YAML expression and trusted Python-hook resolution.

Config and page data flow through ``python::`` calls, ``env::`` references, and
Jinja template strings before downstream content, image, and deploy stages use it.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from jinja2 import Environment, StrictUndefined, TemplateError
from slugify import slugify

from .errors import ExpressionResolutionError, ProjectConfigError
from .models import ExpressionContext, ExpressionContextFunction, ExpressionFunction, PageContext, ProjectPaths
from .utils import copy_value, deep_merge, mapping, parse_date

# TODO: Make expression prefixes configurable, and allow for custom prefixes to be registered with the expression resolver.

ENV_EXPRESSION_PREFIX = "env::"
PYTHON_EXPRESSION_PREFIX = "python::"
SIGNAL_LINE_SEPARATOR = " // "
YAML_FUNCTIONS: dict[str, ExpressionFunction] = {}
YAML_CONTEXT_FUNCTIONS: dict[str, ExpressionContextFunction] = {}


@dataclass(frozen=True)
class ExpressionRegistry:
    functions: Mapping[str, ExpressionFunction]
    context_functions: Mapping[str, ExpressionContextFunction]


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


def module_function_mapping(module: Any, path: Path, attribute: str) -> dict[str, Any]:
    registry = getattr(module, attribute, {})

    if callable(registry):
        registry = registry()

    if registry is None:
        registry = {}

    if not isinstance(registry, Mapping):
        raise ProjectConfigError(f"{path}: {attribute} must be a mapping or zero-argument function")

    invalid = [name for name, function in registry.items() if not callable(function)]

    if invalid:
        raise ProjectConfigError(f"{path}: {attribute} function(s) are not callable: {', '.join(map(str, invalid))}")

    return {str(name): function for name, function in registry.items()}


def module_yaml_functions(path: Path) -> dict[str, ExpressionFunction]:
    module = import_python_module(path)
    return module_function_mapping(module, path, "YAML_FUNCTIONS")


def module_yaml_context_functions(path: Path) -> dict[str, ExpressionContextFunction]:
    module = import_python_module(path)
    return module_function_mapping(module, path, "YAML_CONTEXT_FUNCTIONS")


def module_expression_registry(path: Path) -> ExpressionRegistry:
    module = import_python_module(path)
    return ExpressionRegistry(
        functions=module_function_mapping(module, path, "YAML_FUNCTIONS"),
        context_functions=module_function_mapping(module, path, "YAML_CONTEXT_FUNCTIONS"),
    )


def merge_function_registries(registries: list[Mapping[str, ExpressionFunction]]) -> dict[str, ExpressionFunction]:
    merged: dict[str, ExpressionFunction] = {}

    for registry in registries:
        duplicates = sorted(set(merged).intersection(registry))

        if duplicates:
            raise ProjectConfigError(f"duplicate YAML function name(s): {', '.join(duplicates)}")

        merged = {**merged, **dict(registry)}

    return merged


def registry_names(registry: ExpressionRegistry) -> set[str]:
    return set(registry.functions) | set(registry.context_functions)


def merge_expression_registries(registries: list[ExpressionRegistry]) -> ExpressionRegistry:
    merged = ExpressionRegistry(functions={}, context_functions={})

    for registry in registries:
        local_duplicates = sorted(set(registry.functions).intersection(registry.context_functions))

        if local_duplicates:
            raise ProjectConfigError(f"duplicate YAML function name(s): {', '.join(local_duplicates)}")

        duplicates = sorted(registry_names(merged).intersection(registry_names(registry)))

        if duplicates:
            raise ProjectConfigError(f"duplicate YAML function name(s): {', '.join(duplicates)}")

        merged = ExpressionRegistry(
            functions={**dict(merged.functions), **dict(registry.functions)},
            context_functions={**dict(merged.context_functions), **dict(registry.context_functions)},
        )

    return merged


def normalize_expression_registry(
    registry: Mapping[str, ExpressionFunction] | ExpressionRegistry | None,
) -> ExpressionRegistry:
    if registry is None:
        return ExpressionRegistry(
            functions=YAML_FUNCTIONS,
            context_functions=YAML_CONTEXT_FUNCTIONS,
        )

    if isinstance(registry, ExpressionRegistry):
        return registry

    return ExpressionRegistry(functions=registry, context_functions={})


def expression_registry(project: ProjectPaths) -> ExpressionRegistry:
    resolved_project = project
    custom = [module_expression_registry(path) for path in resolved_project.python_modules]
    return merge_expression_registries(
        [
            ExpressionRegistry(
                functions=YAML_FUNCTIONS,
                context_functions=YAML_CONTEXT_FUNCTIONS,
            ),
            *custom,
        ]
    )


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
    registry: ExpressionRegistry,
    path: str,
    context: ExpressionContext | None = None,
) -> Any:
    name = value.removeprefix(PYTHON_EXPRESSION_PREFIX).strip()

    if not name:
        raise ExpressionResolutionError(f"{path or 'value'}: missing YAML function name")

    function = registry.functions.get(name)

    if function is not None:
        try:
            return copy_value(function())
        except Exception as exc:
            raise ExpressionResolutionError(
                f"{path or 'value'}: YAML function {name!r} failed: {exc}"
            ) from exc

    context_function = registry.context_functions.get(name)

    if context_function is None:
        raise ExpressionResolutionError(
            f"{path or 'value'}: unknown YAML function {name!r}"
        )

    if context is None:
        raise ExpressionResolutionError(
            f"{path or 'value'}: YAML context function {name!r} requires page context"
        )

    try:
        return copy_value(context_function(context))
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
    registry: ExpressionRegistry,
    path: str = "",
    context: ExpressionContext | None = None,
) -> Any:
    if isinstance(value, Mapping):
        return {
            key: resolve_python_function_calls(
                item,
                registry,
                expression_child_path(path, key),
                context,
            )
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [
            resolve_python_function_calls(
                item,
                registry,
                expression_index_path(path, index),
                context,
            )
            for index, item in enumerate(value)
        ]

    if isinstance(value, tuple):
        return tuple(
            resolve_python_function_calls(
                item,
                registry,
                expression_index_path(path, index),
                context,
            )
            for index, item in enumerate(value)
        )

    if isinstance(value, str) and value.strip().startswith(PYTHON_EXPRESSION_PREFIX):
        return call_expression_function(value.strip(), registry, path, context)

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
    registry: Mapping[str, ExpressionFunction] | ExpressionRegistry | None = None,
    path: str = "value",
    context: ExpressionContext | None = None,
) -> Any:
    value_resolved = resolve_yaml_expression_values(value, registry=registry, path=path, context=context)
    template_context = value_resolved if isinstance(value_resolved, Mapping) else {}
    return resolve_template_strings(value_resolved, template_context, path)


def resolve_yaml_expression_values(
    value: Any,
    *,
    registry: Mapping[str, ExpressionFunction] | ExpressionRegistry | None = None,
    path: str = "value",
    context: ExpressionContext | None = None,
) -> Any:
    functions = normalize_expression_registry(registry)
    function_resolved = resolve_python_function_calls(value, functions, path, context)
    return resolve_env_references(function_resolved, path)


def freeze_expression_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({
            key: freeze_expression_value(item)
            for key, item in value.items()
        })

    if isinstance(value, list | tuple):
        return tuple(freeze_expression_value(item) for item in value)

    if isinstance(value, set | frozenset):
        return frozenset(freeze_expression_value(item) for item in value)

    return copy_value(value)


def expression_context(context: PageContext, project: ProjectPaths) -> ExpressionContext:
    return ExpressionContext(
        project=project,
        route=context.route,
        source_file=context.source_chain[-1] if context.source_chain else None,
        source_chain=context.source_chain,
        data=freeze_expression_value(context.data),
        site=freeze_expression_value(context.data.get("site") or {}),
        slots=freeze_expression_value(context.slots),
        article=str(context.slots.get("article") or ""),
    )


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


def normalize_resolved_page_fields(data: Mapping[str, Any]) -> dict[str, Any]:
    parsed_date = parse_date(data.get("date"))
    normalized = (
        deep_merge(data, {"date": parsed_date})
        if parsed_date
        else copy_value(data)
    )

    return (
        deep_merge(
            normalized,
            {"site": normalize_resolved_site_fields(normalized["site"])},
        )
        if isinstance(normalized.get("site"), Mapping)
        else normalized
    )


def resolve_site_expressions(
    site: Mapping[str, Any],
    *,
    registry: Mapping[str, ExpressionFunction] | ExpressionRegistry | None = None,
) -> dict[str, Any]:
    resolved = resolve_yaml_expressions({"site": site}, registry=registry, path="")
    return normalize_resolved_site_fields(mapping(resolved.get("site"), "site"))


def resolve_page_context_expressions(
    context: PageContext,
    *,
    project: ProjectPaths | None = None,
    registry: Mapping[str, ExpressionFunction] | ExpressionRegistry | None = None,
) -> PageContext:
    page_context = expression_context(context, project) if project is not None else None
    resolved_data = resolve_yaml_expressions(
        context.data,
        registry=registry,
        path=f"page:{context.route.url_path}",
        context=page_context,
    )
    data = normalize_resolved_page_fields(resolved_data) if isinstance(resolved_data, Mapping) else resolved_data

    return PageContext(
        route=context.route,
        data=data,
        slots=copy_value(context.slots),
        assets=context.assets,
        template=context.template,
        source_chain=context.source_chain,
    )
