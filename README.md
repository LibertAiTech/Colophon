# Colophon

Colophon is a small static site generator for content-driven sites. It reads YAML and Markdown content, renders Jinja templates, resolves trusted local Python hooks, creates image derivatives, builds archives/tags/RSS, serves with optional watch mode, and can run a config-driven deploy flow.

## Quick Start

Install Colophon into a Python environment:

```bash
python -m pip install colophon
```

SFTP deploy support is optional:

```bash
python -m pip install 'colophon[sftp]'
```

Run the package from this repo during development:

```bash
cd colophon_repo
PYTHONPATH=src .venv/bin/python -m colophon scaffold /private/tmp/colophon-demo --force
PYTHONPATH=src .venv/bin/python -m colophon build --config /private/tmp/colophon-demo/colophon.yml
PYTHONPATH=src .venv/bin/python -m colophon serve --config /private/tmp/colophon-demo/colophon.yml --watch --port 8000
```

After installing the package into an environment, use the console command directly:

```bash
colophon build --config colophon.yml
colophon serve --config colophon.yml --watch --port 8000
colophon vendor download --config colophon.yml
colophon deploy --config colophon.yml --target production --dry-run
colophon scaffold ./new-site
colophon scaffold ./new-site --template default
colophon scaffold ./new-site --template-dir ./my-scaffold-template
```

Builds can run from outside the project root with explicit paths:

```bash
colophon --project /path/to/site build --output _preview
colophon build --config /path/to/site/colophon.yml --manifest /tmp/colophon-manifest.json
colophon build --config colophon.yml --json --quiet --build-time 2026-01-02T03:04:05Z
```

Build the sibling `libertaitech` site while working in this split workspace:

```bash
cd ../libertaitech
PYTHONPATH=../colophon_repo/src ../colophon_repo/.venv/bin/python -m colophon build --config colophon.yml
```

Run the framework test suite:

```bash
cd ../colophon_repo
PYTHONPATH=src .venv/bin/python -m unittest discover -v
```

## Project Layout

A Colophon site is wired through `colophon.yml`. The generator does not need to live inside the site.

```text
my-site/
  colophon.yml
  site_hooks.py
  content/
    site.yaml
    index.yml
    images.yml
    post-sidebar.yml
    pages/about.md
    posts/hello-world.md
  templates/
    base.html
    index.html
    post.html
    simple.html
    archive.html
    tag.html
    feed.xml
  static/
    styles.css
    vendor/
  _site/
```

`content/`, `templates/`, `static/`, and `_site/` are defaults. They can be changed in config or with CLI overrides.

## `colophon.yml`

The project config tells Colophon where the site lives and which local Python modules are trusted extension points.

```yaml
paths:
  content: content
  templates: templates
  static: static
  output: _site
  deploy: content/deploy.yaml
python:
  modules:
    - site_hooks.py
vendor:
  mode: auto
  local_dir: vendor
  assets:
    webawesome:
      enabled: false
```

Path values are resolved relative to the config file unless they are absolute. `paths.deploy` is the only deploy-config path key.
`vendor.mode` may be `auto`, `cdn`, or `local`; `auto` uses local files when present and CDN URLs otherwise.

Colophon validates config strictly. Use mappings where mappings are documented, sequences where sequences are documented, and real booleans such as `true` or `false`; aliases and shorthand forms such as `paths.project`, `paths.deploy_config`, `vendor.require`, scalar lists, boolean strings, and asset boolean shorthand are rejected.

Every command accepts `--config`. Build and serve also accept quick path overrides:

```bash
colophon build --config colophon.yml --content draft-content --output _preview
colophon serve --config colophon.yml --templates experimental-templates --port 8000
```

The loaded project is immutable during a build, so two independent site roots can build in the same Python process without monkeypatching global paths.

## Python API

Import Colophon from Python when integrating with scripts, CI, editors, or deployment tools:

```python
from colophon import BuildOptions, build_project, build_site, project_from_config

result = build_project(
    "/path/to/site",
    output="_preview",
    manifest_path="/tmp/colophon-manifest.json",
    build_time="2026-01-02T03:04:05Z",
)

print(result.output_dir)
print(result.counts["pages"])
print(result.manifest.to_dict()["posts"])
```

`build_project()` accepts a project root plus the same path overrides as the CLI. `build_site()` accepts an explicit immutable `ProjectPaths` value:

```python
project = project_from_config("/path/to/site/colophon.yml", output="_preview")
result = build_site(project, options=BuildOptions(build_time=0))
```

Both entry points return `BuildResult`. It includes the output directory, a `BuildManifest`, warnings, duration, counts, `to_dict()`, and `write_manifest(path)`. Library calls raise typed `ColophonError` subclasses instead of exiting the Python process. The CLI catches those errors and exits with shell status codes.

