# Authorship Guide

[README](../README.md) | [CLI](cli.md) | [Site design](site-design.md) | [Publishing](publishing.md) | [Python API](python-api.md) | [Reference](reference.md)

This guide covers the content authoring model: Markdown, YAML pages, frontmatter, collections, expressions, and author-facing hooks.

## First Page

`content/index.yml` becomes `/`:

```yaml
template: page
title: Home
summary: A small site built with Colophon.
hero:
  title: Field Notes
  subtitle: Notes, essays, and release logs.
```

`content/pages/about.md` becomes `/about/`:

```markdown
---
title: About
summary: About this site.
---

## Hello

This is a Markdown page.
```

`content/posts/first-note.md` becomes `/posts/first-note/`.

## Markdown

Markdown is rendered with support for headings, tables, strikethrough, task lists, definition lists, inline URLs, and inline HTML. Level-two headings become table-of-contents entries:

```markdown
## Install

This heading appears in `toc`.
```

Markdown pages and posts receive defaults such as `title`, `slug`, `url`, `summary`, `tags`, `toc`, and `reading_minutes`. Frontmatter can override those values.

## YAML Pages

YAML pages are useful for structured homepages, feature grids, sidebars, and page-specific collection definitions.

```yaml
template: page
title: Home
feature_cards:
  - title: Content first
    text: YAML data flows directly into Jinja templates.
```

Non-index YAML files render when they are under `content/pages/`, set `render: true`, or set a template.

Support files do not create pages:

- `site.yaml`
- `images.yml`
- `post-sidebar.yml`
- `deploy.yaml`
- files under `content/images/`

## Frontmatter

Recommended post frontmatter:

```yaml
title:
date: python::get_date
summary: python::first_paragraph
tags:
status: published
listed: true
cover:
mastodon_comments: true
```

`python::get_date` and `python::first_paragraph` are examples from the scaffold's `site_hooks.py`; they only work after you register those functions. Literal values work too.

Arbitrary frontmatter fields pass through to templates:

```yaml
series: release-notes
content_warning: Discusses unreleased software.
canonical_url: https://example.com/original
```

Reserved keys are `references`, `bindings`, `slot`, and `render`.

## Listing and Collections

Set `draft: true` or `listed: false` to keep a page out of collections, archives, tags, and feeds while still allowing it to render if it has a route.

`collections.posts` is the default date-desc collection of listed pages under `/posts/`.

Pages can define additional collections:

```yaml
collections:
  demo_posts:
    under: /posts/
    tag: demo
    sort: title asc
    limit: 5
```

Collection query fields:

- `under`: include pages under a route prefix
- `template`: include pages with a template value
- `tag`: include pages containing a tag
- `sort`: `date asc`, `date desc`, `title asc`, `title desc`, or route fallback
- `limit`: maximum number of items

## YAML Expressions

Expression forms:

```yaml
field: python::function_name
password: env::SECRET_NAME
label: "{{ site.title }} archive"
```

Resolution order:

1. `python::` functions
2. `env::` variables
3. Jinja strings containing `{{ ... }}`

Function results are copied before they are merged into page data. Page data is normalized again after expression resolution, so `date: python::get_date` can return either a date object or a parseable date string.

Missing functions, duplicate names, failed imports, and missing environment variables raise errors with the YAML path that failed.

## Python Hooks

> Warning: do not build untrusted Colophon sites. Python hooks execute arbitrary local code during build. Treat a Colophon site repository like source code, not like inert content.

Declare trusted hook modules in `colophon.yml`:

```yaml
python:
  modules:
    - site_hooks.py
```

Zero-argument hooks work anywhere expressions are resolved:

```python
import os


def build_revision() -> str:
    return os.environ.get("GITHUB_SHA", "local")


def blogroll_links() -> list[dict[str, str]]:
    return [{"label": "Example", "href": "https://example.com"}]


def deploy_password() -> str:
    return os.environ["EXAMPLE_FTP_PASSWORD"]


YAML_FUNCTIONS = {
    "build_revision": build_revision,
    "blogroll_links": blogroll_links,
    "deploy_password": deploy_password,
}
```

Context hooks work in page/frontmatter data and receive an immutable `ExpressionContext`:

```python
from colophon import ExpressionContext


def first_paragraph(context: ExpressionContext) -> str:
    return context.article.split("<p>", 1)[1].split("</p>", 1)[0]


def last_updated(context: ExpressionContext) -> str:
    source = context.source_file.absolute_path if context.source_file else None
    return str(source.stat().st_mtime_ns) if source and source.exists() else ""


def site_stats(context: ExpressionContext) -> dict[str, int]:
    files = [path for path in context.project.content_dir.rglob("*.md")]
    return {"markdown_files": len(files)}


YAML_CONTEXT_FUNCTIONS = {
    "first_paragraph": first_paragraph,
    "last_updated": last_updated,
    "site_stats": site_stats,
}
```

Other practical hooks include `read_time`, `recently_changed_pages`, environment-backed deploy passwords, and `build_revision`.

Related: [Site design](site-design.md), [Template reference](template-reference.md), [Publishing](publishing.md).
