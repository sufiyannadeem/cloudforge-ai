FROM python:3.12-alpine3.24@sha256:c5ba3deef00c7758561a0f03c26f44f10589263d40e732b8748e0d1f38f6dd89

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apk add --no-cache ca-certificates libstdc++ krb5-libs=1.22.3-r0 \
    && addgroup -S appgroup \
    && adduser -S -D -H -G appgroup -h /app appuser

COPY requirements.lock .

RUN python -m pip install \
    --no-cache-dir \
    --no-compile \
    --only-binary=:all: \
    --require-hashes \
    -r requirements.lock

COPY app ./app

COPY knowledge ./knowledge

RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 8090

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090", "--timeout-graceful-shutdown", "20", "--timeout-keep-alive", "5", "--limit-concurrency", "16"]
