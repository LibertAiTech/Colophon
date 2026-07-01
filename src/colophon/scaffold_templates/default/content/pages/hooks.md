---
title: Custom Python hooks
summary: python::first_paragraph
docs_links: python::blogroll_links
hook_values:
  build_revision: python::build_revision
  last_updated: python::last_updated
  read_time: python::read_time
  first_paragraph: python::first_paragraph
  site_stats: python::site_stats
  recently_changed_pages: python::recently_changed_pages
  first_link: "{{ docs_links[0].label }}"
---

## Python module loading

`colophon.yml` declares `site_hooks.py` under `python.modules`. During build, Colophon imports that trusted local module and reads its `YAML_FUNCTIONS` and `YAML_CONTEXT_FUNCTIONS` registries.

## YAML usage

```yaml
summary: python::first_paragraph
last_updated: python::last_updated
```

Zero-argument hooks work in site config. Context hooks work in page/frontmatter data and receive the current route, source file, source chain, page data, site data, slots, and rendered article. Duplicate names and missing functions fail with a path-aware error.
