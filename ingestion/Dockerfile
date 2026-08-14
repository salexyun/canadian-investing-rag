# Separate image from the root Dockerfile (the serving app) on purpose:
# ingestion needs a real Chromium browser on disk for the CRA/CIRO/AMF
# fetch path (they block plain HTTP clients -- see fetch.py), which the
# serving app never touches. Baking that into the app image would undo
# the CPU-only/no-CUDA size work already done there for nothing the app
# uses. Kestra's Docker task runner uses this image for the fetch/chunk/
# load flow tasks (../flows/ingestion.yml); it shares the same
# pyproject.toml/uv.lock as the app -- one dependency set for the whole
# project, this image just adds the browser binary on top.
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock .
RUN uv sync --locked --no-install-project

COPY . .
RUN uv sync --locked

# --with-deps installs the OS-level libraries Chromium needs (fonts,
# libnss3, etc.) that python:3.11-slim doesn't ship -- Playwright's own
# apt-get wrapper, not a hand-maintained package list here.
RUN uv run playwright install --with-deps chromium

# Stays at /app (not /app/ingestion) -- flows/ingestion.yml runs
# `uv run python ingestion/<script>.py` the same way it's run outside
# Docker, and uv's project-root discovery + the scripts' own
# REPO_ROOT-relative paths both assume /app is the repo root.
