# The commit-boundary gate image for aspergillus.
#
# exophial builds this image from the judged commit's own tree and runs the
# gate.command from .exophial/config.yaml in it as the container's argv
# (exophial docs/REPO_INIT.md, section "The gate Dockerfile"). The gate
# command is `uv run --directory python pytest tests -q`, so the image needs
# Python and uv only. The subtree-sync gate does not use this image. It runs
# .pre-commit-config.yaml on the host.
#
# The uv tag matches the host uv (0.11.2). The dependency manifests are
# copied and installed first. `COPY . .` comes last, so a commit that changes
# no dependency file reuses the cached dependency layers.
FROM ghcr.io/astral-sh/uv:0.11.2-python3.12-trixie-slim

ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /gate

COPY python/pyproject.toml python/uv.lock python/
RUN uv sync --locked --directory python --no-install-project

COPY . .

# Installs the aspergillus package itself, now that its source is present.
RUN uv sync --locked --directory python
