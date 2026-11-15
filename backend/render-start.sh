#!/bin/sh
set -eu

# Free Render services do not support a paid pre-deploy command. This demo runs
# one web instance, so migrations finish before the API starts on each cold boot.
alembic upgrade head
python -m app.seed
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --proxy-headers \
  --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}"
