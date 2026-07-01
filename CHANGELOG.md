# Changelog

## v0.1.0

Initial alpha release of Colophon.

### Highlights

- Static site generation from YAML and Markdown content.
- Jinja template rendering with Colophon globals for public URLs, images, and vendor assets.
- Strict project config and content validation.
- Trusted local Python hooks through `YAML_FUNCTIONS`.
- Page-aware Python hooks through `YAML_CONTEXT_FUNCTIONS` and `ExpressionContext`.
- Content image registry with generated derivatives.
- Archive, tag, and RSS feed generation.
- Mastodon timeline/comment metadata support.
- Config-driven deploy over FTP, FTPS, SFTP, and SSHFS.
- Atomic watch rebuilds for local serving.
- Public distribution name changed to `colophon-site` to avoid the unrelated PyPI `colophon` package.

### Install

```bash
python -m pip install colophon-site
python -m pip install 'colophon-site[sftp]'
```

Pinned GitHub install:

```bash
python -m pip install git+https://github.com/AeonCypher/Colophon.git@v0.1.0
python -m pip install 'colophon-site[sftp] @ git+https://github.com/AeonCypher/Colophon.git@v0.1.0'
```

### Compatibility

This is an alpha release. Until `0.3.0`, config keys and template variables may change. From `0.3.0` onward, content schema and template globals will be migration-guided. From `1.0.0` onward, breaking changes require a major version bump.

## Release Checklist

1. Confirm `pyproject.toml` and `src/colophon/version.py` both declare `0.1.0`.
2. Run:

   ```bash
   PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m unittest discover -v
   ```

3. Confirm no platform artifacts are tracked:

   ```bash
   git ls-files | grep -E '(^|/)\.DS_Store$'
   ```

   The command should print nothing.

4. Configure pending Trusted Publishers before the first upload:

   - TestPyPI project: `colophon-site`, owner `AeonCypher`, repository `Colophon`, workflow `publish.yml`, environment `testpypi`.
   - PyPI project: `colophon-site`, owner `AeonCypher`, repository `Colophon`, workflow `publish.yml`, environment `pypi`.

5. From a clean checkout, build and check the release artifacts:

   ```bash
   python -m pip install --upgrade build twine
   python -m build
   python -m twine check dist/*
   ```

6. Install the generated wheel in a fresh virtual environment and smoke-test:

   ```bash
   colophon --help
   colophon-site --help
   colophon scaffold ./smoke-site
   colophon build --config ./smoke-site/colophon.yml
   ```

7. Repeat the same install smoke test from the generated sdist.

8. Tag the release:

   ```bash
   git tag -a v0.1.0 -m "Colophon v0.1.0"
   git push origin v0.1.0
   ```

9. Run the TestPyPI publish workflow manually on ref `v0.1.0`.
10. Verify TestPyPI by installing dependencies from PyPI, then installing `colophon-site==0.1.0` from TestPyPI with `--no-deps`, and rerun the smoke tests.
11. Recheck that `colophon-site` is still available on PyPI immediately before publishing.
12. Create the GitHub release for `v0.1.0` using the notes above; the release event publishes to PyPI through Trusted Publishing.
13. Verify the real PyPI install in a fresh virtual environment and rerun the smoke tests.