Public library imports are intentionally curated through `colophon` / `colophon.core`. Internal modules may change between releases.

## Build Results and Manifests

Every successful build returns an in-memory manifest. Writing a manifest JSON file is opt-in with `--manifest`, `BuildOptions(manifest_path=...)`, or `BuildResult.write_manifest(path)`.

The manifest contains:

- schema version, Colophon version, project root, output directory, and build time
- generated pages and posts with routes, templates, source chains, size, and SHA-256
- archive pages, tag pages, and feeds
- copied static assets, content image assets, colocated content assets, and generated image derivatives
- skipped files and warnings, when relevant

Use `--json` to print the full build result for automation:

```bash
colophon build --config colophon.yml --json --manifest build-manifest.json
```

For repeatable builds, pass `--build-time`, `BuildOptions(build_time=...)`, or set `SOURCE_DATE_EPOCH`. That single timestamp is used for feed rendering and build metadata.

## Content Files

`content/site.yaml` defines site-wide data, template mapping, and route rules:

```yaml
site:
  title: Example Site
  description: A site generated by Colophon.
  url: https://example.test
  nav:
    - label: Home
      href: /

templates:
  default: index.html
  page: index.html
  post: post.html
  static: simple.html

routes:
  - match: /posts/**
    template: post
  - match: /**
    template: page
```

`content/index.yml` becomes `/`. YAML pages are useful for structured homepage data such as hero text, feature lists, sidebar cards, and collection definitions.

`content/pages/about.md` becomes `/about/`. Files inside `content/pages/` route without the `pages` prefix, so `content/pages/docs/install.md` becomes `/docs/install/`.

`content/posts/hello-world.md` becomes `/posts/hello-world/`. Posts use YAML front matter plus Markdown body:

```markdown
---
title: Hello world
slug: hello-world
date: 2026-01-01
summary: The first post.
tags:
  - demo
status: published
---

## Heading

Markdown body.
```

Support files do not create pages: `site.yaml`, `images.yml`, `post-sidebar.yml`, `deploy.yaml`, and files under `content/images/`.

## Markdown and Page Data

Markdown is rendered with support for headings, tables, strikethrough, task lists, definition lists, inline URLs, and inline HTML. Level-two headings become `toc` entries:

```markdown
## Install

This heading appears in `toc`.
```

Markdown pages and posts receive defaults such as `title`, `slug`, `url`, `summary`, `tags`, `toc`, and `reading_minutes`. YAML front matter can override those values.

Set `draft: true` or `listed: false` to keep a page out of collections, archives, tags, and feeds while still allowing it to render if it has a route.

## Template Variables

Templates receive the merged page data as top-level variables. Common values include:

| Variable | Meaning |
| --- | --- |
| `site` | Data from `content/site.yaml` after defaults and expressions resolve. |
| `title`, `summary`, `date`, `tags` | Page or post front matter and normalized defaults. |
| `article` | Rendered Markdown body for Markdown files. |
| `toc` | List of level-two headings from Markdown. |
| `page.route` | Current public route, such as `/about/`. |
| `page.source_chain` | Content files merged to build the page. |
| `post` | Alias for the current context, useful in post templates. |
| `collections.posts` | Default date-desc collection of listed pages under `/posts/`. |
| `pages.all` | Listed page summaries for the whole site. |
| `pages.children` | Listed direct children of the current route. |
| `pages.section` | Listed pages in the same first path segment. |
| `assets` | Colocated source assets copied for this page. |
| `uses_mastodon_timeline` | Whether the current page needs timeline browser assets. |

Useful globals and filters:

```jinja
{{ public_url(page.route) }}
{{ image("cover", "card").url }}
{{ vendor_url("webawesome", "webawesome.loader.js") }}
{{ vendor_enabled("mastodon-comments") }}
{{ date | date }}
{{ title | slugify }}
```

`collections` can be customized per page:

```yaml
collections:
  demo_posts:
    under: /posts/
    tag: demo
    sort: title asc
    limit: 5
```

## Template Selection and Routing

Template selection uses this order:

1. `template` or `bindings.template` in the content file.
2. The most specific matching route rule in `content/site.yaml`.
3. `templates.default`.

Static pages under `content/pages/` default to the `static` template unless they set their own template.

`routes` accepts exact paths and prefix globs ending in `/**`:

```yaml
routes:
  - match: /posts/**
    template: post
  - match: /**
    template: page
```

## YAML Expressions

YAML values can call trusted zero-argument Python functions or read environment variables.

```yaml
site:
  signal_line:
    BUILD: python::demo_status
    AUTHOR: "{{ site.author }}"

deploy:
  targets:
    production:
      password: env::EXAMPLE_FTP_PASSWORD
```

Expression resolution is recursive and copy-on-write. Function results are copied before being merged into page data, so later template work cannot mutate module-owned values.

