import logging

from django.db.backends.postgresql.base import DatabaseWrapper as PostgresDatabaseWrapper

logger = logging.getLogger(__name__)


class DatabaseWrapper(PostgresDatabaseWrapper):
    """PostgreSQL backend that does not abort on versions older than 14.

    Django 5.2 officially requires PostgreSQL 14+. This project still has
    PostgreSQL 10.6 on port 5432. PostgreSQL 17 is already installed on
    port 5433; start that service and switch DATABASES['default']['PORT']
    when possible.
    """

    def check_database_version_supported(self):
        minimum = self.features.minimum_database_version
        current = self.get_database_version()
        if minimum is not None and current < minimum:
            logger.warning(
                "Django 5.2 requiere PostgreSQL %s o superior (encontrado %s). "
                "Se omite el corte para permitir continuar; migre a PostgreSQL 14+.",
                ".".join(str(part) for part in minimum),
                ".".join(str(part) for part in current),
            )
