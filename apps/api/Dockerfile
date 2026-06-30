FROM python:3.14-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY alembic.ini ./
RUN uv sync --frozen --no-dev
# Run unprivileged (defense in depth; the K8s securityContext also enforces
# runAsNonRoot). Fixes Trivy DS-0002.
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser
EXPOSE 8080
CMD ["uv", "run", "uvicorn", "atlas_api.main:app", "--host", "0.0.0.0", "--port", "8080"]
