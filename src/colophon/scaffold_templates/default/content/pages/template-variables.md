---
title: Template variables
summary: A reference page for the values available inside Jinja templates.
variable_groups:
  - title: Site and route
    variables:
      - name: site
        meaning: Site-wide data from content/site.yaml after defaults and expressions resolve.
      - name: page.route
        meaning: The current public route, such as /template-variables/.
      - name: page.source_chain
        meaning: The content files merged to build the current page.
  - title: Content values
    variables:
      - name: title
        meaning: The normalized page or post title.
      - name: article
        meaning: Rendered Markdown body for Markdown pages and posts.
      - name: toc
        meaning: Level-two Markdown headings captured as anchor data.
      - name: reading_minutes
        meaning: Estimated reading time for Markdown content.
  - title: Navigation data
    variables:
      - name: collections.posts
        meaning: Listed pages under /posts/, sorted by date descending by default.
      - name: pages.all
        meaning: Listed page summaries for the whole site.
      - name: pages.children
        meaning: Listed direct children of the current route.
      - name: pages.section
        meaning: Listed pages in the same first path segment.
  - title: Helpers
    variables:
      - name: image(name, variant)
        meaning: Resolve logical images, direct static assets, or external URLs; missing files fail the build.
      - name: public_url(path)
        meaning: Prefix a route with site.url for feeds and canonical links.
---

## Template context

Templates receive page data as top-level variables. This page is Markdown, so its body is rendered into `article`, and its front matter supplies `variable_groups`.

## Example

```jinja
<h1>{{ title }}</h1>
<p>Route: {{ page.route }}</p>
{% for post in collections.posts %}
  <a href="{{ post.url }}">{{ post.title }}</a>
{% endfor %}
```

The rendered list below is produced by `templates/simple.html` from this page's front matter.
