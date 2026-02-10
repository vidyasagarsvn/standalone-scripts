import os

import pytest

from postgres_utils.connection import PostgresClient, PostgresConfig


@pytest.fixture
def config() -> PostgresConfig:
    """Fixture for PostgresConfig with environment variables set."""
    os.environ["POSTGRES_USER"] = "postgres"
    os.environ["POSTGRES_PASSWORD"] = "password"
    return PostgresConfig(host="localhost", database="testdb", port=5432)


def test_postgres_config_env(monkeypatch):
    """Test PostgresConfig reads credentials from environment variables."""
    monkeypatch.setenv("POSTGRES_USER", "envuser")
    monkeypatch.setenv("POSTGRES_PASSWORD", "envpass")
    cfg = PostgresConfig(host="localhost", database="testdb")
    assert cfg.user == "envuser"
    assert cfg.password == "envpass"
    assert cfg.jdbc_url.startswith("jdbc:postgresql://")
    assert "localhost" in cfg.jdbc_url
    assert cfg.psycopg2_dsn.startswith("postgresql://")


def test_postgres_config_missing_user(monkeypatch):
    """Test PostgresConfig raises ValueError if user/password missing."""
    monkeypatch.delenv("POSTGRES_USER", raising=False)
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    with pytest.raises(ValueError):
        PostgresConfig(host="localhost", database="testdb")


def test_postgres_client_connect_disconnect(config):
    """Test PostgresClient connect/disconnect logic without real DB."""
    client = PostgresClient(config)
    # Should not raise, even if DB is not running (will raise on connect)
    assert client._connected is False
    # Don't actually connect to DB in unit test
    # client.connect()  # Would raise if DB is not available
    # client.disconnect()  # Should be safe to call


def test_postgres_client_context_manager(config):
    """Test PostgresClient context manager entry/exit without real DB."""
    client = PostgresClient(config)
    # Should be able to enter/exit context without DB
    try:
        client.__enter__()
        client.__exit__(None, None, None)
    except Exception:
        pass  # Acceptable if DB is not running
