#!/bin/sh
# Hosts without a release step (Hugging Face Spaces) set MIGRATE_ON_START=1.
# Only safe with a single instance: two containers migrating at once can race.
set -e
case "${MIGRATE_ON_START:-}" in
  1|true|True|yes)
    python manage.py prepare_db
    python manage.py migrate --noinput
    ;;
esac
exec "$@"
