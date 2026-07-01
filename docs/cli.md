# CLI Guide

[README](../README.md) | [Authorship](authorship.md) | [Site design](site-design.md) | [Publishing](publishing.md) | [Python API](python-api.md) | [Reference](reference.md)

Colophon installs two console commands:

- `colophon`: primary command
- `colophon-site`: alias matching the PyPI distribution name

Both commands run the same CLI.

## Install

```bash
python -m pip install colophon-site
```

Pinned GitHub install:

```bash
python -m pip install git+https://github.com/AeonCypher/Colophon.git@v0.1.0
```

Optional SFTP support:

```bash
python -m pip install 'colophon-site[sftp]'
python -m pip install 'colophon-site[sftp] @ git+https://github.com/AeonCypher/Colophon.git@v0.1.0'
```

## Common Flags

Global flags:

```bash
colophon --config colophon.yml build
colophon --project /path/to/site build
colophon --quiet build --config colophon.yml
colophon --verbose build --config colophon.yml
colophon --debug build --config colophon.yml
```

Build and serve accept quick path overrides:

```bash
colophon build --config colophon.yml --content draft-content --output _preview
colophon serve --config colophon.yml --templates experimental-templates --port 8000
```

## `build`

Build writes static output to the configured output directory, usually `_site/`.

```bash
colophon build --config colophon.yml
colophon build --config colophon.yml --output _preview
```

Automation output:

```bash
colophon build --config colophon.yml --json --quiet
colophon build --config colophon.yml --manifest build-manifest.json
colophon build --config colophon.yml --json --manifest build-manifest.json
```

Repeatable build time:

```bash
colophon build --config colophon.yml --build-time 2026-01-02T03:04:05Z
SOURCE_DATE_EPOCH=1767225600 colophon build --config colophon.yml
```

## `serve`

Serve builds the site and starts a local HTTP server.

```bash
colophon serve --config colophon.yml --port 8000
colophon serve --config colophon.yml --watch --port 8000
```

With `--watch`, Colophon snapshots configured content, templates, static files, config, and Python modules. A change triggers a rebuild.

Watch builds are atomic by default. Colophon renders into a temporary output directory and only replaces the served output after a successful rebuild. If a rebuild fails, the previous successful site remains available.

Smoke-test mode starts and stops the server:

```bash
colophon serve --config colophon.yml --watch --test
```

## `scaffold`

Create a neutral demo site:

```bash
colophon scaffold ./new-site
colophon scaffold ./new-site --template default
colophon scaffold ./new-site --template-dir ./my-scaffold-template
```

Use `--force` only when the destination is empty or when you intentionally want scaffold files overwritten.

## `vendor download`

Download configured browser vendor assets for local/offline builds:

```bash
colophon vendor download --config colophon.yml
colophon vendor download --config colophon.yml --asset webawesome --force
colophon vendor download --config colophon.yml --dry-run
```

Templates should use `vendor_url(name, path)` instead of hardcoded CDN or local paths.

## `deploy`

Deploy runs configured publication steps: build checks, optional Mastodon posting/comment enablement, final build, and upload.

```bash
colophon deploy --config colophon.yml --target production --dry-run
colophon deploy --config colophon.yml --target production
colophon deploy --config colophon.yml --post-id first-note --dry-run
colophon deploy --config colophon.yml --force-post
```

Dry-run behavior:

- builds still run
- Mastodon status text is rendered but not posted
- comment status metadata is not written
- upload and purge actions are planned but not executed

See [Publishing](publishing.md) for deploy config and provider recipes.

## Errors

User-facing failures are reported without tracebacks by default:

```text
configuration error: missing project config: /path/to/colophon.yml
template error: /about/: failed to render template 'simple.html': ...
```

Use `--debug` when you need the Python traceback.

Related: [Publishing](publishing.md), [Python API](python-api.md), [Reference](reference.md).
