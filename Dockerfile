# One container: the Next.js page is built to static files and served by the FastAPI server.

# --- web: build the static page ---
FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
# empty API URL = same origin as the page
ENV NEXT_PUBLIC_API_URL=""
RUN npx next build

# --- app: Python API + the built page ---
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY jury/ jury/
COPY personas/ personas/
COPY prompts/ prompts/
COPY examples/ examples/
RUN uv sync --frozen --no-dev
# headless Chromium for capturing a project's live site (shared path so the non-root user can use it)
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN /app/.venv/bin/python -m playwright install --with-deps --only-shell chromium && chmod -R a+rX /ms-playwright
COPY --from=web /web/out web/out

RUN useradd --create-home jury && mkdir -p /app/data && chown jury /app/data
USER jury
ENV HOST=0.0.0.0 PORT=8000 JURY_DB=/app/data/jury.sqlite
EXPOSE 8000
CMD ["/app/.venv/bin/python", "-m", "jury.api"]
