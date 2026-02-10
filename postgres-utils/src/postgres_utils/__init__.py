"""PostgreSQL Spark Loader - Load data from PostgreSQL into Apache Spark DataFrames."""

from .connection import PostgresConfig, PostgresClient, PostgresSparkReader

__version__ = "1.0.0"
__all__ = [
    "PostgresConfig",
    "PostgresClient",
    "PostgresSparkReader",
]
