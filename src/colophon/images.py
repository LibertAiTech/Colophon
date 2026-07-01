"""Image configuration, asset copying, and derivative generation.

Image definitions and page references flow into a Jinja ``image()`` resolver that
returns direct assets or generated resized derivatives.
"""

from __future__ import annotations

import re
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from slugify import slugify

from .errors import AssetError
from .expressions import expression_registry, resolve_yaml_expression_values
from .models import ProjectPaths, RenderJob
from .utils import copy_value, deep_merge, load_wrapped_yaml, mapping

from PIL import Image, ImageFilter, ImageOps


DEFAULT_IMAGE = {
    "alt": "",
    "class": "",
    "crop": "",
    "fit": "cover",
    "position": "50% 50%",
    "quality": 85,
    "label": "",
    "size": "",
    "fallback": {},
}


AUTO_CROP_SAMPLE_EDGE = 96


AUTO_CROP_MIN_MEAN_SIGNAL = 1.0


def load_images(project: ProjectPaths) -> dict[str, Any]:
    resolved_project = project
    return mapping(
        resolve_yaml_expression_values(
            load_wrapped_yaml(list(resolved_project.image_configs), unwrap="images"),
            registry=expression_registry(resolved_project),
            path="images",
        ),
        "images",
    )


def copy_content_images(project: ProjectPaths) -> tuple[tuple[Path, Path], ...]:
    resolved_project = project

    if not resolved_project.content_images_dir.exists():
        return ()

    copied: list[tuple[Path, Path]] = []

    for source in sorted(resolved_project.content_images_dir.rglob("*")):
        if not source.is_file():
            continue

        destination = resolved_project.output_dir / "images" / source.relative_to(resolved_project.content_images_dir)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append((source, destination))

    return tuple(copied)


def copy_referenced_assets(
    render_jobs: list[RenderJob],
    project: ProjectPaths,
) -> tuple[tuple[tuple[Path, Path], ...], tuple[str, ...]]:
    resolved_project = project
    copied: list[tuple[Path, Path]] = []
    skipped: list[str] = []

    for asset in sorted({asset for job in render_jobs for asset in job.page_context.assets}):
        source = resolved_project.content_dir / asset
        destination = resolved_project.output_dir / asset

        if source.exists() and source.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied.append((source, destination))
        else:
            skipped.append(asset)

    return tuple(copied), tuple(skipped)


def direct_image_source(path_or_url: str, project: ProjectPaths) -> Path | None:
    resolved_project = project

    if path_or_url.startswith("/images/"):
        return resolved_project.content_dir / path_or_url.lstrip("/")

    if path_or_url.startswith("/assets/"):
        return resolved_project.static_dir / path_or_url.lstrip("/")

    return None


def is_external_url(value: str) -> bool:
    return bool(re.match(r"^(?:[a-z][a-z0-9+.-]*:)?//", value)) or value.startswith("data:")


def image_size(path: Path) -> tuple[int, int] | None:
    if Image is None or not path.exists():
        return None

    try:
        with Image.open(path) as image:
            return image.size
    except Exception:
        return None


def parse_position(value: str) -> tuple[float, float]:
    tokens = str(value or "50% 50%").replace(",", " ").split()

    def parse_token(token: str) -> float:
        named = {"left": 0.0, "top": 0.0, "center": 0.5, "right": 1.0, "bottom": 1.0}

        if token in named:
            return named[token]

        if token.endswith("%"):
            return min(1.0, max(0.0, float(token[:-1]) / 100))

        return min(1.0, max(0.0, float(token)))

    if len(tokens) == 1:
        tokens = [tokens[0], "50%"]

    try:
        return parse_token(tokens[0]), parse_token(tokens[1])
    except Exception:
        return 0.5, 0.5


def format_position(position: tuple[float, float]) -> str:
    return " ".join(f"{round(value * 100, 3):g}%" for value in position)


def sample_size(size: tuple[int, int], max_edge: int = AUTO_CROP_SAMPLE_EDGE) -> tuple[int, int]:
    width, height = size
    scale = min(1.0, max_edge / max(width, height, 1))
    return max(1, round(width * scale)), max(1, round(height * scale))


