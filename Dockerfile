# Prepwise Django API — multi-stage, non-root, gunicorn.
#   docker build -t prepwise-backend .
#   docker run --rm -p 8000:8000 --env-file .env prepwise-backend

# ---------------------------------------------------------------------------
# Stage 1 — resolve dependencies into wheels
# ---------------------------------------------------------------------------
# Every pin in requirements.txt ships a manylinux cp312 wheel (psycopg2-binary
# and Pillow included), so no compiler toolchain is needed. If a future pin is
# source-only, pip will say so here — add:
#   RUN apt-get update && apt-get install -y --no-install-recommends \
#         build-essential libpq-dev && rm -rf /var/lib/apt/lists/*
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /wheels
COPY requirements.txt .
RUN pip wheel --wheel-dir /wheels -r requirements.txt

# ---------------------------------------------------------------------------
# Stage 2 — runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=prepwise.settings \
    PORT=8000

# psycopg2-binary bundles libpq, so the runtime needs no system packages and no
# apt layer at all.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin prepwise

WORKDIR /app

COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-index --find-links=/wheels -r requirements.txt \
 && rm -rf /wheels

COPY . .

# collectstatic needs importable settings, but no database and no real secrets.
RUN SECRET_KEY=build-only DEBUG=False \
    DB_PASSWORD=build-only DB_HOST=localhost \
    python manage.py collectstatic --noinput \
 && chown -R prepwise:prepwise /app/staticfiles

USER prepwise

EXPOSE 8000

# The health endpoint is a cheap DB ping — see apis/views.py::HealthCheckView.
# Uses stdlib urllib so the image needs neither curl nor wget.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD ["python", "-c", "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/api/v1/health/',timeout=4).read()"]

ENTRYPOINT ["/bin/sh", "/app/docker-entrypoint.sh"]
CMD ["gunicorn", "-c", "gunicorn.conf.py", "prepwise.wsgi:application"]
