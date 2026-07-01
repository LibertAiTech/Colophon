"""Mastodon-specific deploy behavior.

Built page contexts flow into post selection and status text rendering; successful
or dry-run status URLs flow back into source metadata for comments.
"""

from __future__ import annotations

import datetime as dt
import json
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any

import frontmatter
import yaml
from jinja2 import TemplateError

from colophon.collections import is_post_context, should_list_page, summarize_page
from colophon.deploy.config import DEFAULT_DEPLOY_MASTODON
from colophon.errors import DeployConfigError, DeployError
from colophon.expressions import make_expression_environment
from colophon.mastodon import mastodon_instance_url
from colophon.models import DeployPostSelection, PageContext, SourceFile
from colophon.utils import deep_merge, mapping, public_url, read_yaml


def deploy_post_date(value: Any) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()

    if isinstance(value, dt.date):
        return value

    return dt.date.min


def is_deployable_post_context(context: PageContext) -> bool:
    return (
        is_post_context(context)
        and should_list_page(context)
        and str(context.data.get("status") or "").lower() == "published"
    )


def deploy_post_sort_key(context: PageContext) -> tuple[dt.date, str]:
    return deploy_post_date(context.data.get("date")), context.route.url_path


def deploy_source_file(context: PageContext) -> SourceFile:
    if not context.source_chain:
        raise DeployConfigError(f"post {context.route.url_path} has no source file")

    return context.source_chain[-1]


def select_deploy_post(
    contexts: list[PageContext] | tuple[PageContext, ...],
    *,
    post_id: str | None = None,
    strategy: str = "latest_published",
) -> DeployPostSelection:
    candidates = [context for context in contexts if is_deployable_post_context(context)]

    if post_id:
        selected = next(
            (
                context
                for context in candidates
                if str(context.data.get("slug") or "") == post_id
                or context.route.url_path.strip("/").split("/")[-1] == post_id
            ),
            None,
        )

        if selected is None:
            raise DeployConfigError(f"no published post found for post id {post_id!r}")

        return DeployPostSelection(
            context=selected,
            summary=summarize_page(selected),
            source_file=deploy_source_file(selected),
        )

    if strategy != "latest_published":
        raise DeployConfigError(f"unknown deploy post selector {strategy!r}")

    if not candidates:
        raise DeployConfigError("no published posts available to deploy")

    selected = max(candidates, key=deploy_post_sort_key)
    return DeployPostSelection(
        context=selected,
        summary=summarize_page(selected),
        source_file=deploy_source_file(selected),
    )


def deploy_post_template_data(selection: DeployPostSelection, site: Mapping[str, Any]) -> dict[str, Any]:
    summary = selection.summary
    return deep_merge(
        summary,
        {
            "url": public_url(site, str(summary.get("url") or summary.get("route") or "")),
            "route": str(summary.get("route") or ""),
        },
    )


def render_deploy_template(template: str, context: Mapping[str, Any], path: str) -> str:
    try:
        return make_expression_environment().from_string(template).render(**context)
    except TemplateError as exc:
        raise DeployConfigError(f"{path}: failed to render deploy template: {exc}") from exc


def render_mastodon_post_text(
    mastodon: Mapping[str, Any],
    selection: DeployPostSelection,
    site: Mapping[str, Any],
) -> str:
    template = str(mastodon.get("post_text") or DEFAULT_DEPLOY_MASTODON["post_text"])
    text = render_deploy_template(
        template,
        {"post": deploy_post_template_data(selection, site), "site": site},
        "deploy.mastodon.post_text",
    ).strip()

    if not text:
        raise DeployConfigError("deploy.mastodon.post_text rendered an empty status")

    return text


def load_deploy_mastodon(
    mastodon: Mapping[str, Any],
    site: Mapping[str, Any],
) -> dict[str, Any]:
    site_mastodon = site.get("mastodon") or {}
    instance_url = mastodon_instance_url(
        mastodon.get("instance_url")
        or mastodon.get("host")
        or site_mastodon.get("instance_url")
        or site_mastodon.get("host")
    )
    normalized = deep_merge(mastodon, {"instance_url": instance_url})

    if not normalized.get("access_token"):
        raise DeployConfigError("deploy.mastodon.access_token is required")

    if not instance_url:
        raise DeployConfigError("deploy.mastodon.instance_url or site.mastodon.host is required")

    return normalized


def mastodon_status_url(payload: Mapping[str, Any]) -> str:
    return str(payload.get("url") or payload.get("uri") or "").strip()


def post_mastodon_status(
    mastodon: Mapping[str, Any],
    status_text: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    if dry_run:
        return {"id": "dry-run", "url": "https://dry-run.invalid/@deploy/0"}

    token = str(mastodon.get("access_token") or "")
    instance_url = mastodon_instance_url(mastodon.get("instance_url"))
    body = urlencode({"status": status_text}).encode("utf-8")
    request = urllib.request.Request(
        f"{instance_url}/api/v1/statuses",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "colophon-deploy/0.1",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise DeployError(f"Mastodon post failed with HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise DeployError(f"Mastodon post failed: {exc}") from exc


def load_source_metadata(source_file: SourceFile) -> dict[str, Any]:
    if source_file.kind == "markdown":
        post = frontmatter.loads(source_file.absolute_path.read_text(encoding="utf-8"))
        return dict(post.metadata)

    if source_file.kind == "yaml":
        return read_yaml(source_file.absolute_path)

    return {}


def mastodon_comments_status_url(raw_comments: Any) -> str:
    if raw_comments is None:
        return ""

    if isinstance(raw_comments, bool):
        return ""

    comments = mapping(raw_comments, "mastodon_comments", error=DeployConfigError)
    return str(comments.get("status_url") or "").strip()


def source_mastodon_status_url(source_file: SourceFile) -> str:
    return mastodon_comments_status_url(load_source_metadata(source_file).get("mastodon_comments"))


def comments_with_status_url(raw_comments: Any, status_url: str) -> dict[str, Any]:
    comments = (
        {"enabled": raw_comments}
        if isinstance(raw_comments, bool)
        else mapping(raw_comments, "mastodon_comments", error=DeployConfigError)
    )
    defaults = {} if "enabled" in comments else {"enabled": True}
    return deep_merge(deep_merge(defaults, comments), {"status_url": status_url})


def write_source_mastodon_status_url(source_file: SourceFile, status_url: str) -> None:
    if source_file.kind == "markdown":
        post = frontmatter.loads(source_file.absolute_path.read_text(encoding="utf-8"))
        post.metadata = deep_merge(
            dict(post.metadata),
            {
                "mastodon_comments": comments_with_status_url(
                    post.metadata.get("mastodon_comments"),
                    status_url,
                )
            },
        )
        source_file.absolute_path.write_text(frontmatter.dumps(post), encoding="utf-8")
        return

    if source_file.kind == "yaml":
        data = read_yaml(source_file.absolute_path)
        updated = deep_merge(
            data,
            {
                "mastodon_comments": comments_with_status_url(
                    data.get("mastodon_comments"),
                    status_url,
                )
            },
        )
        source_file.absolute_path.write_text(
            yaml.safe_dump(updated, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        return

    raise DeployConfigError(f"cannot update Mastodon comments in {source_file.content_path}")
