# ── Stage 1: build the React frontend ────────────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build
# Output: /app/frontend/dist


# ── Stage 2: Python runtime ───────────────────────────────────────────────────
FROM python:3.12-slim

# Install uv from the official distroless image (fast, no pip upgrade needed)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy source files before uv sync so hatchling can build the package correctly.
# (actor_game.py must exist when the wheel is built, or the installed package is empty.)
COPY pyproject.toml uv.lock actor_game.py server.py entrypoint.sh ./

ENV UV_SYSTEM_PYTHON=1
RUN uv sync --frozen --no-dev

# Copy pre-built frontend static files from stage 1
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Data directory — expected to be a mounted volume at runtime
ENV ACTOR_GAME_DATA_DIR=/data
VOLUME ["/data"]

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
