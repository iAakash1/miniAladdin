FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    HOME=/tmp \
    WEB_CONCURRENCY=1 \
    PORT=8080

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    addgroup --system omnisignal && \
    adduser --system --ingroup omnisignal --home /nonexistent --no-create-home omnisignal

COPY --chown=omnisignal:omnisignal api ./api
COPY --chown=omnisignal:omnisignal src ./src
COPY --chown=omnisignal:omnisignal services ./services
COPY --chown=omnisignal:omnisignal config ./config
COPY --chown=omnisignal:omnisignal artifacts ./artifacts
COPY --chown=omnisignal:omnisignal experiments ./experiments

# The API is a read layer over committed research artifacts. Raw SEC archives,
# derived training panels, and Model Lab predictions belong to offline jobs and
# would add more than 5 GiB to every revision without serving a request.
COPY --chown=omnisignal:omnisignal data/manifests ./data/manifests
COPY --chown=omnisignal:omnisignal data/research/models ./data/research/models
COPY --chown=omnisignal:omnisignal data/research/reports ./data/research/reports
COPY --chown=omnisignal:omnisignal data/research/universe ./data/research/universe

USER omnisignal

CMD ["sh", "-c", "exec uvicorn api.index:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
