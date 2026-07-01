# Colophon

Colophon is a content-first static site generator for YAML, Markdown, Jinja templates, trusted local Python hooks, image derivatives, RSS, Mastodon-aware pages, and config-driven deploys.

Colophon will publish to PyPI as `colophon-site`. The Python package and primary CLI command remain `colophon`.

## Quickstart

Install Colophon:

```bash
python -m pip install colophon-site
```

Until the first PyPI release is available, pin the GitHub release tag:

```bash
python -m pip install git+https://github.com/AeonCypher/Colophon.git@v0.1.0
```

Create, build, and serve a site:

```bash
colophon scaffold ./my-site
cd ./my-site
colophon build --config colophon.yml
colophon serve --config colophon.yml --watch --port 8000
```

The `colophon-site` CLI alias is also installed:

```bash
colophon-site build --config colophon.yml
```

SFTP deploy support is optional:

```bash
python -m pip install 'colophon-site[sftp]'
python -m pip install 'colophon-site[sftp] @ git+https://github.com/AeonCypher/Colophon.git@v0.1.0'
```

## Why Use Colophon?

- Content-first authoring with Markdown, YAML pages, frontmatter, and Jinja templates.
- Strict builds that fail early for bad config, missing images, unknown hooks, and unsafe deploy targets.
- Trusted local Python hooks when static content needs computed values without a plugin system.
- Static output for cheap hosting, with deploy recipes for FTP, FTPS, SFTP, and SSHFS.
- Built-in support for image variants, archive/tag/feed pages, Mastodon comments, and Mastodon timelines.
- No frontend bundler by default.

## Documentation

- [CLI guide](docs/cli.md): install variants, commands, common flags, JSON output, manifests, and dry-runs.
- [Authorship guide](docs/authorship.md): Markdown, YAML pages, frontmatter, collections, YAML expressions, and author-facing Python hooks.
- [Site design guide](docs/site-design.md): project layout, config, templates, routes, static assets, vendor assets, images, and template helpers.
- [Publishing guide](docs/publishing.md): deploy config, provider recipes, Mastodon setup, feeds, archive/tag output, and repeatable builds.
- [Python API guide](docs/python-api.md): embedded API, public facade, build results, manifests, deploy calls, and errors.
- [Template reference](docs/template-reference.md): complete template globals, filters, object shapes, image fields, Mastodon fields, and stability notes.
- [Reference](docs/reference.md): compatibility policy, config key reference, troubleshooting, release expectations, and support boundaries.
- [Changelog](CHANGELOG.md): release notes and release checklist.
- [Contributing](CONTRIBUTING.md): development setup, architecture, coding style, and tests.

## Development

Run commands from this repository root:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -v
PYTHONPATH=src .venv/bin/python -m colophon --help
```

The package uses a `src/` layout. During local development, either install the package into the environment or set `PYTHONPATH=src`.

## AI Usage
This application, including some parts of the code and documenation, were created with the assistance of AI tools. 