# Publishing Guide

[README](../README.md) | [CLI](cli.md) | [Authorship](authorship.md) | [Site design](site-design.md) | [Python API](python-api.md) | [Reference](reference.md)

This guide covers post-build publication: deploy config, provider recipes, Mastodon, feeds, archive/tag output, and repeatable build time.

## Archives, Tags, and Feeds

Every build creates:

- `/archive/` from `templates/archive.html`
- `/tags/<tag>/` from `templates/tag.html`
- `/feed.xml` from `templates/feed.xml`

These pages use listed post summaries sorted by date descending. Tag routes are slugified from post tags.

For repeatable feeds and build metadata, pass `--build-time`, `BuildOptions(build_time=...)`, or set `SOURCE_DATE_EPOCH`.

```bash
colophon build --config colophon.yml --build-time 2026-01-02T03:04:05Z
SOURCE_DATE_EPOCH=1767225600 colophon build --config colophon.yml
```

## Mastodon

Mastodon support has two parts:

- build-time config normalization and asset activation
- browser-time timeline/comment fetching by vendor widgets

Colophon does not fetch timelines during a normal build.

Site-level timeline config:

```yaml
site:
  mastodon:
    enabled: true
    host: social.example
    user: alice
    user_id: "123"
    profile_name: "@alice"
    timeline:
      enabled: true
      max_posts_show: 3
```

Post comments can use a status URL:

```yaml
mastodon_comments:
  status_url: https://social.example/@alice/123456
```

Or mark a post as comment-ready before deploy:

```yaml
mastodon_comments: true
```

Templates can check normalized `mastodon_comments.enabled` and `uses_mastodon_timeline`. When those features render, Colophon activates the needed browser assets: DOMPurify, Font Awesome, Mastodon comments, and Mastodon embed timeline.

## Mastodon Posting

Deploy posting needs an access token stored outside source control:

```yaml
deploy:
  mastodon:
    access_token: env::MASTODON_ACCESS_TOKEN
    post_text: "{{ post.title }} {{ post.url }}"
```

Create a Mastodon application from your account preferences, grant the token `write:statuses` for posting, and export it before deploy. Mastodon documents token creation in its [token guide](https://docs.joinmastodon.org/client/token/) and status posting in the [statuses API](https://docs.joinmastodon.org/methods/statuses/).

Dry-run deploy renders the status text and returns a synthetic `https://dry-run.invalid/...` URL without posting or writing comment metadata. A real `mastodon_post` followed by `enable_comments` writes the returned status URL back to the selected post.

## Deploy Config

Deploy config lives at `paths.deploy`, defaulting to `content/deploy.yaml`.

```yaml
deploy:
  default_target: production
  steps:
    - preflight_build
    - mastodon_post
    - enable_comments
    - build
    - upload
  post:
    select: latest_published
  mastodon:
    access_token: env::MASTODON_ACCESS_TOKEN
    post_text: "{{ post.title }} {{ post.url }}"
  targets:
    production:
      transport: ftps
      host: example.test
      port: 21
      username: deploy
      password: env::EXAMPLE_FTP_PASSWORD
      remote_path: public_html/example.test/
      purge: true
```

Run without upload or deletion:

```bash
EXAMPLE_FTP_PASSWORD=dummy colophon deploy --config colophon.yml --target production --dry-run
```

Supported steps are `preflight_build`, `mastodon_post`, `enable_comments`, `build`, and `upload`.

Supported transports:

- `ftp`
- `ftps`
- `sftp`
- `sshfs`

Default ports:

- `ftp`: 21
- `ftps`: 21
- `sftp`: 22
- `sshfs`: 22

SFTP requires `colophon-site[sftp]`. SSHFS requires the system `sshfs` command.

Remote purge is guarded: Colophon refuses obviously unsafe paths such as `/`, `~`, and shallow home directories.

## Hetzner Web Hosting over FTPS/SFTP

Use the host, username, and password from the hosting control panel. FTPS usually uses port 21; SFTP uses port 22 when your plan provides SSH/SFTP.

```yaml
deploy:
  targets:
    production:
      transport: ftps
      host: your-host.example
      username: your-login
      password: env::HETZNER_WEB_PASSWORD
      remote_path: public_html/example.com/
      purge: true
```

## Hetzner Storage Box over SFTP/SSHFS

Storage Box SSH/SFTP access uses the Storage Box host and SSH port documented by Hetzner. Their Storage Box SSH/SFTP guide is at [docs.hetzner.com](https://docs.hetzner.com/storage/storage-box/access/access-ssh-rsync-borg/).

```yaml
deploy:
  targets:
    storage_box:
      transport: sftp
      host: u123456.your-storagebox.de
      port: 23
      username: u123456
      password: env::HETZNER_STORAGEBOX_PASSWORD
      remote_path: sites/example.com/
      purge: true
```

For SSHFS, switch `transport: sshfs` and keep the same host, port, username, and remote path.

## Generic Shared Hosting

Most shared hosts work with FTPS:

```yaml
deploy:
  targets:
    shared:
      transport: ftps
      host: ftp.example.com
      username: account-name
      password: env::SHARED_HOST_PASSWORD
      remote_path: public_html/
      purge: true
```

Related: [CLI](cli.md), [Site design](site-design.md), [Reference](reference.md).
