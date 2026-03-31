# Target linux/amd64 explicitly — Cloud Run only runs amd64 and building on
# Apple Silicon without this flag produces an arm64 image that crashes on startup.

# ── Stage 1: build the React frontend ────────────────────────────────────────
# cgr.dev/chainguard/node:latest-dev includes npm and a shell for build tools
FROM --platform=linux/amd64 cgr.dev/chainguard/node:latest-dev AS frontend-builder

USER root
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build
# Output: /app/frontend/dist


# ── Stage 2: Python dependency builder ───────────────────────────────────────
FROM --platform=linux/amd64 cgr.dev/chainguard/python:latest-dev AS python-builder

# Copy uv — statically linked Rust binary, works on any glibc image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

USER root
WORKDIR /app

# Only copy the lockfile — src/ is not needed to install third-party deps.
# This layer stays cached across all code changes.
COPY pyproject.toml uv.lock ./

ENV UV_SYSTEM_PYTHON=1
ENV UV_NO_CACHE=1
RUN uv sync --frozen --no-dev --no-install-project

# Make the venv readable and executable by all users so the nonroot runtime
# user can invoke the installed scripts and packages directly.
RUN chmod -R a+rX /app/.venv


# ── Stage 3: Python runtime ───────────────────────────────────────────────────
# cgr.dev/chainguard/python:latest — no shell, no uv, minimal attack surface.
FROM --platform=linux/amd64 cgr.dev/chainguard/python:latest

USER root
WORKDIR /app

# Copy the built venv — no uv in this image
COPY --from=python-builder /app/.venv /app/.venv

# Application source — on PYTHONPATH so modules are importable without install
COPY src/ ./src/
COPY entrypoint.py ./

# Copy pre-built frontend static files from stage 1
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Data directory — volume-mounted in local dev; /tmp/actor-game on Cloud Run
ENV ACTOR_GAME_DATA_DIR=/data
# src/ is on the path so actor_game, server, and gcs_db are importable
ENV PYTHONPATH=/app/src
VOLUME ["/data"]

EXPOSE 8080

# Drop to nonroot for runtime (uid 65532 in Chainguard images)
USER nonroot

ENTRYPOINT ["/app/.venv/bin/python", "/app/entrypoint.py"]
