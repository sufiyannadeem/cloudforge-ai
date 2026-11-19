import pytest
from .service_identity import production_database


@pytest.mark.parametrize("dsn", ["postgres://postgres@db/app?sslmode=verify-full", "postgres://cf_aiops@db/app?sslmode=disable", "postgres://cf_aiops@db/app?sslmode=require", "postgres://cf_aiops@/app?host=/tmp&sslmode=verify-full"])
def test_production_database_fail_closed(monkeypatch, dsn):
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(RuntimeError): production_database(dsn, "cf_aiops")


def test_verified_database_and_development_compatibility(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    production_database("postgres://cf_aiops@db/app?sslmode=verify-full", "cf_aiops")
    monkeypatch.setenv("APP_ENV", "development")
    production_database("postgres://shared@localhost/app?sslmode=disable", "cf_aiops")


def test_runtime_cannot_initialize_production_schema(monkeypatch):
    from .database import initialize_database, _require_database_url
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(RuntimeError, match="explicit migration"):
        initialize_database()
    monkeypatch.setenv("DATABASE_URL", "first")
    assert _require_database_url() == "first"
    monkeypatch.setenv("DATABASE_URL", "rotated")
    assert _require_database_url() == "rotated"
