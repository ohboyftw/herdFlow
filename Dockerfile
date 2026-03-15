# Stage 1: Frontend build
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Stage 2: Python agent
FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04
ENV DEBIAN_FRONTEND=noninteractive

# Install Python 3.12
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 python3.12-venv python3-pip curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install Python deps
COPY pyproject.toml ./
RUN uv sync --no-dev

# Copy application
COPY agent/ agent/
COPY tests/ tests/
COPY scripts/ scripts/
COPY --from=frontend /app/frontend/dist /app/frontend/dist

# Expose ports
EXPOSE 8080

# Run agent
CMD ["uv", "run", "python", "-m", "agent.main"]
