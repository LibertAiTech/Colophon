# Contributing to Colophon

Colophon is organized as a small pipeline of mostly pure components with side
effects kept at the edges. When changing the project, prefer moving data through
explicit function arguments and immutable dataclasses instead of reintroducing
shared mutable globals.

## Development Setup

Run commands from this repository root:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -v
PYTHONPATH=src .venv/bin/python -m colophon --help
```

The package uses a `src/` layout. During local development, either install the
package into the environment or set `PYTHONPATH=src`.

## Component Map

`colophon.core` is only a facade. It should stay small and export
stable entry points such as `build_site`, `deploy_site`, `scaffold_site`,
`serve_site`, `project_from_config`, `build_project`, and `main`.
Internal behavior belongs in the subsystem modules below.

| Component | Responsibility |
| --- | --- |
| `cli.py` | Argument parsing and command dispatch. It wires project loading to build, serve, deploy, and scaffold commands. |
| `project.py` | Strict project path resolution from `colophon.yml` and explicit CLI/API overrides. |
| `models.py` | Frozen dataclasses and callable type aliases shared across the pipeline. |
| `errors.py` | Domain-specific exception classes. |
| `utils.py` | Low-level pure helpers for copying, merging, YAML loading, strict schema checks, dates, routes, and public URLs. |
| `expressions.py` | YAML expression resolution, `env::` references, `python::` hook calls, expression registries, and Jinja-in-YAML rendering. |
| `mastodon.py` | Strict site-level Mastodon config loading, timeline/comment defaults, host parsing, and status URL parsing. |
| `markdown.py` | Markdown rendering, table-of-contents generation, text statistics, and reading-time estimation. |
| `content.py` | Content discovery, route discovery, source chains, layer loading, page context construction, site config loading, and post sidebar loading. |
| `collections.py` | Page summaries, collection selection/sorting, page graph attachment, post detection, related posts, and post enrichment. |
| `images.py` | Image config loading, content image copying, derivative generation, smart crop positioning, and the Jinja `image()` resolver. |
| `vendor.py` | Browser vendor asset config, dependency expansion, CDN/local URL resolution, local preflight checks, and downloads. |
| `render.py` | Jinja environment creation, filters/globals, template selection, output path resolution, page rendering, and archive/tag/feed rendering. |
| `build.py` | Build orchestration: load config, discover content, build contexts, create render jobs, copy assets, render pages, and render auxiliary pages. |
| `serve.py` | Input snapshotting, watch/rebuild loop, and local HTTP serving. |
| `scaffold.py` | Copying package-data scaffold files into a new site. |
| `scaffold_templates/` | Named scaffold source trees. `default/` is the only packaged scaffold source. |
| `deploy/config.py` | Strict deploy config loading, validation, defaults, target selection data, and secret redaction. |
| `deploy/mastodon.py` | Deploy post selection, Mastodon post text rendering, status posting, and source metadata write-back for comments. |
| `deploy/transports.py` | FTP, FTPS, SFTP, and SSHFS upload side effects plus dry-run upload planning. |
| `deploy/pipeline.py` | Deploy step orchestration and the public `deploy_site()` implementation. |

## Dependency Direction

Keep imports flowing from orchestration toward lower-level components. Avoid
cycles by following this shape:

```text
cli
  -> project
  -> build
  -> serve
  -> scaffold
  -> deploy.pipeline

build
  -> content
  -> collections
  -> render
  -> images
  -> vendor

content
  -> models
  -> utils
  -> markdown
  -> expressions
  -> mastodon

render
  -> models
  -> utils
  -> images
  -> vendor

deploy.pipeline
  -> build
  -> deploy.config
  -> deploy.mastodon
  -> deploy.transports
