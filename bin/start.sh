#!/usr/bin/env bash
# Start command for deployed environments: apply migrations, then serve on $PORT.
set -euo pipefail

python manage.py migrate --noinput

exec gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT:?PORT must be set}" \
  --workers "${WEB_CONCURRENCY:-2}" \
  --access-logfile - \
  --error-logfile -
