"""Deploy step orchestration.

Normalized deploy config, selected post state, Mastodon posting, final rebuilds,
and transport uploads flow through immutable ``DeployState`` transitions.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from colophon.build import build_contexts, build_site
from colophon.content import load_post_sidebar, load_site_config, scan_content_tree
from colophon.deploy.config import load_deploy_config, redact_secrets
from colophon.deploy.mastodon import load_deploy_mastodon, mastodon_status_url, post_mastodon_status, render_mastodon_post_text, select_deploy_post, source_mastodon_status_url, write_source_mastodon_status_url
from colophon.deploy.transports import TRANSPORT_UPLOADERS, upload_site_directory
from colophon.errors import DeployConfigError, DeployError
from colophon.models import DeployState, MastodonPoster, PageContext, ProjectPaths, SiteConfig, TransportUploader


def load_deploy_contexts(project: ProjectPaths) -> tuple[SiteConfig, list[PageContext]]:
    resolved_project = project
    site_config = load_site_config(resolved_project)
    content_index = scan_content_tree(resolved_project.content_dir)
    post_sidebar = load_post_sidebar(resolved_project)
    return site_config, build_contexts(site_config, content_index, post_sidebar, resolved_project)


def ensure_deploy_selection(state: DeployState) -> DeployState:
    if state.selection is not None and state.site_config is not None:
        return state

    site_config, contexts = load_deploy_contexts(state.project)
    selection = select_deploy_post(
        contexts,
        post_id=state.post_id,
        strategy=str(state.config.get("post", {}).get("select") or "latest_published"),
    )
    return replace(
        state,
        site_config=site_config,
        contexts=tuple(contexts),
        selection=selection,
    )


def deploy_step_preflight_build(state: DeployState) -> DeployState:
    print("deploy: preflight build")
    build_site(state.project)
    return ensure_deploy_selection(replace(state, selection=None, site_config=None, contexts=()))


def deploy_step_mastodon_post(state: DeployState) -> DeployState:
    state = ensure_deploy_selection(state)
    selection = state.selection

    if selection is None or state.site_config is None:
        raise DeployConfigError("deploy post selection failed")

    existing_status_url = source_mastodon_status_url(selection.source_file)

    if existing_status_url and not state.force_post:
        print(f"deploy: using existing Mastodon status for {selection.summary['slug']}")
        return replace(state, status_url=existing_status_url, posted=False)

    site = state.site_config.data["site"]
    mastodon = load_deploy_mastodon(state.config["mastodon"], site)
    status_text = render_mastodon_post_text(mastodon, selection, site)
    payload = state.mastodon_poster(mastodon, status_text, state.dry_run)
    status_url = mastodon_status_url(payload)

    if not status_url:
        raise DeployError("Mastodon response did not include a status URL")

    print(f"deploy: {'would post' if state.dry_run else 'posted'} Mastodon status for {selection.summary['slug']}")
    return replace(
        state,
        status_text=status_text,
        status_url=status_url,
        posted=not state.dry_run,
    )


def deploy_step_enable_comments(state: DeployState) -> DeployState:
    state = ensure_deploy_selection(state)
    selection = state.selection

    if selection is None or not state.status_url:
        return state

    existing_status_url = source_mastodon_status_url(selection.source_file)

    if existing_status_url == state.status_url:
        return state

    if state.dry_run:
        print(f"deploy: would enable comments for {selection.summary['slug']}")
        return state

    write_source_mastodon_status_url(selection.source_file, state.status_url)
    print(f"deploy: enabled comments for {selection.summary['slug']}")
    return state


def deploy_step_build(state: DeployState) -> DeployState:
    print("deploy: final build")
    build_site(state.project)
    site_config, contexts = load_deploy_contexts(state.project)
    selection = select_deploy_post(
        contexts,
        post_id=state.post_id,
        strategy=str(state.config.get("post", {}).get("select") or "latest_published"),
    )
    return replace(
        state,
        site_config=site_config,
        contexts=tuple(contexts),
        selection=selection,
    )


def deploy_step_upload(state: DeployState) -> DeployState:
    actions = upload_site_directory(
        state.target_config,
        state.project,
        source_dir=state.project.output_dir,
        dry_run=state.dry_run,
        uploaders=state.transport_uploaders,
    )

    for action in actions:
        print(f"deploy: {'would ' if state.dry_run else ''}{action}")

    return replace(state, uploaded=not state.dry_run, upload_actions=tuple(actions))


DEPLOY_STEP_HANDLERS: dict[str, Callable[[DeployState], DeployState]] = {
    "preflight_build": deploy_step_preflight_build,
    "mastodon_post": deploy_step_mastodon_post,
    "enable_comments": deploy_step_enable_comments,
    "build": deploy_step_build,
    "upload": deploy_step_upload,
}


def run_deploy_steps(state: DeployState) -> DeployState:
    current = state

    for step in state.config["steps"]:
        current = DEPLOY_STEP_HANDLERS[step](current)

    return current


def deploy_site(
    project: ProjectPaths,
    config_path: Path | None = None,
    target: str | None = None,
    post_id: str | None = None,
    dry_run: bool = False,
    force_post: bool = False,
    mastodon_poster: MastodonPoster = post_mastodon_status,
    transport_uploaders: Mapping[str, TransportUploader] | None = None,
) -> dict[str, Any]:
    resolved_project = project
    config = load_deploy_config(resolved_project, config_path)
    target_name = target or str(config.get("default_target"))
    target_config = config["targets"].get(target_name)

    if not target_config:
        raise DeployConfigError(f"unknown deploy target {target_name!r}")

    print(f"deploy: target {target_name} {redact_secrets(target_config)}")
    state = DeployState(
        project=resolved_project,
        config=config,
        target_name=target_name,
        target_config=target_config,
        post_id=post_id,
        dry_run=dry_run,
        force_post=force_post,
        mastodon_poster=mastodon_poster,
        transport_uploaders=TRANSPORT_UPLOADERS if transport_uploaders is None else transport_uploaders,
    )
    finished = run_deploy_steps(state)
    post_slug = finished.selection.summary["slug"] if finished.selection else ""

    return {
        "target": finished.target_name,
        "post_slug": post_slug,
        "status_url": finished.status_url,
        "posted": finished.posted,
        "uploaded": finished.uploaded,
        "dry_run": finished.dry_run,
        "upload_actions": list(finished.upload_actions),
    }
