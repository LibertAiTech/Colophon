# Python API Guide

[README](../README.md) | [CLI](cli.md) | [Authorship](authorship.md) | [Site design](site-design.md) | [Publishing](publishing.md) | [Reference](reference.md)

Colophon can be embedded from Python for scripts, CI, editors, and deployment tools. Public imports are curated through `colophon` and `colophon.core`.

## Public Facade

Stable public entry points:

- `build_project`
- `build_site`
- `deploy_site`
- `project_from_config`
- `scaffold_site`
- `serve_site`
- `main`
- `BuildOptions`
- `BuildResult`
- `BuildManifest`
- `BuildMessage`
- `ManifestEntry`
- `ExpressionContext`
- documented error classes

Internal modules may change between releases.

## Build a Site

Use `build_project()` when you want Colophon to load the project from a root/config path:

```python
from colophon import build_project

result = build_project(
    "/path/to/site",
    output="_preview",
    manifest_path="/tmp/colophon-manifest.json",
    build_time="2026-01-02T03:04:05Z",
)

print(result.output_dir)
print(result.counts["pages"])
```

Use `project_from_config()` and `build_site()` when you want an explicit immutable project value:

```python
from colophon import BuildOptions, build_site, project_from_config

project = project_from_config("/path/to/site/colophon.yml", output="_preview")
result = build_site(project, options=BuildOptions(build_time=0))
```

## Build Options

`BuildOptions` fields:

- `manifest_path`: optional manifest JSON path
- `build_time`: datetime, ISO string, Unix timestamp, or `None`
- `atomic`: render into a temporary output directory before publishing output

## Build Result

`BuildResult` includes:

- `project`
- `output_dir`
- `manifest`
- `warnings`
- `duration_seconds`
- `counts`
- `manifest_path`
- `to_dict()`
- `write_manifest(path)`

```python
manifest_path = result.write_manifest("/tmp/manifest.json")
payload = result.to_dict()
```

## Manifests

The manifest includes:

- schema version, Colophon version, project root, output directory, and build time
- generated pages and posts with routes, templates, source chains, size, and SHA-256
- archive pages, tag pages, and feeds
- copied static assets, content image assets, colocated content assets, and generated image derivatives
- skipped files and warnings

For repeatable builds, pass `BuildOptions(build_time=...)` or set `SOURCE_DATE_EPOCH`.

## Deploy from Python

```python
from colophon import deploy_site, project_from_config

project = project_from_config("/path/to/site/colophon.yml")
result = deploy_site(
    project,
    target="production",
    post_id="first-note",
    dry_run=True,
)

print(result["upload_actions"])
```

`deploy_site()` returns a dictionary containing target, selected post slug, status URL, whether a post/upload happened, dry-run state, and upload actions.

Tests can inject a Mastodon poster or transport uploaders:

```python
result = deploy_site(
    project,
    dry_run=False,
    mastodon_poster=lambda config, text, dry_run: {"url": "https://social.example/@alice/1"},
    transport_uploaders={"ftps": lambda target, source_dir, dry_run: ["fake upload"]},
)
```

## Errors

Library calls raise typed `ColophonError` subclasses instead of exiting the Python process. The CLI catches those errors and exits with shell status codes.

Common error classes:

- `ProjectConfigError`
- `ContentError`
- `ExpressionResolutionError`
- `TemplateBuildError`
- `AssetError`
- `DeployConfigError`
- `DeployError`

Related: [CLI](cli.md), [Publishing](publishing.md), [Reference](reference.md).
