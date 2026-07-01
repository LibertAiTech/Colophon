"""Command-line parsing and dispatch for Colophon.

Arguments are validated into a ``ProjectPaths`` value, then routed to build,
serve, deploy, scaffold, or vendor subsystems while preserving the same build
path exposed to Python callers.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from pathlib import Path
from typing import Any

from .build import build_site, resolve_required_vendor_assets
from .deploy.pipeline import deploy_site
from .errors import ColophonError
from .models import BuildOptions, BuildResult
from .project import DEFAULT_CONFIG_FILE, project_from_inputs
from .scaffold import scaffold_site
from .serve import serve_site
from .vendor import download_vendor_assets


def add_output_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--quiet", action="store_true", default=argparse.SUPPRESS, help="Suppress normal progress output.")
    parser.add_argument("--verbose", action="count", default=argparse.SUPPRESS, help="Show more diagnostic output.")
    parser.add_argument("--debug", action="store_true", default=argparse.SUPPRESS, help="Show tracebacks for unexpected failures.")


def add_project_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", default=argparse.SUPPRESS, help="Project root to use for relative config and paths.")
    parser.add_argument("--config", default=argparse.SUPPRESS, help="Path to colophon.yml.")
    parser.add_argument("--content", default=argparse.SUPPRESS, help="Override the configured content directory.")
    parser.add_argument("--templates", default=argparse.SUPPRESS, help="Override the configured templates directory.")
    parser.add_argument("--static", default=argparse.SUPPRESS, help="Override the configured static directory.")
    parser.add_argument("--output", default=argparse.SUPPRESS, help="Override the configured output directory.")


def add_build_result_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--manifest", default=argparse.SUPPRESS, help="Write a machine-readable build manifest JSON file.")
    parser.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="Print the build result as JSON.")
    parser.add_argument("--build-time", default=argparse.SUPPRESS, help="Build timestamp as ISO-8601 text or epoch seconds.")


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    add_output_arguments(parser)
    add_project_arguments(parser)


def project_from_args(args: argparse.Namespace):
    return project_from_inputs(
        getattr(args, "project", "."),
        config=getattr(args, "config", DEFAULT_CONFIG_FILE),
        content=getattr(args, "content", None),
        templates=getattr(args, "templates", None),
        static=getattr(args, "static", None),
        output=getattr(args, "output", None),
    )


def build_options_from_args(args: argparse.Namespace) -> BuildOptions:
    return BuildOptions(
        manifest_path=getattr(args, "manifest", None),
        build_time=getattr(args, "build_time", None),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="colophon")
    add_common_arguments(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Build the static site.")
    add_common_arguments(build)
    add_build_result_arguments(build)

    serve = subparsers.add_parser("serve", help="Build and serve the static site.")
    add_common_arguments(serve)
    serve.add_argument("--watch", action="store_true", default=argparse.SUPPRESS, help="Rebuild on file changes.")
    serve.add_argument("--test", action="store_true", default=argparse.SUPPRESS, help="Serve briefly, then stop.")
    serve.add_argument("--port", type=int, default=argparse.SUPPRESS)

    deploy = subparsers.add_parser("deploy", help="Build, announce, and upload the site.")
    add_common_arguments(deploy)
    deploy.add_argument("--target", default=argparse.SUPPRESS, help="Deploy target name from deploy config.")
    deploy.add_argument("--post-id", default=argparse.SUPPRESS, help="Post slug to announce instead of the configured selector.")
    deploy.add_argument("--dry-run", action="store_true", default=argparse.SUPPRESS, help="Show deploy actions without posting or uploading.")
    deploy.add_argument("--force-post", action="store_true", default=argparse.SUPPRESS, help="Create a new Mastodon post even when one is already linked.")

    scaffold = subparsers.add_parser("scaffold", help="Create a boring demo site.")
    add_output_arguments(scaffold)
    scaffold.add_argument("path", help="Directory to create.")
    scaffold.add_argument("--force", action="store_true", default=argparse.SUPPRESS, help="Allow scaffolding into an existing empty directory.")
    scaffold_source = scaffold.add_mutually_exclusive_group()
    scaffold_source.add_argument("--template", default=argparse.SUPPRESS, help="Packaged scaffold template name.")
    scaffold_source.add_argument("--template-dir", default=argparse.SUPPRESS, help="Local scaffold template directory containing colophon.yml.")

    vendor = subparsers.add_parser("vendor", help="Manage browser vendor assets.")
    add_output_arguments(vendor)
    vendor_subparsers = vendor.add_subparsers(dest="vendor_command")
    vendor_download = vendor_subparsers.add_parser("download", help="Download browser vendor assets locally.")
    add_common_arguments(vendor_download)
    vendor_download.add_argument("--asset", action="append", default=argparse.SUPPRESS, help="Vendor asset name to download.")
    vendor_download.add_argument("--force", action="store_true", default=argparse.SUPPRESS, help="Overwrite existing local vendor files.")
    vendor_download.add_argument("--dry-run", action="store_true", default=argparse.SUPPRESS, help="Show planned downloads without writing files.")

    return parser


def summarize_build(result: BuildResult) -> str:
    page_count = sum(
        result.counts.get(key, 0)
        for key in ("pages", "posts", "archive_pages", "tag_pages", "feeds")
    )
    asset_count = sum(
        result.counts.get(key, 0)
        for key in ("static_assets", "content_assets", "generated_images")
    )
    return f"built {result.output_dir} ({page_count} output page(s), {asset_count} asset(s))"


def print_build_result(result: BuildResult, args: argparse.Namespace) -> None:
    if getattr(args, "json", False):
        print(json.dumps(result.to_dict(), sort_keys=True))
        return

    if getattr(args, "quiet", False):
        return

    print(summarize_build(result))

    if getattr(args, "manifest", None):
        print(f"manifest: {Path(args.manifest)}")

    if getattr(args, "verbose", 0):
        for key, value in sorted(result.counts.items()):
            print(f"{key}: {value}")


def quietable_call(args: argparse.Namespace, function: Any, *items: Any, **kwargs: Any) -> Any:
    if not getattr(args, "quiet", False):
        return function(*items, **kwargs)

    with contextlib.redirect_stdout(io.StringIO()):
        return function(*items, **kwargs)


def dispatch(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if args.command == "scaffold":
        scaffold_site(
            Path(args.path),
            force=getattr(args, "force", False),
            template=getattr(args, "template", "default"),
            template_dir=Path(args.template_dir) if getattr(args, "template_dir", None) else None,
        )
        return 0

    if args.command == "vendor":
        if args.vendor_command != "download":
            parser.error("vendor requires a subcommand")

        project = project_from_args(args)
        names = tuple(getattr(args, "asset", ())) or resolve_required_vendor_assets(project)
        actions = download_vendor_assets(
            project,
            names,
            force=getattr(args, "force", False),
            dry_run=getattr(args, "dry_run", False),
        )

        if not getattr(args, "quiet", False):
            for action in actions:
                print(action)

        return 0

    project = project_from_args(args)

    if args.command == "deploy":
        quietable_call(
            args,
            deploy_site,
            project=project,
            target=getattr(args, "target", None),
            post_id=getattr(args, "post_id", None),
            dry_run=getattr(args, "dry_run", False),
            force_post=getattr(args, "force_post", False),
        )
        return 0

    result = build_site(project, options=build_options_from_args(args))
    print_build_result(result, args)

    if args.command == "serve":
        serve_site(
            getattr(args, "port", 8000),
            project=project,
            watch=getattr(args, "watch", False),
            test=getattr(args, "test", False),
        )

    return 0


def format_error(error: ColophonError) -> str:
    return f"{error.category} error: {error}"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return dispatch(args, parser)
    except ColophonError as exc:
        if getattr(args, "debug", False):
            raise

        print(format_error(exc), file=sys.stderr)
        return exc.exit_code
    except Exception as exc:
        if getattr(args, "debug", False):
            raise

        print(f"internal error: {exc}", file=sys.stderr)
        return 70
