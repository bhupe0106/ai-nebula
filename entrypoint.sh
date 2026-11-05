#!/usr/bin/env sh
set -e

echo "Collecting static files…"
python manage.py collectstatic --noinput

echo "Applying database migrations…"
python manage.py migrate --noinput

if [ -n "$DJANGO_SUPERUSER_EMAIL" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
  echo "Ensuring admin user $DJANGO_SUPERUSER_EMAIL exists…"
  python manage.py createsuperuser --noinput || true
fi

exec "$@"
