
# postgres-utils

Load data from PostgreSQL into Apache Spark DataFrames using JDBC connections. Provides both a direct PostgreSQL client and a Spark DataFrame loader.

## Features

- Simple configuration using `PostgresConfig` dataclass
- Use `PostgresClient` for direct PostgreSQL access (with connection pooling)
- Use `PostgresSparkReader` to load tables or queries into Spark DataFrames
- Parallel data loading with partitioning support
- Schema inspection for PostgreSQL tables
- Full type hints and comprehensive docstrings
- Built with `uv` package manager for fast dependency management

## Installation


Using `uv`:

```bash
uv pip install -e .
```

Or with pip:

```bash
pip install -e .
```

## Quick Start

df = loader.read_table("users")
df.show()
df_filtered = loader.read_sql("SELECT * FROM users WHERE age > 18")
df_filtered.show()
df_partitioned = loader.read_partitioned(

```python
from pyspark.sql import SparkSession
from postgres_utils import PostgresConfig, PostgresClient, PostgresSparkReader

# Create PostgreSQL configuration
config = PostgresConfig(
    host="localhost",
    database="mydb",
    user="postgres",
    password="password",
    port=5432,
)

# Direct PostgreSQL access (with connection pooling)
with PostgresClient(config) as db:
    version = db.execute_single("SELECT version()")
    print("PostgreSQL version:", version)

# Spark DataFrame loading
spark = SparkSession.builder.appName("postgres_utils").getOrCreate()
reader = PostgresSparkReader(spark, config)

# Read a table
df = reader.read_table("users")
df.show()

# Read with custom query
df_filtered = reader.read_sql("SELECT * FROM users WHERE age > 18")
df_filtered.show()

# Read with partitioning for large datasets
df_partitioned = reader.read_partitioned(
    "orders",
    partition_column="id",
    num_partitions=8,
    lower_bound=1,
    upper_bound=100000,
)
```

## Configuration


### PostgresConfig Parameters

- `host`: PostgreSQL server hostname or IP address
- `database`: Database name to connect to
- `user`: PostgreSQL username (or set `POSTGRES_USER` environment variable)
- `password`: PostgreSQL password (or set `POSTGRES_PASSWORD` environment variable)
- `port`: PostgreSQL port (default: 5432)

### Environment Variables

Instead of hardcoding credentials, you can use environment variables:

```bash
export POSTGRES_USER=your_username
export POSTGRES_PASSWORD=your_password
```

Then create config without credentials:

```python
config = PostgresConfig(host="localhost", database="mydb")
```

## API Reference


### PostgresClient Methods

- `execute(query, params=None)`: Run a query and return all results (list of tuples)
- `execute_single(query, params=None)`: Run a query and return the first result (tuple or None)
- `execute_dict(query, params=None)`: Run a query and return results as list of dicts

### PostgresSparkReader Methods


#### `read_table(table, **options)`

Read an entire PostgreSQL table into a Spark DataFrame.

**Parameters:**
- `table`: Table name
- `**options`: Additional Spark JDBC options (numPartitions, etc.)

**Returns:** Spark DataFrame


#### `read_sql(query, **options)`

Execute a SQL query and load results into a Spark DataFrame.

**Parameters:**
- `query`: SQL SELECT statement
- `**options`: Additional Spark JDBC options

**Returns:** Spark DataFrame


#### `read_partitioned(table, partition_column, num_partitions, lower_bound, upper_bound, **options)`

Read table with parallel partitioning for better performance.

**Parameters:**
- `table`: Table name
- `partition_column`: Column to partition on
- `num_partitions`: Number of partitions (default: 4)
- `lower_bound`: Lower bound for partition column (optional)
- `upper_bound`: Upper bound for partition column (optional)
- `**options`: Additional Spark JDBC options

**Returns:** Partitioned Spark DataFrame


#### `schema(table)`

Fetch the schema of a PostgreSQL table.

**Parameters:**
- `table`: Table name

**Returns:** Spark StructType schema


## Examples & Tests

- See `examples/test_postgres_utils.py` for a usage script
- Run unit tests with `pytest` (see `tests/` directory)

Install development dependencies:

```bash
uv pip install -e ".[dev]"
```

Run tests:

```bash
pytest
```

Run with coverage:

```bash
pytest --cov=postgres_utils
```

Code quality checks:

```bash
black src/
ruff check src/
mypy src/
```


## License

MIT
