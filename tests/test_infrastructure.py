import pytest
from django.db import connection


@pytest.mark.django_db
def test_database_connection_uses_postgresql():
    connection.ensure_connection()
    assert connection.vendor == "postgresql"
