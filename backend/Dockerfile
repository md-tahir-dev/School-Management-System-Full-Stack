FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# requirements-dev.txt = runtime deps + pytest/ruff, so `docker compose exec api pytest` works.
# For a slimmer production image, install requirements.txt only.
COPY requirements.txt requirements-dev.txt ./
RUN pip install -r requirements-dev.txt

COPY . .
RUN chmod +x docker-entrypoint.sh \
 && mkdir -p /app/uploads \
 && useradd --system --uid 10001 app && chown -R app /app
USER app

EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
