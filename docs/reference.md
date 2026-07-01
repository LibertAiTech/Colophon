# Reference

[README](../README.md) | [CLI](cli.md) | [Authorship](authorship.md) | [Site design](site-design.md) | [Publishing](publishing.md) | [Python API](python-api.md) | [Template reference](template-reference.md)

This is the compact reference for compatibility, config keys, troubleshooting, and release/support expectations. Use the topic guides for workflow details.

## Compatibility Policy

Until `0.3.0`, config keys and template variables may change.

From `0.3.0` onward, content schema and template globals will be migration-guided.

From `1.0.0` onward, breaking changes require a major version bump.

Patch releases preserve documented behavior except for bug fixes. Minor releases may add compatible features. Clearly broken, unsafe, or previously undocumented behavior may be fixed directly.

Stable surface:

- CLI commands and documented flags
- public Python facade exported from `colophon` / `colophon.core`
- documented config keys
- documented template globals and filters marked stable

Internal convenience surface:

- subsystem modules
- helper functions not exported from `colophon.core`
- undocumented template values

## Package and Import Names

- PyPI distribution: `colophon-site`
- Primary CLI: `colophon`
- CLI alias: `colophon-site`
- Python import package: `colophon`

## Project Config Keys

`colophon.yml`:

| Key | Type | Meaning |
| --- | --- | --- |
| `paths.content` | string | Content directory, default `content`. |
| `paths.templates` | string | Template directory, default `templates`. |
| `paths.static` | string | Static asset directory, default `static`. |
| `paths.output` | string | Output directory, default `_site`. |
| `paths.deploy` | string | Deploy config path, default `content/deploy.yaml`. |
| `python.modules` | list | Trusted Python hook modules. |
| `vendor.mode` | string | `auto`, `cdn`, or `local`. |
| `vendor.local_dir` | string | Vendor directory under `static/`, default `vendor`. |
| `vendor.required` | list | Vendor assets required regardless of page use. |
| `vendor.assets` | mapping | Per-asset vendor overrides. |

Paths are resolved relative to the config file unless absolute.

Strict validation rejects aliases and shorthand forms such as `paths.project`, `paths.deploy_config`, `vendor.require`, scalar lists, boolean strings, and asset boolean shorthand.

## Site Config Keys

`content/site.yaml`:

| Key | Type | Meaning |
| --- | --- | --- |
| `site.title` | string | Site title. |
| `site.subtitle` | string | Optional subtitle. |
| `site.description` | string | Site description. |
| `site.url` | string | Absolute public base URL. |
| `site.author` | string | Site author. |
| `site.signal_line` | string/mapping | Header/status data; mappings render as joined labels. |
| `site.nav` | list | Navigation entries. |
| `site.footer` | mapping | Footer data for templates. |
| `site.mastodon` | mapping | Mastodon timeline defaults. |
| `templates` | mapping | Template aliases. |
| `routes` | list | Route match rules. |

## Content Keys

Stable page/post keys:

- `title`
- `slug`
- `url`
- `summary`
- `date`
- `tags`
- `toc`
- `reading_minutes`
- `draft`
- `listed`
- `status`
- `cover`
- `cover_image`
- `mastodon_comments`
- `collections`

Reserved keys:

- `references`
- `bindings`
- `slot`
- `render`

## Deploy Config Keys

`content/deploy.yaml`:

| Key | Type | Meaning |
| --- | --- | --- |
| `deploy.default_target` | string | Target name used by default. |
| `deploy.steps` | list | Ordered deploy steps. |
| `deploy.post.select` | string | Post selection strategy, currently `latest_published`. |
| `deploy.mastodon.access_token` | string | Token or `env::...` expression. |
| `deploy.mastodon.post_text` | string | Jinja status template. |
| `deploy.targets.<name>.transport` | string | `ftp`, `ftps`, `sftp`, or `sshfs`. |
| `deploy.targets.<name>.host` | string | Remote host. |
| `deploy.targets.<name>.port` | int | Optional transport port. |
| `deploy.targets.<name>.username` | string | Remote username. |
| `deploy.targets.<name>.password` | string | Remote password or `env::...` expression. |
| `deploy.targets.<name>.remote_path` | string | Remote directory. |
| `deploy.targets.<name>.purge` | bool | Whether to purge before upload. |

Supported deploy steps are `preflight_build`, `mastodon_post`, `enable_comments`, `build`, and `upload`.

## Error Categories

The CLI reports user-facing failures without tracebacks by default. Use `--debug` for tracebacks.

Common categories:

- configuration errors
- content errors
- expression resolution errors
- template errors
- asset errors
- deploy config errors
- deploy runtime errors

Programmatic callers can catch `ColophonError` or specific subclasses such as `ProjectConfigError`, `ContentError`, `ExpressionResolutionError`, `TemplateBuildError`, `AssetError`, `DeployConfigError`, and `DeployError`.

## Troubleshooting

- `missing project config`: pass `--config` or run from a directory containing `colophon.yml`.
- `unknown YAML function`: declare the function in a module listed under `python.modules`.
- `YAML context function requires page context`: move the expression into page/frontmatter data or use a zero-argument hook.
- `duplicate YAML function name`: rename one function or remove one module.
- `missing environment variable`: export the required variable or use dry-run with dummy values for deploy tests.
- Template undefined errors: check content field names and template variable names.
- Missing images fail the build: inspect `content/images.yml`, direct image references, and `content/images/`.
- SFTP import errors: install `colophon-site[sftp]`.
- Deploy upload errors usually come from missing host/user/path/password values or network credentials.

## Release and Support Expectations

Release notes live in [CHANGELOG.md](../CHANGELOG.md). Development guidance lives in [CONTRIBUTING.md](../CONTRIBUTING.md).

Before a release:

1. Confirm `pyproject.toml` and `src/colophon/version.py` agree on the version.
2. Run the full test suite with bytecode writes disabled.
3. Confirm no `.DS_Store` files are tracked.
4. Configure pending Trusted Publishers for TestPyPI and PyPI using the release workflow and GitHub environments.
5. From a clean checkout, build the wheel and sdist, then run `twine check dist/*`.
6. Install both generated artifacts in fresh virtual environments and smoke-test both CLI commands.
7. Tag `v0.1.0`, push the tag, and run the TestPyPI workflow on that ref.
8. Verify the TestPyPI install, then recheck PyPI name availability.
9. Publish the GitHub release; the release event publishes to PyPI through Trusted Publishing.
10. Verify the final PyPI install in a fresh virtual environment.

Related: [CLI](cli.md), [Python API](python-api.md), [Template reference](template-reference.md).
