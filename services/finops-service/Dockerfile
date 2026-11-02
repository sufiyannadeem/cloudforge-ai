FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN groupadd -g 1000 appgroup \
    && useradd -u 1000 -g appgroup -m -d /home/appuser appuser

COPY requirements.lock .

RUN python -m pip install \
    --no-cache-dir \
    --no-compile \
    --only-binary=:all: \
    --require-hashes \
    -r requirements.lock

COPY app ./app

RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 8091

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8091"]
