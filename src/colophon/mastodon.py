"""Strict Mastodon site, timeline, and comment config loaders."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

from .errors import ContentError
from .utils import copy_value, deep_merge, mapping, trim_url


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
    raw = mapping(
        timeline_config if timeline_config is not None else mastodon.get("timeline"),
        "site.mastodon.timeline",
        error=ContentError,
    )
    reject_unknown(raw, MASTODON_TIMELINE_KEYS, "site.mastodon.timeline")
    timeline = deep_merge(DEFAULT_MASTODON_TIMELINE, raw)

    return {
        "enabled": raw.get("enabled", bool(mastodon.get("enabled"))),
        "container_id": timeline["container_id"],
        "options": timeline_browser_options(mastodon, timeline),
    }


def load_mastodon_site_config(raw_config: Any) -> dict[str, Any]:
    raw = mapping(raw_config, "site.mastodon", error=ContentError)
    reject_unknown(raw, MASTODON_SITE_KEYS, "site.mastodon")
    config = deep_merge(
        DEFAULT_MASTODON,
        {key: copy_value(value) for key, value in raw.items() if key != "timeline"},
    )
    host = mastodon_host(config.get("host") or config.get("instance_url"))
    instance_url = mastodon_instance_url(config.get("instance_url") or host)
    mastodon = deep_merge(
        config,
        {
            "host": host,
            "instance_url": instance_url,
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
            "user": mastodon.get("user") or "",
        },
    )


def load_mastodon_comments(
    raw_config: Any,
    site_mastodon: Mapping[str, Any],
) -> dict[str, Any]:
    raw = (
        {"enabled": raw_config}
        if isinstance(raw_config, bool)
        else mapping(raw_config, "mastodon_comments", error=ContentError)
    )
    reject_unknown(raw, MASTODON_COMMENT_KEYS, "mastodon_comments")
    defaults = load_mastodon_comment_defaults(site_mastodon)
    status_url = raw.get("status_url") or ""
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
            "user": merged.get("user") or "",
            "toot_id": merged.get("toot_id") or "",
            "filter": merged.get("filter") or "",
            "lang": merged.get("lang") or "",
        },
    )
    has_thread = all(merged.get(key) for key in ("host", "user", "toot_id"))

    return deep_merge(
        merged,
        {"enabled": has_thread and raw.get("enabled", bool(raw))},
    )
