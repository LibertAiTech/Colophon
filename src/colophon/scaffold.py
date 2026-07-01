"""Scaffold starter-site copying.

Package-data or local template files flow into a target project directory while
preserving overwrite safety rules.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

from .errors import ProjectConfigError


IGNORED_TEMPLATE_NAMES = frozenset({"_site", ".git", "__pycache__", ".DS_Store", ".venv"})


def scaffold_templates_root():
    return resources.files("colophon").joinpath("scaffold_templates")


def packaged_scaffold_root(template: str = "default"):
    root = scaffold_templates_root().joinpath(template)

    if root.is_dir():
        return root

    raise ProjectConfigError(f"unknown scaffold template: {template}")


def local_scaffold_root(template_dir: Path):
    root = template_dir.expanduser().resolve()

    if not root.is_dir():
        raise ProjectConfigError(f"missing scaffold template directory: {root}")

    if not (root / "colophon.yml").is_file():
        raise ProjectConfigError(f"scaffold template directory must contain colophon.yml: {root}")

    return root


def scaffold_source_root(template: str = "default", template_dir: Path | None = None):
    return local_scaffold_root(template_dir) if template_dir else packaged_scaffold_root(template)


def scaffold_file_entries(root=None, prefix: Path = Path()):
    current = packaged_scaffold_root() if root is None else root
    files = (
        [(prefix / entry.name, entry)]
        if entry.is_file()
        else scaffold_file_entries(entry, prefix / entry.name)
        if entry.is_dir() and entry.name not in IGNORED_TEMPLATE_NAMES
        else []
        for entry in current.iterdir()
        if entry.name not in IGNORED_TEMPLATE_NAMES
    )
    return sorted(
        (item for group in files for item in group),
        key=lambda item: item[0].as_posix(),
    )


def scaffold_site(
    target: Path,
    *,
    force: bool = False,
    template: str = "default",
    template_dir: Path | None = None,
) -> None:
    destination = target.expanduser().resolve()
    source_root = scaffold_source_root(template, template_dir)

    if destination.exists() and any(destination.iterdir()) and not force:
        raise ProjectConfigError(f"refusing to scaffold into non-empty directory: {destination}")

    destination.mkdir(parents=True, exist_ok=True)
    for relative_path, entry in scaffold_file_entries(source_root):
        path = destination / relative_path

        if path.exists() and not force:
            raise ProjectConfigError(f"refusing to overwrite existing file: {path}")

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(entry.read_bytes())
