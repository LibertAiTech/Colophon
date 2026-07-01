---
title: Images
summary: Examples of generated image variants and direct static assets.
image_examples:
  - title: Generated logical image
    image: demo_card
    variant: card
    text: Uses content/images.yml plus content/images/demo.ppm and writes a derivative under _site/images/generated/.
  - title: Square variant
    image: demo_card
    variant: square
    text: Uses the square variant defined under images.demo_card.variants.
  - title: Direct static asset
    image: /assets/demo.svg
    text: Resolves a file copied directly from static/assets/demo.svg.
---

## Logical images

Logical images are configured in `content/images.yml` and stored under `content/images/`.

```yaml
images:
  demo_card:
    file: demo.ppm
    width: 640
    height: 360
    variants:
      square:
        width: 240
        height: 240
```

## Template helper

```jinja
{% set card = image("demo_card", "square") %}
{% if card.exists %}
  <img src="{{ card.url }}" alt="{{ card.alt }}">
{% endif %}
```
