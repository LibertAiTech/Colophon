"""Strict Mastodon site, timeline, and comment config loaders."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

from .errors import ContentError
from .utils import copy_value, deep_merge, trim_url


DEFAULT_MASTODON_TIMELINE = {
    "enabled": False,
    "container_id": "mastodon-timeline",
    "timeline_type": "profile",
    "default_theme": "dark",
    "max_posts_fetch": 20,
    "max_posts_show": 5,
    "hide_reblogs": True,
    "hide_replies": True,
}


DEFAULT_MASTODON_COMMENTS = {
    "enabled": False,
    "host": "",
    "user": "",
    "toot_id": "",
    "filter": "",
    "lang": "",
}


DEFAULT_MASTODON = {
    "enabled": False,
    "host": "",
    "instance_url": "",
    "user": "",
    "user_id": "",
    "profile_name": "",
    "timeline": DEFAULT_MASTODON_TIMELINE,
}


MASTODON_SITE_KEYS = frozenset(DEFAULT_MASTODON)
MASTODON_TIMELINE_KEYS = frozenset(DEFAULT_MASTODON_TIMELINE)
MASTODON_COMMENT_KEYS = frozenset((*DEFAULT_MASTODON_COMMENTS, "status_url"))


def reject_unknown(raw: Mapping[str, Any], allowed: frozenset[str], path: str) -> None:
    unknown = sorted(str(key) for key in raw if key not in allowed)

    if unknown:
        raise ContentError(f"{path} contains unsupported key(s): {', '.join(unknown)}")


def require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ContentError(f"{path} must be a mapping")

    return dict(value)


def optional_mapping(value: Any, path: str) -> dict[str, Any]:
    return {} if value is None else require_mapping(value, path)


def require_string(value: Any, path: str) -> str:
    if not isinstance(value, str):
        raise ContentError(f"{path} must be a string")

    return value.strip()


def optional_string(value: Any, path: str, default: str = "") -> str:
    return default if value is None else require_string(value, path)


def optional_bool(value: Any, path: str, default: bool = False) -> bool:
    if value is None:
        return default

    if not isinstance(value, bool):
        raise ContentError(f"{path} must be a boolean")

    return value


def optional_int(value: Any, path: str, default: int) -> int:
    if value is None:
        return default

    if not isinstance(value, int) or isinstance(value, bool):
        raise ContentError(f"{path} must be an integer")

    return value


def mastodon_host(value: Any) -> str:
    text = trim_url(value)

    if not text:
        return ""

    parsed = urlparse(text if "://" in text else f"https://{text}")
    return (parsed.netloc or parsed.path).strip("/")


def mastodon_instance_url(value: Any) -> str:
    text = trim_url(value)

    if not text:
        return ""

    parsed = urlparse(text if "://" in text else f"https://{text}")
    host = parsed.netloc or parsed.path
    return f"{parsed.scheme or 'https'}://{host.strip('/')}"


def parse_mastodon_status_url(value: str) -> dict[str, str]:
    text = trim_url(value)

    if not text:
        return {}

    parsed = urlparse(text if "://" in text else f"https://{text}")
    parts = [part for part in parsed.path.split("/") if part]

    if len(parts) >= 2 and parts[0].startswith("@"):
        return {
            "host": mastodon_host(parsed.netloc),
            "user": parts[0].lstrip("@").split("@")[0],
            "toot_id": parts[1],
        }

    if len(parts) >= 4 and parts[0] == "users" and parts[2] == "statuses":
        return {
            "host": mastodon_host(parsed.netloc),
            "user": parts[1],
            "toot_id": parts[3],
        }

    return {}


def timeline_browser_options(mastodon: Mapping[str, Any], timeline: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "mtContainerId": timeline["container_id"],
        "instanceUrl": mastodon["instance_url"],
        "timelineType": timeline["timeline_type"],
        "userId": mastodon["user_id"],
        "profileName": mastodon["profile_name"],
        "defaultTheme": timeline["default_theme"],
        "maxNbPostFetch": timeline["max_posts_fetch"],
        "maxNbPostShow": timeline["max_posts_show"],
        "hideReblog": timeline["hide_reblogs"],
        "hideReplies": timeline["hide_replies"],
    }


def load_mastodon_timeline(
    mastodon: Mapping[str, Any],
    timeline_config: Any = None,
) -> dict[str, Any]:
    raw = optional_mapping(timeline_config if timeline_config is not None else mastodon.get("timeline"), "site.mastodon.timeline")
    reject_unknown(raw, MASTODON_TIMELINE_KEYS, "site.mastodon.timeline")
    timeline = deep_merge(
        DEFAULT_MASTODON_TIMELINE,
        {
            "enabled": optional_bool(raw.get("enabled"), "site.mastodon.timeline.enabled", False),
            "container_id": optional_string(raw.get("container_id"), "site.mastodon.timeline.container_id", DEFAULT_MASTODON_TIMELINE["container_id"]),
            "timeline_type": optional_string(raw.get("timeline_type"), "site.mastodon.timeline.timeline_type", DEFAULT_MASTODON_TIMELINE["timeline_type"]),
            "default_theme": optional_string(raw.get("default_theme"), "site.mastodon.timeline.default_theme", DEFAULT_MASTODON_TIMELINE["default_theme"]),
            "max_posts_fetch": optional_int(raw.get("max_posts_fetch"), "site.mastodon.timeline.max_posts_fetch", DEFAULT_MASTODON_TIMELINE["max_posts_fetch"]),
            "max_posts_show": optional_int(raw.get("max_posts_show"), "site.mastodon.timeline.max_posts_show", DEFAULT_MASTODON_TIMELINE["max_posts_show"]),
            "hide_reblogs": optional_bool(raw.get("hide_reblogs"), "site.mastodon.timeline.hide_reblogs", DEFAULT_MASTODON_TIMELINE["hide_reblogs"]),
            "hide_replies": optional_bool(raw.get("hide_replies"), "site.mastodon.timeline.hide_replies", DEFAULT_MASTODON_TIMELINE["hide_replies"]),
        },
    )
    enabled = optional_bool(raw.get("enabled"), "site.mastodon.timeline.enabled", bool(mastodon.get("enabled")))

    return {
        "enabled": enabled,
        "container_id": timeline["container_id"],
        "options": timeline_browser_options(mastodon, timeline),
    }


def load_mastodon_site_config(raw_config: Any) -> dict[str, Any]:
    raw = optional_mapping(raw_config, "site.mastodon")
    reject_unknown(raw, MASTODON_SITE_KEYS, "site.mastodon")
    config = deep_merge(DEFAULT_MASTODON, {key: copy_value(value) for key, value in raw.items() if key != "timeline"})
    host = mastodon_host(
        optional_string(raw.get("host"), "site.mastodon.host", DEFAULT_MASTODON["host"])
        or optional_string(raw.get("instance_url"), "site.mastodon.instance_url", DEFAULT_MASTODON["instance_url"])
    )
    instance_url = mastodon_instance_url(
        optional_string(raw.get("instance_url"), "site.mastodon.instance_url", "")
        or host
    )
    mastodon = deep_merge(
        config,
        {
            "enabled": optional_bool(raw.get("enabled"), "site.mastodon.enabled", False),
            "host": host,
            "instance_url": instance_url,
            "user": optional_string(raw.get("user"), "site.mastodon.user", DEFAULT_MASTODON["user"]),
            "user_id": optional_string(raw.get("user_id"), "site.mastodon.user_id", DEFAULT_MASTODON["user_id"]),
            "profile_name": optional_string(raw.get("profile_name"), "site.mastodon.profile_name", DEFAULT_MASTODON["profile_name"]),
        },
    )

    return deep_merge(
        mastodon,
        {
            "timeline": load_mastodon_timeline(
                mastodon,
                raw.get("timeline"),
            ),
        },
    )


def load_mastodon_comment_defaults(mastodon: Mapping[str, Any]) -> dict[str, Any]:
    return deep_merge(
        DEFAULT_MASTODON_COMMENTS,
        {
            "host": mastodon_host(mastodon.get("host") or mastodon.get("instance_url")),
            "user": optional_string(mastodon.get("user"), "site.mastodon.user", ""),
        },
    )


def load_mastodon_comments(
    raw_config: Any,
    site_mastodon: Mapping[str, Any],
) -> dict[str, Any]:
    raw = optional_mapping(raw_config, "mastodon_comments")
    reject_unknown(raw, MASTODON_COMMENT_KEYS, "mastodon_comments")
    defaults = load_mastodon_comment_defaults(site_mastodon)
    status_url = optional_string(raw.get("status_url"), "mastodon_comments.status_url", "")
    from_status_url = parse_mastodon_status_url(status_url)
    explicit = {
        key: copy_value(value)
        for key, value in raw.items()
        if key not in {"enabled", "status_url"}
    }
    merged = deep_merge(deep_merge(defaults, from_status_url), explicit)
    merged = deep_merge(
        merged,
        {
            "host": mastodon_host(merged.get("host")),
            "user": optional_string(merged.get("user"), "mastodon_comments.user", ""),
            "toot_id": optional_string(merged.get("toot_id"), "mastodon_comments.toot_id", ""),
            "filter": optional_string(merged.get("filter"), "mastodon_comments.filter", ""),
            "lang": optional_string(merged.get("lang"), "mastodon_comments.lang", ""),
        },
    )
    has_thread = all(merged.get(key) for key in ("host", "user", "toot_id"))
    explicit_enabled = optional_bool(raw.get("enabled"), "mastodon_comments.enabled", bool(raw))

    return deep_merge(
        merged,
        {"enabled": has_thread and explicit_enabled},
    )
