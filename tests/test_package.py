from __future__ import annotations

import os
import json
import subprocess
import sys
import tempfile
import tomllib
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import colophon
from colophon.build import resolve_required_vendor_assets
from colophon.content import load_site_config
from colophon.deploy.config import validate_deploy_config
from colophon.expressions import expression_registry, import_python_module, module_yaml_functions, resolve_yaml_expressions
from colophon.utils import copy_value
from colophon.vendor import load_vendor_config, vendor_url_for


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def replace_site_title(root: Path, title: str) -> None:
    path = root / "content" / "site.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace("title: Example Site", f"title: {title}"),
        encoding="utf-8",
    )


def read_site_output(root: Path, route: str) -> str:
    path = root / "_site" / route.strip("/") / "index.html"
    return path.read_text(encoding="utf-8")


def file_bytes_by_relative_path(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class ColophonPackageTests(unittest.TestCase):
    def test_public_entrypoints_are_curated_and_module_runnable(self) -> None:
        import colophon.core as core

        env = {
            **os.environ,
            "PYTHONPATH": str(SRC),
        }
        result = subprocess.run(
            [sys.executable, "-m", "colophon", "--help"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(
            sorted(core.__all__),
            [
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
            ],
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("usage: colophon", result.stdout)

    def test_packaging_metadata_declares_distribution_surface(self) -> None:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        project = metadata["project"]

        self.assertEqual(project["name"], "colophon-site")
        self.assertEqual(project["license"], "Apache-2.0")
        self.assertEqual(project["license-files"], ["LICENSE"])
        self.assertEqual(project["requires-python"], ">=3.11")
        self.assertEqual(metadata["project"]["scripts"]["colophon"], "colophon.cli:main")
        self.assertEqual(metadata["project"]["scripts"]["colophon-site"], "colophon.cli:main")
        self.assertTrue(hasattr(colophon, "build_site"))
        self.assertEqual(project["urls"]["Repository"], "https://github.com/AeonCypher/Colophon")
        self.assertIn("Topic :: Internet :: WWW/HTTP :: Site Management", project["classifiers"])
        self.assertNotIn("License :: OSI Approved :: Apache Software License", project["classifiers"])
        self.assertNotIn("paramiko>=3", project["dependencies"])
        self.assertEqual(project["optional-dependencies"]["sftp"], ["paramiko>=3"])
        self.assertEqual(
            metadata["tool"]["setuptools"]["exclude-package-data"]["colophon"],
            ["**/__pycache__/*", "**/*.py[cod]"],
        )

    def test_programmatic_build_result_manifest_and_write_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            site = root / "demo"
            manifest_path = root / "build-manifest.json"
            colophon.scaffold_site(site)

            result = colophon.build_site(
                colophon.project_from_config(site / "colophon.yml"),
                options=colophon.BuildOptions(build_time="2026-01-02T03:04:05Z"),
            )
            output_dir = result.output_dir
            expected_output_dir = (site / "_site").resolve()
            written = result.write_manifest(manifest_path)
            manifest = json.loads(written.read_text(encoding="utf-8"))

        self.assertIsInstance(result, colophon.BuildResult)
        self.assertEqual(output_dir, expected_output_dir)
        self.assertEqual(result.manifest.build_time, "2026-01-02T03:04:05+00:00")
        self.assertGreater(result.counts["pages"], 0)
        self.assertGreater(result.counts["posts"], 0)
        self.assertGreater(result.counts["static_assets"], 0)
        self.assertGreater(result.counts["generated_images"], 0)
        self.assertEqual(result.manifest_path, None)
        self.assertEqual(manifest["schema_version"], "1.0")
        self.assertEqual(manifest["build_time"], "2026-01-02T03:04:05+00:00")
        self.assertIn("pages", manifest)
        self.assertIn("posts", manifest)
        self.assertIn("generated_images", manifest)

    def test_cli_and_python_builds_produce_equivalent_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / "demo"
            colophon.scaffold_site(site)
            build_time = "2026-01-02T03:04:05Z"

            colophon.build_site(
                colophon.project_from_config(site / "colophon.yml", output="_site_python"),
                options=colophon.BuildOptions(build_time=build_time),
            )

            env = {
                **os.environ,
                "PYTHONPATH": str(SRC),
            }
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "colophon",
                    "build",
                    "--config",
                    str(site / "colophon.yml"),
                    "--output",
                    "_site_cli",
                    "--build-time",
                    build_time,
                    "--quiet",
                ],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            python_files = file_bytes_by_relative_path(site / "_site_python")
            cli_files = file_bytes_by_relative_path(site / "_site_cli")

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(cli_files, python_files)

    def test_cli_project_output_manifest_json_and_quiet_modes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            site = root / "demo"
            manifest_path = root / "manifest.json"
            colophon.scaffold_site(site)
            env = {
                **os.environ,
                "PYTHONPATH": str(SRC),
            }

            json_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "colophon",
                    "--project",
                    str(site),
                    "build",
                    "--output",
                    "_site_cli",
                    "--manifest",
                    str(manifest_path),
                    "--json",
                    "--build-time",
                    "2026-01-02T03:04:05Z",
                ],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            quiet_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "colophon",
                    "build",
                    "--project",
                    str(site),
                    "--output",
                    "_site_quiet",
                    "--quiet",
                ],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            payload = json.loads(json_result.stdout)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            cli_output_exists = (site / "_site_cli" / "index.html").exists()
            quiet_output_exists = (site / "_site_quiet" / "index.html").exists()

        self.assertEqual(json_result.returncode, 0)
        self.assertEqual(quiet_result.returncode, 0)
        self.assertEqual(quiet_result.stdout, "")
        self.assertTrue(cli_output_exists)
        self.assertTrue(quiet_output_exists)
        self.assertEqual(payload["manifest"]["build_time"], "2026-01-02T03:04:05+00:00")
        self.assertEqual(manifest["build_time"], "2026-01-02T03:04:05+00:00")

    def test_cli_and_api_report_readable_configuration_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.yml"
            env = {
                **os.environ,
                "PYTHONPATH": str(SRC),
            }
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "colophon",
                    "build",
                    "--config",
                    str(missing),
                ],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            with self.assertRaisesRegex(colophon.ProjectConfigError, "missing project config"):
                colophon.build_project(Path(tmp), config="missing.yml")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("configuration error:", result.stderr)
        self.assertIn("missing project config", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_atomic_build_preserves_previous_output_after_template_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / "demo"
            colophon.scaffold_site(site)
            project = colophon.project_from_config(site / "colophon.yml")
            colophon.build_site(
                project,
                options=colophon.BuildOptions(build_time="2026-01-02T03:04:05Z"),
            )
            previous = (site / "_site" / "index.html").read_bytes()
            (site / "templates" / "index.html").unlink()

            with self.assertRaises(colophon.TemplateBuildError):
                colophon.build_site(
                    project,
                    options=colophon.BuildOptions(build_time="2026-01-02T03:04:06Z"),
                )

            current = (site / "_site" / "index.html").read_bytes()

        self.assertEqual(current, previous)

    def test_two_configured_sites_build_independently_without_global_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first"
            second = Path(tmp) / "second"
            colophon.scaffold_site(first)
            colophon.scaffold_site(second)
            replace_site_title(first, "First Site")
            replace_site_title(second, "Second Site")

            colophon.build_site(colophon.project_from_config(first / "colophon.yml"))
            colophon.build_site(colophon.project_from_config(second / "colophon.yml"))

            first_html = (first / "_site" / "index.html").read_text(encoding="utf-8")
            second_html = (second / "_site" / "index.html").read_text(encoding="utf-8")

        self.assertIn("First Site", first_html)
        self.assertIn("Second Site", second_html)
        self.assertNotIn("Second Site", first_html)
        self.assertNotIn("First Site", second_html)

    def test_cli_scaffold_build_serve_and_deploy_dry_run_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / "demo"

            colophon.main(["scaffold", str(site)])
            colophon.main(["build", "--config", str(site / "colophon.yml")])

            with patch.dict(os.environ, {"EXAMPLE_FTP_PASSWORD": "secret"}, clear=False):
                colophon.main(["deploy", "--config", str(site / "colophon.yml"), "--dry-run"])
                with patch("colophon.cli.serve_site") as serve_site:
                    colophon.main(["serve", "--config", str(site / "colophon.yml"), "--test", "--port", "0"])

            rendered = site / "_site" / "index.html"
            rendered_exists = rendered.exists()

        self.assertTrue(rendered_exists)
        self.assertEqual(serve_site.call_args.kwargs["test"], True)

    def test_legacy_root_cli_flags_are_rejected(self) -> None:
        for argv in (["--deploy"], ["--serve"], ["--watch"], ["--test"]):
            with self.subTest(argv=argv), self.assertRaises(SystemExit) as raised:
                colophon.main(argv)

            self.assertEqual(raised.exception.code, 2)

    def test_strict_config_rejects_removed_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / "site"
            site.mkdir()

            write_text(site / "colophon.yml", "paths:\n  project: legacy\n")
            with self.assertRaisesRegex(colophon.ProjectConfigError, "paths.project"):
                colophon.project_from_config(site / "colophon.yml")

            write_text(site / "colophon.yml", "vendor:\n  require:\n    - webawesome\n")
            with self.assertRaisesRegex(colophon.ProjectConfigError, "vendor.require"):
                colophon.project_from_config(site / "colophon.yml")

        with self.assertRaisesRegex(colophon.DeployConfigError, "top-level deploy"):
            validate_deploy_config({"targets": {"production": {}}})

    def test_scaffold_site_documents_and_builds_feature_examples(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / "demo"
            colophon.scaffold_site(site)

            expected_files = {
                "README.md",
                "colophon.yml",
                "site_hooks.py",
                "content/pages/about.md",
                "content/pages/features.yml",
                "content/pages/template-variables.md",
                "content/pages/images.md",
                "content/pages/hooks.md",
                "content/pages/deploy.md",
                "content/posts/hello-world.md",
                "content/posts/second-post.md",
                "content/images/demo.ppm",
                "static/assets/demo.svg",
            }
            missing_files = [
                relative_path
                for relative_path in sorted(expected_files)
                if not (site / relative_path).exists()
            ]

            colophon.build_site(colophon.project_from_config(site / "colophon.yml"))

            outputs = {
                "home": (site / "_site" / "index.html").read_text(encoding="utf-8"),
                "about": read_site_output(site, "about"),
                "features": read_site_output(site, "features"),
                "variables": read_site_output(site, "template-variables"),
                "images": read_site_output(site, "images"),
                "hooks": read_site_output(site, "hooks"),
                "deploy": read_site_output(site, "deploy"),
                "archive": read_site_output(site, "archive"),
                "tag": read_site_output(site, "tags/demo"),
                "feed": (site / "_site" / "feed.xml").read_text(encoding="utf-8"),
            }
            static_asset_exists = (site / "_site" / "assets" / "demo.svg").exists()
            generated_images_exist = (site / "_site" / "images" / "generated").exists()

        self.assertEqual(missing_files, [])
        self.assertIn("content/pages/about.md", outputs["about"])
        self.assertIn("renders at <code>/about/</code>", outputs["about"])
        self.assertIn("Project config", outputs["features"])
        self.assertIn("collections.posts", outputs["variables"])
        self.assertIn("Generated logical image", outputs["images"])
        self.assertNotIn("exists=False", outputs["images"])
        self.assertIn("Resolved hook values", outputs["hooks"])
        self.assertIn("build_revision", outputs["hooks"])
        self.assertIn("first_paragraph", outputs["hooks"])
        self.assertIn("EXAMPLE_FTP_PASSWORD", outputs["deploy"])
        self.assertIn("Second scaffold post", outputs["archive"])
        self.assertIn("Hello world", outputs["tag"])
        self.assertIn("<title>Second scaffold post</title>", outputs["feed"])
        self.assertIn("https://github.com/AeonCypher/Colophon", outputs["home"])
        self.assertIn("/assets/demo.svg", outputs["images"])
        self.assertTrue(static_asset_exists)
        self.assertTrue(generated_images_exist)
        self.assertNotIn("BUILD: python::", outputs["home"])

    def test_scaffold_supports_named_default_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / "named"

            colophon.main(["scaffold", str(site), "--template", "default"])
            project = colophon.project_from_config(site / "colophon.yml")
            readme_exists = (site / "README.md").exists()

        self.assertTrue(readme_exists)
        self.assertEqual(project.vendor.mode, "auto")
        self.assertEqual(project.vendor.local_dir, "vendor")

    def test_scaffold_supports_template_dir_and_ignores_generated_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "template"
            destination = root / "site"
            write_text(
                source / "colophon.yml",
                """
paths:
  content: content
  templates: templates
  static: static
  output: _site
""",
            )
            write_text(source / "content" / "site.yaml", "site:\n  title: Custom\n")
            write_text(source / "_site" / "index.html", "generated")
            write_text(source / ".git" / "config", "generated")
            write_text(source / ".venv" / "pyvenv.cfg", "generated")
            write_text(source / "__pycache__" / "x.pyc", "generated")
            write_text(source / ".DS_Store", "generated")

            colophon.main(["scaffold", str(destination), "--template-dir", str(source)])

            copied = (destination / "content" / "site.yaml").read_text(encoding="utf-8")
            ignored_exists = [
                (destination / "_site" / "index.html").exists(),
                (destination / ".git" / "config").exists(),
                (destination / ".venv" / "pyvenv.cfg").exists(),
                (destination / "__pycache__" / "x.pyc").exists(),
                (destination / ".DS_Store").exists(),
            ]

        self.assertIn("Custom", copied)
        self.assertEqual(ignored_exists, [False, False, False, False, False])

    def test_scaffold_template_dir_requires_colophon_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "template"
            source.mkdir()

            with self.assertRaisesRegex(colophon.ProjectConfigError, "must contain colophon.yml"):
                colophon.scaffold_site(Path(tmp) / "site", template_dir=source)

    def test_custom_python_module_functions_are_loaded_and_copied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / "site"
            colophon.scaffold_site(site)
            write_text(
                site / "site_hooks.py",
                """
from __future__ import annotations

generated = {"items": [{"label": "original"}]}

def dynamic_value():
    return generated

YAML_FUNCTIONS = {"dynamic_value": dynamic_value}
""",
            )
            write_text(
                site / "content" / "site.yaml",
                """
site:
  title: Hook Site
  signal_line:
    VALUE: python::dynamic_value
""",
            )

            project = colophon.project_from_config(site / "colophon.yml")
            config = load_site_config(project)
            registry = module_yaml_functions(site / "site_hooks.py")
            result = resolve_yaml_expressions(
                {"value": "python::dynamic_value"},
                registry=registry,
            )
            result["value"]["items"][0]["label"] = "changed"
            module = import_python_module(site / "site_hooks.py")

        self.assertIn("VALUE: {'items': [{'label': 'original'}]}", config.data["site"]["signal_line"])
        self.assertEqual(module.generated["items"][0]["label"], "original")

    def test_custom_python_missing_module_and_duplicate_names_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / "site"
            colophon.scaffold_site(site)
            missing = colophon.project_from_config(site / "colophon.yml")
            missing = replace(
                missing,
                python_modules=(site / "missing_hooks.py",),
            )

            write_text(site / "one.py", "YAML_FUNCTIONS = {'same': lambda: 'one'}\n")
            write_text(site / "two.py", "YAML_FUNCTIONS = {'same': lambda: 'two'}\n")
            write_text(site / "three.py", "YAML_CONTEXT_FUNCTIONS = {'same': lambda context: 'three'}\n")
            duplicate = replace(
                missing,
                python_modules=(site / "one.py", site / "two.py"),
            )
            duplicate_across_registries = replace(
                missing,
                python_modules=(site / "one.py", site / "three.py"),
            )

            with self.assertRaisesRegex(colophon.ProjectConfigError, "missing Python extension"):
                expression_registry(missing)

            with self.assertRaisesRegex(colophon.ProjectConfigError, "duplicate YAML function"):
                expression_registry(duplicate)

            with self.assertRaisesRegex(colophon.ProjectConfigError, "duplicate YAML function"):
                expression_registry(duplicate_across_registries)

    def test_scaffold_site_builds_through_config_and_renders_public_features(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site_root = Path(tmp) / "site"
            colophon.scaffold_site(site_root)
            project = colophon.project_from_config(site_root / "colophon.yml")

            colophon.build_site(project)

            home = (site_root / "_site" / "index.html").read_text(encoding="utf-8")
            post = (site_root / "_site" / "posts" / "hello-world" / "index.html").read_text(
                encoding="utf-8"
            )
            feed_exists = (site_root / "_site" / "feed.xml").exists()
            static_asset_exists = (site_root / "_site" / "assets" / "demo.svg").exists()

        self.assertIn("Example Site", home)
        self.assertIn("Project repository", home)
        self.assertIn("This post is Markdown with YAML front matter", post)
        self.assertTrue(feed_exists)
        self.assertTrue(static_asset_exists)

    def test_vendor_config_parses_immutably(self) -> None:
        raw = {
            "mode": "local",
            "local_dir": "third-party",
            "required": ["webawesome"],
            "assets": {
                "dompurify": {
                    "enabled": True,
                    "local_path": "dompurify",
                    "required_files": ["purify.min.js"],
                    "files": {"purify.min.js": "file:///tmp/purify.min.js"},
                },
            },
        }
        original = copy_value(raw)

        config = load_vendor_config(raw)

        self.assertEqual(raw, original)
        self.assertEqual(config.mode, "local")
        self.assertEqual(config.local_dir, "third-party")
        self.assertEqual(config.required, ("webawesome",))
        self.assertEqual(dict(config.assets)["dompurify"].enabled, True)

    def test_vendor_url_resolution_uses_cdn_auto_and_local_modes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / "site"
            colophon.scaffold_site(site)
            write_text(
                site / "colophon.yml",
                """
paths:
  content: content
  templates: templates
  static: static
  output: _site
vendor:
  mode: cdn
  assets:
    dompurify:
      enabled: true
""",
            )
            cdn_project = colophon.project_from_config(site / "colophon.yml")
            write_text(
                site / "colophon.yml",
                """
paths:
  content: content
  templates: templates
  static: static
  output: _site
vendor:
  mode: auto
  assets:
    dompurify:
      enabled: true
""",
            )
            auto_project = colophon.project_from_config(site / "colophon.yml")
            write_text(site / "static" / "vendor" / "dompurify" / "purify.min.js", "purify")

            cdn_url = vendor_url_for(
                cdn_project,
                ("dompurify",),
                "dompurify",
                "purify.min.js",
            )
            auto_url = vendor_url_for(
                auto_project,
                ("dompurify",),
                "dompurify",
                "purify.min.js",
            )

        self.assertEqual(cdn_url, "https://cdn.jsdelivr.net/npm/dompurify@3.2.6/dist/purify.min.js")
        self.assertEqual(auto_url, "/vendor/dompurify/purify.min.js")

    def test_local_vendor_mode_fails_when_required_files_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / "site"
            colophon.scaffold_site(site)
            write_text(
                site / "colophon.yml",
                """
paths:
  content: content
  templates: templates
  static: static
  output: _site
  deploy: content/deploy.example.yaml
python:
  modules:
    - site_hooks.py
vendor:
  mode: local
  assets:
    webawesome:
      enabled: true
""",
            )
            project = colophon.project_from_config(site / "colophon.yml")

            with self.assertRaisesRegex(colophon.ProjectConfigError, "vendor download"):
                colophon.build_site(project)

            output_exists = (site / "_site").exists()

        self.assertFalse(output_exists)

    def test_mastodon_config_auto_requires_browser_vendor_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / "site"
            colophon.scaffold_site(site)
            write_text(
                site / "content" / "site.yaml",
                """
site:
  title: Vendor Site
  mastodon:
    enabled: true
    host: social.example
    user: alice
    user_id: "123"
    profile_name: "@alice"
    timeline:
      enabled: true
""",
            )
            write_text(
                site / "content" / "index.yml",
                """
template: page
title: Home
sidebar:
  cards:
    - type: mastodon_timeline
""",
            )
            write_text(
                site / "content" / "posts" / "hello-world.md",
                """---
title: Hello world
slug: hello-world
date: 2026-01-01
summary: The first generated post.
tags:
  - demo
status: published
mastodon_comments:
  status_url: https://social.example/@alice/123456
---

## Hello
""",
            )
            project = colophon.project_from_config(site / "colophon.yml")

            assets = resolve_required_vendor_assets(project)

        self.assertIn("dompurify", assets)
        self.assertIn("font-awesome", assets)
        self.assertIn("mastodon-comments", assets)
        self.assertIn("mastodon-embed-timeline", assets)

    def test_vendor_download_dry_run_and_local_file_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / "site"
            source = Path(tmp) / "source" / "test.js"
            target = site / "static" / "vendor" / "test-lib" / "test.js"
            colophon.scaffold_site(site)
            write_text(source, "console.log('test');")
            write_text(
                site / "colophon.yml",
                f"""
paths:
  content: content
  templates: templates
  static: static
  output: _site
vendor:
  mode: local
  assets:
    test-lib:
      enabled: true
      local_path: test-lib
      required_files:
        - test.js
      files:
        test.js: {source.as_uri()}
""",
            )

            colophon.main([
                "vendor",
                "download",
                "--config",
                str(site / "colophon.yml"),
                "--asset",
                "test-lib",
                "--dry-run",
            ])
            dry_run_exists = target.exists()
            colophon.main([
                "vendor",
                "download",
                "--config",
                str(site / "colophon.yml"),
                "--asset",
                "test-lib",
            ])
            target_text = target.read_text(encoding="utf-8")

        self.assertFalse(dry_run_exists)
        self.assertEqual(target_text, "console.log('test');")


if __name__ == "__main__":
    unittest.main()
