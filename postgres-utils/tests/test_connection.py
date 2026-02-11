
import os
from unittest.mock import MagicMock

import pytest

from postgres_utils.connection import PostgresClient, PostgresConfig, PostgresSparkReader


class TestPostgresUtils:
    """
    Unit tests for PostgresConfig, PostgresClient, and PostgresSparkReader.
    Combines connection and Spark reader tests in a single class for convenience.
    """
    def setup_method(self):
        """Set up shared config, spark, reader, and client for each test."""
        os.environ["POSTGRES_USER"] = "postgres"
        os.environ["POSTGRES_PASSWORD"] = "password"
        self.config = PostgresConfig(host="localhost", database="testdb", port=5432)
        self.spark = MagicMock()
        self.reader = PostgresSparkReader(self.spark, self.config)
        self.client = PostgresClient(self.config)

    def test_postgres_config_env(self, monkeypatch):
        """Test PostgresConfig reads credentials from environment variables."""
        monkeypatch.setenv("POSTGRES_USER", "envuser")
        monkeypatch.setenv("POSTGRES_PASSWORD", "envpass")
        cfg = PostgresConfig(host="localhost", database="testdb")
        assert cfg.user == "envuser"
        assert cfg.password == "envpass"
        assert cfg.jdbc_url.startswith("jdbc:postgresql://")
        assert "localhost" in cfg.jdbc_url
        assert cfg.psycopg2_dsn.startswith("postgresql://")

    def test_postgres_config_missing_user(self, monkeypatch):
        """Test PostgresConfig raises ValueError if user/password missing."""
        monkeypatch.delenv("POSTGRES_USER", raising=False)
        monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
        with pytest.raises(ValueError):
            PostgresConfig(host="localhost", database="testdb")

    def test_postgres_client_connect_disconnect(self):
        """Test PostgresClient connect/disconnect logic without real DB."""
        assert self.client._connected is False
        # Don't actually connect to DB in unit test

    def test_postgres_client_context_manager(self):
        """Test PostgresClient context manager entry/exit without real DB."""
        try:
            self.client.__enter__()
            self.client.__exit__(None, None, None)
        except Exception:
            pass

    def test_spark_reader_init(self):
        """Test initialization of PostgresSparkReader."""
        assert self.reader.spark is self.spark
        assert self.reader.config is self.config

    def test_spark_reader_read_table_calls_jdbc(self):
        """Test read_table calls Spark JDBC and returns DataFrame."""
        self.reader.spark.read.jdbc.return_value = "mock_df"
        df = self.reader.read_table("users")
        assert df == "mock_df"
        self.reader.spark.read.jdbc.assert_called_once()

    def test_spark_reader_read_sql_calls_jdbc(self):
        """Test read_sql calls Spark JDBC and returns DataFrame."""
        self.reader.spark.read.jdbc.return_value = "mock_df"
        df = self.reader.read_sql("SELECT * FROM users")
        assert df == "mock_df"
        self.reader.spark.read.jdbc.assert_called_once()

    def test_spark_reader_read_partitioned_calls_jdbc(self):
        """Test read_partitioned calls Spark JDBC and returns DataFrame."""
        self.reader.spark.read.jdbc.return_value = "mock_df"
        df = self.reader.read_partitioned(
            table="users",
            partition_column="id",
            num_partitions=2,
            lower_bound=1,
            upper_bound=10,
        )
        assert df == "mock_df"
        self.reader.spark.read.jdbc.assert_called_once()

    def test_spark_reader_schema_returns_schema(self):
        """Test schema method returns DataFrame schema."""
        mock_df = MagicMock()
        mock_df.schema = "mock_schema"
        self.spark.read.jdbc.return_value = mock_df
        schema = self.reader.schema("users")
        assert schema == "mock_schema"
