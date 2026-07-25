# syntax=docker/dockerfile:1

# Verify both tags before the first build. The annotations below let Renovate keep
# them current once this repository is in its scope.
# renovate: datasource=docker depName=python
ARG PYTHON_VERSION=3.14.6
# renovate: datasource=docker depName=ghcr.io/astral-sh/uv
ARG UV_VERSION=0.9.7

# ---------- uv binary ----------
# A named stage from the pinned uv image. BuildKit does not expand variables in
# `COPY --from=<image>:${VAR}`, but FROM does expand a global-scope ARG — so pull
# the version here and copy from the static stage name below.
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# ---------- builder ----------
FROM python:${PYTHON_VERSION}-slim-trixie AS builder

COPY --from=uv /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependency layer — cached unless the lockfile changes.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Project layer.
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ---------- runtime ----------
FROM python:${PYTHON_VERSION}-slim-trixie AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    TZ=America/Chicago

# UID/GID 1000 to match the lab convention.
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid 1000 --create-home --shell /usr/sbin/nologin app

WORKDIR /app

COPY --from=builder --chown=1000:1000 /app /app
COPY --chown=1000:1000 docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 0755 /usr/local/bin/docker-entrypoint.sh

USER 1000:1000

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
