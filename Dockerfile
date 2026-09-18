FROM node:22-alpine AS web
WORKDIR /build/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
COPY scripts/prepare_web_assets.mjs /build/scripts/prepare_web_assets.mjs
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/backend DAGSTER_HOME=/app/infra/dagster
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY backend ./backend
COPY migrations ./migrations
COPY alembic.ini pyproject.toml ./
COPY infra ./infra
COPY scripts ./scripts
COPY --from=web /build/web/dist ./web/dist
RUN useradd --uid 10001 --create-home datapolice && mkdir -p /app/runtime && chown -R datapolice:datapolice /app
USER datapolice
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "data_police.api:app", "--host", "0.0.0.0", "--port", "8000"]
