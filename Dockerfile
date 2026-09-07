# Serving image for the Streamlit app only -- no Playwright/Chromium here
# (see ingestion/Dockerfile for that). Dependencies are synced in their own
# layer, before the rest of the source is copied in, so an edit to app/rag
# code doesn't invalidate the (slow) dependency-install layer on rebuild.
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock .
RUN uv sync --locked --no-install-project

COPY . .
RUN uv sync --locked

EXPOSE 8501

CMD ["uv", "run", "streamlit", "run", "app/main.py", "--server.port=8501", "--server.address=0.0.0.0"]
