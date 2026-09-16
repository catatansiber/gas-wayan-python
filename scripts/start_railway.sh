#!/bin/sh
set -eu

: "${PORT:=8000}"
: "${WEB_CONCURRENCY:=2}"

attempt=1
max_attempts=10
until python manage.py migrate --noinput; do
    if [ "$attempt" -ge "$max_attempts" ]; then
        echo "Database belum siap setelah $max_attempts percobaan; startup dibatalkan." >&2
        exit 1
    fi
    echo "Database belum siap (percobaan $attempt/$max_attempts); mencoba lagi dalam 3 detik." >&2
    attempt=$((attempt + 1))
    sleep 3
done

python manage.py collectstatic --noinput

exec gunicorn config.wsgi:application \
    --bind "0.0.0.0:${PORT}" \
    --workers "${WEB_CONCURRENCY}" \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
