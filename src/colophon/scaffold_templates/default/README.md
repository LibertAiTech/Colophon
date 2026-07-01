# Colophon demo site

This is a deliberately plain scaffold. It is meant to show how Colophon projects are wired, not to provide a finished theme.

## Commands

Build the site:

```bash
colophon build --config colophon.yml
```

Serve with rebuilds:

```bash
colophon serve --config colophon.yml --watch --port 8000
```

Download configured browser vendor assets for local/offline builds:

```bash
colophon vendor download --config colophon.yml
```

Try deploy resolution without uploading:

```bash
EXAMPLE_FTP_PASSWORD=dummy colophon deploy --config colophon.yml --dry-run
```

## What to inspect

- `content/site.yaml` defines site-wide data, navigation, route rules, and template aliases.
- `content/index.yml` is a YAML page rendered at `/`.
- `content/pages/about.md` is a static Markdown page rendered at `/about/`.
- `content/pages/features.yml` is a structured YAML page rendered at `/features/`.
- `content/pages/template-variables.md` explains the variables templates receive.
- `content/pages/images.md` demonstrates logical images, generated variants, and direct static assets.
- `content/pages/hooks.md` shows `python::` expressions loaded from `site_hooks.py`.
- `content/pages/deploy.md` explains `content/deploy.example.yaml` and dry-run deploys.
- `content/posts/` contains two posts so archive, tags, related posts, and feed output are visible.
- `templates/` contains the Jinja files used by each route type.
- `static/` is copied directly into `_site/`.
- `vendor` in `colophon.yml` controls browser dependencies such as WebAwesome,
  DOMPurify, Font Awesome, and Mastodon widgets.

## Custom Python

`site_hooks.py` exports `YAML_FUNCTIONS` for zero-argument hooks and `YAML_CONTEXT_FUNCTIONS` for page/frontmatter hooks. YAML content can call either form with `python::function_name`; the scaffold uses this for the header signal line, homepage links, generated summaries, page statistics, and the hooks page.
