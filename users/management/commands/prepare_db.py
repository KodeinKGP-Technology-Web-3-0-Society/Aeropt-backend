"""
Create the Postgres schema used by Django (agent tables stay in public).
Run before `migrate` on a fresh Supabase project.
"""

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Create the Django Postgres schema (default: django)."

    def handle(self, *args, **options):
        schema = getattr(settings, "DB_SCHEMA", "django")
        with connection.cursor() as cursor:
            cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        self.stdout.write(self.style.SUCCESS(f'Schema "{schema}" is ready.'))
