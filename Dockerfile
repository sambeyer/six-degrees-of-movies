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


# ── Stage 2: Python runtime ───────────────────────────────────────────────────
# cgr.dev/chainguard/python:latest-dev is a minimal Wolfi-based image:
#   - Python + POSIX shell (needed for entrypoint.sh)
#   - No SSH, no package manager, no compilers — far smaller attack surface
#     than python:3.12-slim
#   - Ships with nonroot user (uid 65532); we use root only for the install step
FROM --platform=linux/amd64 cgr.dev/chainguard/python:latest-dev

# Copy uv — statically linked Rust binary, works on any glibc image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install Python dependencies as root (writes to system Python site-packages)
USER root
WORKDIR /app

# Copy source before uv sync so hatchling can build the package correctly
# (actor_game.py must exist when the wheel is built, or the package is empty)
COPY pyproject.toml uv.lock actor_game.py server.py entrypoint.sh gcs_db.py ./

ENV UV_SYSTEM_PYTHON=1
ENV UV_NO_CACHE=1
RUN uv sync --frozen --no-dev

# Make the venv readable and executable by all users so the nonroot runtime
# user can invoke the installed scripts and packages directly.
RUN chmod -R a+rX /app/.venv

# Copy pre-built frontend static files from stage 1
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Data directory — volume-mounted in local dev; /tmp/actor-game on Cloud Run
ENV ACTOR_GAME_DATA_DIR=/data
VOLUME ["/data"]

EXPOSE 8080

# Drop to nonroot for runtime (uid 65532 in Chainguard images)
USER nonroot

ENTRYPOINT ["/bin/sh", "entrypoint.sh"]