def saliency_image(image: Any) -> Any:
    if Image is None or ImageOps is None:
        return None

    gray = ImageOps.grayscale(image)
    sampled = gray.resize(sample_size(gray.size), Image.Resampling.BILINEAR)
    return sampled.filter(ImageFilter.FIND_EDGES) if ImageFilter is not None else sampled


def weighted_centroid(image: Any) -> tuple[float, float] | None:
    width, height = image.size
    pixels = tuple(float(value) for value in image.tobytes())
    total = sum(pixels)

    if not pixels or total / len(pixels) < AUTO_CROP_MIN_MEAN_SIGNAL:
        return None

    x_sum = sum((index % width) * value for index, value in enumerate(pixels))
    y_sum = sum((index // width) * value for index, value in enumerate(pixels))
    return (
        x_sum / total / max(width - 1, 1),
        y_sum / total / max(height - 1, 1),
    )


def crop_axes(source_size: tuple[int, int], target_size: tuple[int, int] | None) -> tuple[bool, bool]:
    if target_size is None:
        return True, True

    source_aspect = source_size[0] / max(source_size[1], 1)
    target_aspect = target_size[0] / max(target_size[1], 1)

    if abs(source_aspect - target_aspect) < 0.001:
        return False, False

    return source_aspect > target_aspect, source_aspect < target_aspect


def smart_crop_position(
    image: Any,
    target_size: tuple[int, int] | None = None,
    fallback: tuple[float, float] = (0.5, 0.5),
) -> tuple[float, float]:
    saliency = saliency_image(image)
    centroid = weighted_centroid(saliency) if saliency is not None else None

    if centroid is None:
        return fallback

    crop_x, crop_y = crop_axes(image.size, target_size)
    return (
        centroid[0] if crop_x else fallback[0],
        centroid[1] if crop_y else fallback[1],
    )


def should_auto_crop(image_data: Mapping[str, Any]) -> bool:
    return str(image_data.get("crop") or "").lower() == "auto" and str(image_data.get("fit") or "cover").lower() == "cover"


def effective_position(source: Path, image_data: Mapping[str, Any]) -> str:
    fallback = parse_position(str(image_data.get("position") or "50% 50%"))

    if not should_auto_crop(image_data) or Image is None:
        return format_position(fallback)

    with Image.open(source) as original:
        target_size = (
            int(image_data.get("width") or original.width),
            int(image_data.get("height") or original.height),
        )
        return format_position(smart_crop_position(original, target_size, fallback))


def resized_image(source: Path, size: tuple[int, int], fit: str, position: str) -> Any:
    if Image is None or ImageOps is None:
        raise RuntimeError("Pillow is required for image crop/resize support")

    with Image.open(source) as original:
        image = original.copy()

    resampling = Image.Resampling.LANCZOS
    fit_mode = str(fit or "cover").lower()

    if fit_mode in {"stretch", "resize"}:
        return image.resize(size, resampling)

    if fit_mode == "contain":
        contained = ImageOps.contain(image, size, method=resampling)
        canvas = Image.new("RGBA", size, (0, 0, 0, 0))
        left = round((size[0] - contained.width) / 2)
        top = round((size[1] - contained.height) / 2)
        canvas.paste(contained, (left, top))
        return canvas

    return ImageOps.fit(
        image,
        size,
        method=resampling,
        centering=parse_position(position),
    )


def save_image(image: Any, destination: Path, quality: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    suffix = destination.suffix.lower()

    if suffix in {".jpg", ".jpeg"}:
        image.convert("RGB").save(destination, quality=quality, optimize=True)
    else:
        image.save(destination, optimize=True)


def generated_image_path(
    key: str,
    variant: str | None,
    width: int,
    height: int,
    suffix: str,
    project: ProjectPaths,
) -> Path:
    resolved_project = project
    variant_part = variant or "base"
    filename = f"{slugify(key)}-{slugify(variant_part)}-{width}x{height}{suffix.lower()}"
    return resolved_project.output_dir / "images" / "generated" / filename


def ensure_generated_image(
    source: Path,
    key: str,
    variant: str | None,
    image_data: Mapping[str, Any],
    project: ProjectPaths,
) -> tuple[str, int, int, str]:
    natural = image_size(source) or (1200, 630)
    width = int(image_data.get("width") or natural[0])
    height = int(image_data.get("height") or natural[1])
    position = effective_position(source, image_data)
    destination = generated_image_path(key, variant, width, height, source.suffix, project)

    if not destination.exists() or destination.stat().st_mtime_ns < source.stat().st_mtime_ns:
        try:
            result = resized_image(
                source,
                (width, height),
                str(image_data.get("fit") or "cover"),
                position,
            )
            save_image(result, destination, int(image_data.get("quality") or 85))
        except Exception as exc:
            raise AssetError(f"failed to generate image {key!r} from {source}: {exc}") from exc

    return f"/images/generated/{destination.name}", width, height, position


def image_result(
    key: str,
    url: str,
    image_data: Mapping[str, Any],
    width: int,
    height: int,
    position: str | None = None,
) -> dict[str, Any]:
    return {
        "exists": True,
        "key": key,
        "url": url,
        "alt": str(image_data.get("alt") or ""),
        "class": str(image_data.get("class") or ""),
        "width": width,
        "height": height,
        "fit": str(image_data.get("fit") or "cover"),
        "position": position or str(image_data.get("position") or "50% 50%"),
        "ratio": f"{width}; --h: {height}",
        "label": str(image_data.get("label") or key.replace("_", " ")),
        "size": str(image_data.get("size") or f"{width}x{height}"),
        "fallback": copy_value(image_data.get("fallback") or {}),
    }


def post_field(post: Any, key: str) -> Any:
    if isinstance(post, Mapping):
        return post.get(key)

    return getattr(post, key, None)


def image_key_for(name_or_path: Any, post: Any = None) -> str:
    image_key = str(name_or_path or "")

    if post is not None:
        possible_key = post_field(post, image_key)

        if possible_key:
            return str(possible_key)

    return image_key


def normalize_image_data(item: Mapping[str, Any], variant: str | None) -> dict[str, Any]:
    base = {key: value for key, value in item.items() if key != "variants"}
    variant_data = (item.get("variants") or {}).get(variant or "", {}) if isinstance(item.get("variants"), Mapping) else {}

    return deep_merge(DEFAULT_IMAGE, deep_merge(base, variant_data if isinstance(variant_data, Mapping) else {}))


def direct_image(name_or_path: str, project: ProjectPaths) -> dict[str, Any]:
    source = direct_image_source(name_or_path, project)

    if is_external_url(name_or_path):
        return image_result(
            name_or_path,
            name_or_path,
            DEFAULT_IMAGE,
            int(DEFAULT_IMAGE.get("width") or 1200),
            int(DEFAULT_IMAGE.get("height") or 630),
        )

    if source is None:
        raise AssetError(f"image path must be a configured logical image or /images/ or /assets/ path: {name_or_path!r}")

    if not source.exists():
        raise AssetError(f"missing image asset: {name_or_path} -> {source}")

    natural = image_size(source) or (1200, 630)
    return image_result(name_or_path, name_or_path, DEFAULT_IMAGE, natural[0], natural[1])


def make_image_resolver(images: Mapping[str, Any], project: ProjectPaths):
    resolved_project = project

    def resolve_image(name_or_path: Any = None, variant: str | None = None, post: Any = None) -> dict[str, Any]:
        if not name_or_path:
            raise AssetError("image() requires a logical image key or direct image path")

        image_key = image_key_for(name_or_path, post)

        if image_key.startswith("/") or is_external_url(image_key):
            return direct_image(image_key, resolved_project)

        item = images.get(image_key)

        if not isinstance(item, Mapping):
            raise AssetError(f"configured image not found: {image_key}")

        image_data = normalize_image_data(item, variant)
        filename = str(image_data.get("file") or "")
        source = resolved_project.content_images_dir / filename if filename else Path()

        if not filename:
            raise AssetError(f"configured image {image_key!r} must include a file")

        if not source.exists():
            raise AssetError(f"missing configured image asset: {image_key} -> {source}")

        url, width, height, position = ensure_generated_image(source, image_key, variant, image_data, resolved_project)
        return image_result(image_key, url, image_data, width, height, position)

    return resolve_image
