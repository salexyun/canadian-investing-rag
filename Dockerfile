# Serving image for the Streamlit app only -- no Playwright/Chromium here
# (see ingestion/Dockerfile for that). Dependencies are synced in their own
# layer, before the rest of the source is copied in, so an edit to app/rag
# code doesn't invalidate the (slow) dependency-install layer on rebuild.
FROM python:3.11.16-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /uvx /bin/

WORKDIR /app

# Skip the dev dependency group (pytest) for both the `uv sync` steps below
# and the `uv run` at container start -- `uv run` re-syncs by default, and
# would otherwise install dev deps at runtime.
ENV UV_NO_DEV=1

COPY pyproject.toml uv.lock .
RUN uv sync --locked --no-install-project

COPY . .
RUN uv sync --locked

EXPOSE 8501

CMD ["uv", "run", "streamlit", "run", "app/main.py", "--server.port=8501", "--server.address=0.0.0.0"]
