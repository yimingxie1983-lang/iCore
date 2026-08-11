FROM node:20-bookworm-slim AS web-builder

WORKDIR /build/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV ONEKEY_CONFIG=/app/ops/config/production.yaml

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY cancer_claw/ ./cancer_claw/
COPY run_server.py ./
COPY ops/config/production.yaml ./ops/config/production.yaml
COPY --from=web-builder /build/web/dist ./web/dist

RUN pip install . \
    && groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid 1000 --create-home appuser \
    && mkdir -p \
        /app/cancer_claw/var/state \
        /app/cancer_claw/var/workspaces \
        /app/cancer_claw/var/agent_instances \
        /app/cancer_claw/resources/knowledge/skill_packs/uploads \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

CMD ["python", "run_server.py"]
