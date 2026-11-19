from contextlib import contextmanager
import pytest
from fastapi import HTTPException
from . import main


def test_readiness_is_bounded_and_does_not_expose_database_errors(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'production')
    for name in ['DATABASE_URL', 'FINOPS_PROJECT_DATABASE_URL', 'FINOPS_AUDIT_DATABASE_URL']:
        monkeypatch.setenv(name, 'postgresql://fixture.invalid/database')
    calls = []
    class Database:
        def execute(self, sql):
            assert sql == 'SELECT 1'
    @contextmanager
    def connect(dsn, **options):
        calls.append(options)
        assert options == {'connect_timeout': 2, 'autocommit': True, 'options': '-c statement_timeout=1000'}
        yield Database()
    monkeypatch.setattr(main.psycopg, 'connect', connect)
    assert main.ready()['status'] == 'ready'
    assert calls
    def unavailable(*args, **kwargs):
        raise main.psycopg.OperationalError('private credentials and connection details')
    monkeypatch.setattr(main.psycopg, 'connect', unavailable)
    with pytest.raises(HTTPException) as error:
        main.ready()
    assert error.value.status_code == 503
    assert 'private' not in error.value.detail