```

The main rule is that side-effectful modules should not become shared utility
dependencies. For example, `deploy/transports.py` may depend on normalized
config and low-level helpers, but rendering and content loading must not depend
on deploy transports.

## Data Flow

A normal build moves through these stages:

1. `cli.py` or a caller creates a `ProjectPaths` value with `project.py`.
2. `build.py` loads `SiteConfig`, image config, and sidebar config.
3. `content.py` scans files, discovers routes, builds source chains, and creates base `PageContext` values.
4. `expressions.py` resolves `env::`, `python::`, and Jinja expressions in config and page data.
5. `collections.py` attaches page graphs, collections, related posts, and post-specific data.
6. `images.py` prepares the Jinja image resolver and copies image assets.
7. `render.py` selects templates and writes HTML, archive pages, tag pages, and RSS.
8. `build.py` coordinates output reset and static/content asset copying.

A deploy run adds these stages:

1. `deploy/config.py` loads and validates deploy settings.
2. `deploy/pipeline.py` runs configured deploy steps in order.
3. `deploy/mastodon.py` selects the post, renders post text, optionally posts to Mastodon, and writes comment status metadata.
4. `build.py` performs the final build after comment metadata changes.
5. `deploy/transports.py` uploads the built output or returns dry-run upload actions.

## Placement Guidelines

Put new code where the question it answers naturally belongs:

| Question | Put it in |
| --- | --- |
| Where is this project on disk? | `project.py` |
| How is YAML or hook data resolved? | `expressions.py` |
| What source files exist and what route do they create? | `content.py` |
| What does a page summary or collection contain? | `collections.py` |
| How is Markdown converted to HTML? | `markdown.py` |
| How are templates selected and rendered? | `render.py` |
| How are image derivatives made? | `images.py` |
| What sequence builds the site? | `build.py` |
| What sequence deploys the site? | `deploy/pipeline.py` |
| How does a remote upload happen? | `deploy/transports.py` |
| What should a generated starter site contain? | `scaffold_templates/default/` |

If a helper is useful across many modules, first check `utils.py`. Add to it
only when the helper is pure, small, and does not pull in a subsystem dependency.

## Coding Style

Prefer pure functions, explicit data flow, and immutable state transitions.
Most pipeline objects are frozen dataclasses in `models.py`; use
`dataclasses.replace()` when a stage needs to return an updated value.

Avoid mutating caller-owned mappings and lists. Use `copy_value()` and
`deep_merge()` for copy-on-write updates. Prefer returning new dictionaries,
lists, tuples, and dataclass instances over updating arguments in place.

Keep repeated structural behavior data-driven. Route matching, deploy step
dispatch, function registries, and transport uploaders should remain mappings
from names to behavior instead of branch-heavy command logic.

## Public Interfaces

The stable public facade is `colophon.core`. Do not add internal helpers to
`core.py` for convenience. Import subsystem APIs directly in tests and internal
code.

`colophon.__main__` should import `main` from `colophon.cli`, and the console
script in `pyproject.toml` should continue pointing at `colophon.cli:main`.

## Scaffold Files

Scaffold content lives under `src/colophon/scaffold_templates/default/` and is
copied by `scaffold.py` with `importlib.resources`. Update scaffold examples by
editing those files directly.

Do not reintroduce a large Python dictionary of scaffold file literals. Also
avoid adding generated caches or build artifacts under `scaffold_templates/`;
they may be packaged as user-visible starter files.

## Testing Expectations

For behavior changes, add or update tests that exercise the real pipeline.
Prefer integrated tests over mocks unless the dependency is a network, upload,
or process boundary. Deploy tests should use dry-run mode, injected Mastodon
posters, or injected transport uploaders instead of making live network calls.

Use these checks before handing off changes:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -v
PYTHONPATH=src .venv/bin/python -m colophon --help
```

If `pytest` is available in the environment, this should also pass:

```bash
PYTHONPATH=src .venv/bin/python -m pytest
```

The current suite is written with `unittest`.

## Review Checklist

Before opening a change, verify:

- `core.py` remains a curated facade.
- Imports follow the dependency direction above.
- Side effects stay in build, scaffold, serve, deploy, image file generation, or transport boundaries.
- New helpers do not mutate inputs.
- Scaffold changes are real files under `scaffold_templates/default/`.
- Tests cover the behavior through public subsystem APIs or the CLI.
