#!/bin/sh
set -e
alembic upgrade head
if [ "$RUN_SEED" = "true" ]; then
  python -m scripts.seed
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers ${UVICORN_ARGS:-}
