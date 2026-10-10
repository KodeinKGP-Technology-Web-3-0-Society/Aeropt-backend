from django.apps import AppConfig
from django.db.backends.signals import connection_created


def _pin_search_path(sender, connection, **kwargs):
    # The `options=-c search_path` startup parameter in settings is not honoured by
    # every connection pooler (Supabase's included); without this, migrate would
    # create the Django tables in `public`, next to the agent's.
    if connection.vendor != "postgresql":
        return
    from django.conf import settings

    with connection.cursor() as cursor:
        cursor.execute(f'SET search_path TO "{settings.DB_SCHEMA}", public')


class ApisConfig(AppConfig):
    name = 'apis'

    def ready(self):
        connection_created.connect(_pin_search_path, dispatch_uid="apis.pin_search_path")
