import os
from unittest.mock import MagicMock

import pytest

from postgres_utils.connection import PostgresConfig, PostgresSparkReader


@pytest.fixture
def config():
    os.environ["POSTGRES_USER"] = "postgres"
    os.environ["POSTGRES_PASSWORD"] = "password"
    return PostgresConfig(host="localhost", database="testdb", port=5432)


def test_spark_reader_init(config):
    spark = MagicMock()
    reader = PostgresSparkReader(spark, config)
    assert reader.spark is spark
    assert reader.config is config


def test_spark_reader_read_table_calls_jdbc(config):
    spark = MagicMock()
    reader = PostgresSparkReader(spark, config)
    reader.spark.read.jdbc.return_value = "mock_df"
    df = reader.read_table("users")
    assert df == "mock_df"
    reader.spark.read.jdbc.assert_called_once()


def test_spark_reader_read_sql_calls_jdbc(config):
    spark = MagicMock()
    reader = PostgresSparkReader(spark, config)
    reader.spark.read.jdbc.return_value = "mock_df"
    df = reader.read_sql("SELECT * FROM users")
    assert df == "mock_df"
    reader.spark.read.jdbc.assert_called_once()


def test_spark_reader_read_partitioned_calls_jdbc(config):
    spark = MagicMock()
    reader = PostgresSparkReader(spark, config)
    reader.spark.read.jdbc.return_value = "mock_df"
    df = reader.read_partitioned(
        table="users",
        partition_column="id",
        num_partitions=2,
        lower_bound=1,
        upper_bound=10,
    )
    assert df == "mock_df"
    reader.spark.read.jdbc.assert_called_once()


def test_spark_reader_schema_returns_schema(config):
    spark = MagicMock()
    mock_df = MagicMock()
    mock_df.schema = "mock_schema"
    spark.read.jdbc.return_value = mock_df
    reader = PostgresSparkReader(spark, config)
    schema = reader.schema("users")
    assert schema == "mock_schema"
