
"""
Example script to test PostgresClient and PostgresSparkLoader from postgres_utils.
This is not a unit test, but a demonstration of usage.
"""

import logging
import os
from postgres_utils import PostgresConfig, PostgresClient, PostgresSparkLoader

def setup_logging():
    logging.basicConfig(level=logging.INFO)

def get_config():
    # Set environment variables or replace with your credentials
    os.environ.setdefault("POSTGRES_USER", "postgres")
    os.environ.setdefault("POSTGRES_PASSWORD", "password")
    return PostgresConfig(
        host="localhost",
        database="testdb",
        port=5432,
    )

def test_postgres_client(config):
    print("\n=== Testing PostgresClient ===")
    try:
        with PostgresClient(config) as db:
            results = db.execute("SELECT version()")
            print(f"PostgreSQL version: {results[0][0]}")
    except Exception as e:
        print(f"PostgresClient error: {e}")

def test_postgres_spark_loader(config):
    print("\n=== Testing PostgresSparkLoader ===")
    try:
        from pyspark.sql import SparkSession
        spark = SparkSession.builder.appName("postgres_utils_example").getOrCreate()
        loader = PostgresSparkLoader(spark, config)
        # Try to read a table (replace 'users' with a real table in your DB)
        df = loader.read_table("users")
        print(f"Loaded DataFrame with {df.count()} rows and schema: {df.schema}")
        spark.stop()
    except Exception as e:
        print(f"PostgresSparkLoader error: {e}")

def main():
    setup_logging()
    config = get_config()
    test_postgres_client(config)
    test_postgres_spark_loader(config)

if __name__ == "__main__":
    main()
