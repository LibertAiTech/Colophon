"""Strict Mastodon site, timeline, and comment config loaders."""

from __future__ import annotations

from collections.abc import Mapping
from functools import partial
from typing import Any
from urllib.parse import urlparse

from .errors import ContentError
from .utils import copy_value, deep_merge, expect, expect_fields, field, trim_url


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
content_value = partial(expect, error=ContentError)
content_fields = partial(expect_fields, error=ContentError)


MASTODON_SITE_FIELDS = {
    "enabled": field("boolean", False),
    "host": field("string", DEFAULT_MASTODON["host"]),
    "instance_url": field("string", DEFAULT_MASTODON["instance_url"]),
    "user": field("string", DEFAULT_MASTODON["user"]),
    "user_id": field("string", DEFAULT_MASTODON["user_id"]),
    "profile_name": field("string", DEFAULT_MASTODON["profile_name"]),
}


MASTODON_TIMELINE_FIELDS = {
    "container_id": field("string", DEFAULT_MASTODON_TIMELINE["container_id"]),
    "timeline_type": field("string", DEFAULT_MASTODON_TIMELINE["timeline_type"]),
    "default_theme": field("string", DEFAULT_MASTODON_TIMELINE["default_theme"]),
    "max_posts_fetch": field("integer", DEFAULT_MASTODON_TIMELINE["max_posts_fetch"]),
    "max_posts_show": field("integer", DEFAULT_MASTODON_TIMELINE["max_posts_show"]),
    "hide_reblogs": field("boolean", DEFAULT_MASTODON_TIMELINE["hide_reblogs"]),
    "hide_replies": field("boolean", DEFAULT_MASTODON_TIMELINE["hide_replies"]),
}


MASTODON_COMMENT_TEXT_FIELDS = {
    "host": field("string", ""),
    "user": field("string", ""),
    "toot_id": field("string", ""),
    "filter": field("string", ""),
    "lang": field("string", ""),
}


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
    raw = content_value(
        timeline_config if timeline_config is not None else mastodon.get("timeline"),
        "site.mastodon.timeline",
        "mapping",
        default={},
    )
    reject_unknown(raw, MASTODON_TIMELINE_KEYS, "site.mastodon.timeline")
    fields = content_fields(
        raw,
        "site.mastodon.timeline",
        {
            "enabled": field("boolean", bool(mastodon.get("enabled"))),
            **MASTODON_TIMELINE_FIELDS,
        },
    )
    timeline = deep_merge(
        DEFAULT_MASTODON_TIMELINE,
        fields,
    )

    return {
        "enabled": timeline["enabled"],
        "container_id": timeline["container_id"],
        "options": timeline_browser_options(mastodon, timeline),
    }


def load_mastodon_site_config(raw_config: Any) -> dict[str, Any]:
    raw = content_value(raw_config, "site.mastodon", "mapping", default={})
    reject_unknown(raw, MASTODON_SITE_KEYS, "site.mastodon")
    fields = content_fields(raw, "site.mastodon", MASTODON_SITE_FIELDS)
    config = deep_merge(
        DEFAULT_MASTODON,
        {key: copy_value(value) for key, value in raw.items() if key != "timeline"},
    )
    host = mastodon_host(fields["host"] or fields["instance_url"])
    instance_url = mastodon_instance_url(fields["instance_url"] or host)
    mastodon = deep_merge(
        config,
        {
            **fields,
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
            "user": content_value(
                mastodon.get("user"),
                "site.mastodon.user",
                "string",
                default="",
            ),
        },
    )


def load_mastodon_comments(
    raw_config: Any,
    site_mastodon: Mapping[str, Any],
) -> dict[str, Any]:
    raw = content_value(raw_config, "mastodon_comments", "mapping", default={})
    reject_unknown(raw, MASTODON_COMMENT_KEYS, "mastodon_comments")
    defaults = load_mastodon_comment_defaults(site_mastodon)
    fields = content_fields(
        raw,
        "mastodon_comments",
        {
            "enabled": field("boolean", bool(raw)),
            "status_url": field("string", ""),
            **MASTODON_COMMENT_TEXT_FIELDS,
        },
    )
    status_url = fields["status_url"]
    from_status_url = parse_mastodon_status_url(status_url)
    explicit = {
        key: fields[key]
        for key in raw
        if key not in {"enabled", "status_url"}
    }
    merged = deep_merge(deep_merge(defaults, from_status_url), explicit)
    text_fields = content_fields(
        merged,
        "mastodon_comments",
        MASTODON_COMMENT_TEXT_FIELDS,
    )
    merged = deep_merge(
        merged,
        {
            **text_fields,
            "host": mastodon_host(text_fields["host"]),
        },
    )
    has_thread = all(merged.get(key) for key in ("host", "user", "toot_id"))

    return deep_merge(
        merged,
        {"enabled": has_thread and fields["enabled"]},
    )
