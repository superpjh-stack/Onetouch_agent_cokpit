FROM node:22-bookworm-slim AS web
WORKDIR /build
COPY v2/web/package.json v2/web/package-lock.json ./
RUN npm ci
COPY v2/web/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY v2/requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir -r /tmp/requirements.lock \
    && useradd --create-home --uid 10001 app \
    && mkdir -p /app/data \
    && chown app:app /app /app/data
COPY onetouch_agent ./onetouch_agent
COPY sample_docs ./sample_docs
COPY v2/*.py ./v2/
COPY --from=web /build/dist ./v2/web/dist
USER app
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/api/health', timeout=3)"
CMD ["uvicorn", "v2.api:app", "--host", "0.0.0.0", "--port", "8501", "--no-proxy-headers"]
