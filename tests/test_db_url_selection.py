import os
import db


def test_get_db_url_prefers_test_database_url_under_pytest(monkeypatch):
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://u:p@localhost:9999/testdb")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@cloudsql/whatever")
    assert db.get_db_url() == "postgresql://u:p@localhost:9999/testdb"


def test_get_db_url_defaults_to_local_under_pytest(monkeypatch):
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@cloudsql/whatever")
    assert db.get_db_url() == "postgresql://postgres:postgres@localhost:5432/smartassistant"


def test_get_db_url_uses_database_url_when_not_pytest(monkeypatch):
    # Simulate non-pytest runtime
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)

    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/proddb")
    assert db.get_db_url() == "postgresql://u:p@localhost:5432/proddb"
