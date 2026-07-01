# Template Reference

[README](../README.md) | [CLI](cli.md) | [Authorship](authorship.md) | [Site design](site-design.md) | [Publishing](publishing.md) | [Python API](python-api.md) | [Reference](reference.md)

Templates are Jinja files loaded from the configured templates directory. Colophon-specific values below are the documented template API.

## Stable Globals

| Name | Type | Meaning |
| --- | --- | --- |
| `site` | mapping | Site-wide data from `content/site.yaml` after defaults and expressions resolve. |
| `public_url(path)` | function | Returns `site.url` plus a route/path, or the path when `site.url` is empty. |
| `image(name_or_path, variant=None, post=None)` | function | Resolves logical images, direct `/assets/` or `/images/` paths, or external URLs. |
| `vendor_url(name, path="")` | function | Returns a CDN or local vendor asset URL according to vendor config. |
| `vendor_enabled(name)` | function | Returns whether a vendor asset is active for the current build. |

## Stable Filters

| Name | Meaning |
| --- | --- |
| `date` | Formats date-like values as `Month D, YYYY`; returns text for other values. |
| `slugify` | Slugifies text for routes, IDs, and tag URLs. |
| `fmt` | Applies Python string formatting using `site` values. |
| `tojson` | Jinja built-in available for JSON script blocks. |

## Current Page Values

Templates receive merged page data as top-level variables. Stable values:

| Name | Type | Meaning |
| --- | --- | --- |
| `title` | string | Page/post title. |
| `slug` | string | Last route segment or frontmatter override. |
| `url` | string | Public route. |
| `summary` | string | Summary/description. |
| `date` | date/string | Parsed date when available. |
| `tags` | list | Tags for posts and pages. |
| `toc` | list | Level-two Markdown headings as `{id, text}` mappings. |
| `reading_minutes` | int | Estimated Markdown reading time. |
| `article` | HTML string | Rendered Markdown body. |
| `assets` | list | Colocated source assets copied for this page. |
| `cover` | string | Recommended logical cover image key. |
| `cover_image` | string | Legacy cover image key, still supported. |
| `mastodon_comments` | mapping | Normalized Mastodon comment config. |
| `uses_mastodon_timeline` | bool | Whether the current page activates timeline browser assets. |
| `post` | mapping | Alias for the current context, useful in post templates. |

Arbitrary frontmatter fields are also available, but only the fields above are stable unless documented elsewhere.

## Page Object

`page` is stable:

| Field | Type | Meaning |
| --- | --- | --- |
| `page.route` | string | Current public route. |
| `page.source_chain` | list | Content files merged to build the page. |

## Page Summary Shape

Page summaries appear in `collections.*`, `pages.*`, `related`, archive pages, tag pages, and feeds.

Stable fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `route` | string | Public route. |
| `url` | string | Alias for route. |
| `source_path` | string | Primary content source path. |
| `section` | string | First route segment. |
| `depth` | int | Route depth. |
| `slug` | string | Slug. |
| `title` | string | Title. |
| `date` | date/string | Date. |
| `summary` | string | Summary. |
| `tags` | list | Tags. |
| `template` | string | Template alias or name. |
| `reading_minutes` | int | Reading time. |
| `cover` | string | Recommended cover key. |
| `cover_image` | string | Cover image key. |
| `sidebar_image` | string | Sidebar image key. |
| `image` | string | Preferred image key. |
| `data` | mapping | Full copied page data; internal convenience, not stable field-by-field. |

## Collections

`collections.posts` is stable and contains listed pages under `/posts/`, sorted by date descending.

Pages can define extra collections:

```yaml
collections:
  demo_posts:
    under: /posts/
    tag: demo
    template: post
    sort: title asc
    limit: 5
```

Collection query fields:

| Field | Meaning |
| --- | --- |
| `under` | Include pages under a route prefix. |
| `template` | Include pages with a template value. |
| `tag` | Include pages containing a tag. |
| `sort` | `date asc`, `date desc`, `title asc`, `title desc`, or route fallback. |
| `limit` | Maximum number of items. |

## Page Graph

`pages` is stable:

| Field | Meaning |
| --- | --- |
| `pages.all` | Listed page summaries for the whole site. |
| `pages.children` | Listed direct children of the current route. |
| `pages.section` | Listed pages in the same first path segment, excluding current route. |

## Image Object

`image()` returns a mapping. Stable fields:

| Field | Meaning |
| --- | --- |
| `exists` | Whether the image resolved. Missing configured images fail before templates finish. |
| `key` | Logical image key when available. |
| `url` | Public URL. |
| `alt` | Alt text. |
| `class` | Optional class from config. |
| `width` | Width. |
| `height` | Height. |
| `fit` | Resize fit mode. |
| `position` | Crop/object position. |
| `ratio` | Aspect ratio. |
| `label` | Human-readable label. |
| `size` | Generated variant size. |
| `fallback` | Fallback metadata when configured. |

Internal convenience fields may appear during development; avoid relying on undocumented image fields.

## Mastodon Fields

`site.mastodon` stable fields:

| Field | Meaning |
| --- | --- |
| `enabled` | Whether Mastodon support is enabled. |
| `host` | Instance host. |
| `instance_url` | Normalized instance URL. |
| `user` | Username without `@`. |
| `user_id` | Account ID for timeline widgets. |
| `profile_name` | Display profile name such as `@alice`. |
| `timeline.enabled` | Whether timeline widgets are enabled. |
| `timeline.container_id` | Browser widget container ID. |
| `timeline.options` | Browser-widget options; stable as rendered data, not stable field-by-field beyond Colophon config keys. |

`mastodon_comments` stable fields:

| Field | Meaning |
| --- | --- |
| `enabled` | True only when host, user, and toot ID are known. |
| `host` | Instance host. |
| `user` | Username. |
| `toot_id` | Status ID. |
| `filter` | Optional browser-widget filter. |
| `lang` | Optional language. |

## Archive, Tag, and Feed Templates

Auxiliary templates receive:

- `archive.html`: `site`, `posts`, `tags`
- `tag.html`: `site`, `tag`, `posts`, `tags`
- `feed.xml`: `site`, `posts`, `build_date`

`posts` uses the page summary shape above.

## Stability Notes

Stable API:

- globals and filters listed above
- current page fields listed above
- page summary fields listed above
- collection query fields listed above
- image fields listed above
- Mastodon fields listed above

Internal convenience:

- `data` contents inside page summaries beyond copied frontmatter
- undocumented nested helper fields
- raw browser-widget option names under `site.mastodon.timeline.options`

Related: [Site design](site-design.md), [Authorship](authorship.md), [Reference](reference.md).