Missing functions, duplicate function names, failed imports, and missing environment variables raise errors that include the YAML path where resolution failed.

## Custom Python Hooks

Custom Python lives in site-owned modules declared by `colophon.yml`.

```python
from __future__ import annotations


def demo_status() -> str:
    return "READY"


def docs_links() -> list[dict[str, str]]:
    return [
        {"label": "About", "href": "/about/"},
        {"label": "Archive", "href": "/archive/"},
    ]


YAML_FUNCTIONS = {
    "demo_status": demo_status,
    "docs_links": docs_links,
}
```

`YAML_FUNCTIONS` may be a mapping or a zero-argument function returning a mapping. Names must be unique across built-ins and all loaded modules. Custom code is trusted local code and runs during build.

Built-in functions are also available:

- `python::generate_random_color`
- `python::generate_random_temperature`
- `python::get_moon_phase`

## Images and Static Assets

Static files under `static/` are copied to the output root. For example, `static/styles.css` becomes `/styles.css`, and `static/assets/demo.svg` becomes `/assets/demo.svg`.

Content images live under `content/images/` and are described by logical names in `content/images.yml`:

```yaml
images:
  demo_card:
    file: demo.ppm
    alt: Generated demo image
    width: 640
    height: 360
    fit: cover
    crop: auto
    variants:
      thumb:
        width: 320
        height: 180
```

Use the `image()` helper in templates:

```jinja
{% set card = image("demo_card", "thumb") %}
<img src="{{ card.url }}" alt="{{ card.alt }}" width="{{ card.width }}" height="{{ card.height }}">
```

The result includes `exists`, `url`, `alt`, `class`, `width`, `height`, `fit`, `position`, `ratio`, `label`, `size`, and `fallback`.

Direct image paths are also supported:

```jinja
{{ image("/assets/demo.svg").url }}
{{ image("/images/original.png").url }}
{{ image("https://example.test/image.jpg").url }}
```

Missing logical image names, missing configured image files, and missing direct `/images/` or `/assets/` files fail the build with an asset error. Generated derivatives are written under `_site/images/generated/`.

## Browser Vendor Assets

Vendor assets are configured in `colophon.yml` under `vendor`. Built-ins include `webawesome`, `dompurify`, `font-awesome`, `mastodon-comments`, and `mastodon-embed-timeline`.

```yaml
vendor:
  mode: auto
  local_dir: vendor
  required:
    - webawesome
  assets:
    dompurify:
      enabled: true
```

Templates should use `vendor_url(name, path)` instead of hardcoded CDN or local paths:

```jinja
<script defer src="{{ vendor_url('dompurify', 'purify.min.js') }}"></script>
```

`auto` mode returns local URLs such as `/vendor/dompurify/purify.min.js` when the required files exist under `static/vendor/`; otherwise it returns CDN URLs. `cdn` always returns CDN URLs. `local` requires the files to exist and fails the build with a message to run:

```bash
colophon vendor download --config colophon.yml
```

Download selected assets with:

```bash
colophon vendor download --config colophon.yml --asset webawesome --force
colophon vendor download --config colophon.yml --dry-run
```

## Archives, Tags, and Feeds

Every build creates:

- `/archive/` from `templates/archive.html`
- `/tags/<tag>/` from `templates/tag.html`
- `/feed.xml` from `templates/feed.xml`

These pages use listed post summaries sorted by date descending. Tag routes are slugified from post tags.

## Mastodon Timeline and Comments

Mastodon support is static-site friendly. Colophon loads strict config and renders data needed by templates and browser-side components, but it does not fetch timelines during build.

Site-level timeline config lives under `site.mastodon`:

```yaml
site:
  mastodon:
    enabled: true
    host: social.example
    user: alice
    user_id: "123"
    profile_name: "@alice"
    timeline:
      enabled: true
      max_posts_show: 3
```

Post comments can be enabled with explicit fields or a status URL:

```yaml
mastodon_comments:
  status_url: https://social.example/@alice/123456
```

Templates can check normalized `mastodon_comments.enabled` and `uses_mastodon_timeline`.
When those features render, Colophon marks the needed browser assets as active:
DOMPurify, Font Awesome, and Mastodon comments for comment threads, and
Mastodon embed timeline for timeline cards.

## Deploy

Deploy is optional and fully config-driven. A typical dry-run config:

```yaml
deploy:
  default_target: production
  steps:
    - preflight_build
    - build
    - upload
  targets:
    production:
      transport: ftps
      host: example.test
      username: deploy
      password: env::EXAMPLE_FTP_PASSWORD
      remote_path: public_html/example.test/
      purge: true
```

Run without side effects:

```bash
EXAMPLE_FTP_PASSWORD=dummy colophon deploy --config colophon.yml --target production --dry-run
```

Supported upload transports are `ftp`, `ftps`, `sftp`, and `sshfs`. SFTP requires the optional package extra:

```bash
python -m pip install 'colophon[sftp]'
```

The default deploy step list is:

```yaml
steps:
  - preflight_build
  - mastodon_post
  - enable_comments
  - build
  - upload
```

`mastodon_post` renders `deploy.mastodon.post_text` with `site` and selected `post` data. `enable_comments` can write the resulting status URL back to the selected post unless the run is a dry run.

Remote purge has safety checks: the target must include a configured `remote_path`, and dry-run reports actions without uploading or deleting remote files.

Deploy is a convenience layer for already-generated static output. It runs configured build steps through the same result-returning build pipeline as the CLI and Python API, and build failures stop deploy before upload.

## Serve and Watch

`serve` builds from the configured output directory and starts a local HTTP server:

```bash
colophon serve --config colophon.yml --watch --port 8000
```

With `--watch`, Colophon snapshots the configured content, templates, static directory, config file, and Python modules. A change triggers a rebuild and keeps serving the same output directory.

Builds are atomic by default. Watch mode renders into a temporary sibling output directory and only replaces the served output after a successful rebuild. If a rebuild fails, the previous successful site remains available and the watch process prints the typed failure category and message.

Static assets, content images, generated image derivatives, archive pages, tag pages, and feeds are refreshed on each successful rebuild.

`--test` on the `serve` command starts the server briefly and stops automatically. It is intended for smoke tests.

## Scaffold

Create a neutral demo site:

```bash
colophon scaffold ./new-site
cd ./new-site
colophon build --config colophon.yml
```

The scaffold is intentionally plain. It demonstrates the feature set with concrete files and generated pages instead of inheriting any real site theme.

The generated footer includes a placeholder Colophon project link at `https://github.com/your-org/colophon`; replace it in `content/site.yaml` when the real repository URL is ready.

Use `--force` only when the destination is empty or when you intentionally want scaffold files overwritten.

## Logging and Errors

Normal CLI builds print a short success summary. `--quiet` suppresses normal output for scripts and CI. `--verbose` prints build counts, and `--json` prints the machine-readable `BuildResult`.

User-facing failures are reported without tracebacks by default:

```text
configuration error: missing project config: /path/to/colophon.yml
template error: /about/: failed to render template 'simple.html': ...
```

Use `--debug` when you need the Python traceback. Programmatic callers can catch `ColophonError` or specific subclasses such as `ProjectConfigError`, `ExpressionResolutionError`, `TemplateBuildError`, `AssetError`, `DeployConfigError`, and `DeployError`.

## Troubleshooting

- `missing project config`: pass `--config` or run from a directory containing `colophon.yml`.
- `unknown YAML function`: declare the function in a module listed under `python.modules`.
- `duplicate YAML function name`: rename one function or remove one module.
- `missing environment variable`: export the required variable or use `--dry-run` with dummy values for deploy tests.
- Template errors around undefined values: check the content file and template variable names.
- Missing images fail the build; inspect `content/images.yml`, direct image references, and `content/images/`.
- Deploy upload errors usually come from missing host/user/path/password values or network credentials.

## Migration Notes

Colophon is designed to be version-controlled separately from a site. In this workspace, `colophon_repo/` is the generator repo and `libertaitech/` is the first external consumer.

Local development command from `libertaitech/`:

```bash
PYTHONPATH=../colophon_repo/src ../colophon_repo/.venv/bin/python -m colophon build --config colophon.yml
```

Backward compatibility with the old embedded generator layout is intentionally removed. Migrate by:

- running explicit commands such as `colophon build`, `colophon serve`, `colophon deploy`, `colophon scaffold`, or `colophon vendor download` instead of root-level legacy flags
- using `build_project()` or passing an explicit `ProjectPaths` to `build_site(project, ...)`
- using `paths.deploy`, `vendor.required`, mapping-based vendor asset config, and mapping-based `mastodon_comments`
- replacing Mastodon timeline camelCase config keys with snake_case keys such as `container_id`, `max_posts_show`, and `hide_reblogs`
- making every logical image in `content/images.yml` point to an existing file under `content/images/`

## Versioning and Compatibility

Colophon uses semantic versioning. Patch releases preserve documented behavior except for bug fixes. Minor releases may add compatible features. Major releases may remove deprecated behavior or make larger compatibility changes.

The CLI commands and the public Python facade exported from `colophon` / `colophon.core` are the documented compatibility surface. Internal modules remain available for Colophon development and tests, but they are not promised as stable integration APIs.

When practical, behavior that is documented and working should receive a deprecation path before removal. Clearly broken, unsafe, or previously undocumented behavior may be fixed directly.

# Authorship

Initial Authors are a join collaboration between Shea Valentine and Aeon Cypher. 
