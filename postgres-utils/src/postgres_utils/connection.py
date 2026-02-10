import logging
import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Generator, Optional

import psycopg2
from psycopg2 import extras
from psycopg2.pool import SimpleConnectionPool
from py4j.protocol import Py4JJavaError
from pyspark.sql import DataFrame, SparkSession

logger = logging.getLogger(__name__)


@dataclass
class PostgresConfig:
    """
    PostgreSQL connection configuration.

    Parameters
    ----------
    host : str
        The hostname or IP address of the PostgreSQL server.
    database : str
        The name of the database to connect to.
    user : str, optional
        The username for authentication. If not provided, reads from POSTGRES_USER environment variable.
    password : str, optional
        The password for authentication. If not provided, reads from POSTGRES_PASSWORD environment variable.
    port : int, optional
        The port number of the PostgreSQL server. Default is 5432.

    Raises
    ------
    ValueError
        If user or password cannot be determined from parameters or environment variables,
        or if host/database are empty.
    """

    host: str
    database: str
    user: str | None = None
    password: str | None = None
    port: int = 5432

    def __post_init__(self) -> None:
        """Validate and resolve credentials from environment variables if needed."""
        if not self.host or not isinstance(self.host, str):
            raise ValueError("host must be a non-empty string")
        if not self.database or not isinstance(self.database, str):
            raise ValueError("database must be a non-empty string")
        if not isinstance(self.port, int) or self.port <= 0 or self.port > 65535:
            raise ValueError("port must be an integer between 1 and 65535")

        self.user = self.user or os.getenv("POSTGRES_USER")
        self.password = self.password or os.getenv("POSTGRES_PASSWORD")

        if not self.user:
            raise ValueError("user must be provided or POSTGRES_USER environment variable must be set")
        if not self.password:
            raise ValueError("password must be provided or POSTGRES_PASSWORD environment variable must be set")

    @property
    def jdbc_url(self) -> str:
        """Generate JDBC URL for PostgreSQL connection."""
        return f"jdbc:postgresql://{self.host}:{self.port}/{self.database}"

    @property
    def jdbc_properties(self) -> dict[str, str]:
        """Generate JDBC connection properties."""
        return {"user": self.user, "password": self.password}

    @property
    def psycopg2_dsn(self) -> str:
        """Generate psycopg2 DSN (Data Source Name) for connections."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


class PostgresClient:
    """
    A PostgreSQL connection manager with connection pooling and context manager support.

    This class provides a convenient interface to connect to PostgreSQL databases,
    execute queries, and manage connections with automatic pooling and error handling.
    Connections are lazy-loaded on first use.

    Parameters
    ----------
    config : PostgresConfig
        PostgreSQL connection configuration.
    min_connections : int, optional
        Minimum number of connections to maintain in the pool. Default is 1.
    max_connections : int, optional
        Maximum number of connections allowed in the pool. Default is 10.

    Attributes
    ----------
    config : PostgresConfig
        PostgreSQL connection configuration.
    min_connections : int
        Minimum number of connections to maintain in the pool.
    max_connections : int
        Maximum number of connections allowed in the pool.

    Examples
    --------
    >>> config = PostgresConfig(host="localhost", database="mydb")
    >>> db = PostgresClient(config)
    >>> with db.cursor() as cur:
    ...     cur.execute("SELECT * FROM users WHERE id = %s", (1,))
    ...     result = cur.fetchone()
    """

    def __init__(
        self,
        config: PostgresConfig,
        min_connections: int = 1,
        max_connections: int = 10,
    ) -> None:
        """Initialize PostgreSQL connection manager.

        Parameters
        ----------
        config : PostgresConfig
            PostgreSQL connection configuration.
        min_connections : int, optional
            Minimum number of connections to maintain in the pool. Default is 1.
        max_connections : int, optional
            Maximum number of connections allowed in the pool. Default is 10.

        Raises
        ------
        ValueError
            If min_connections > max_connections or if connections are not positive.
        """
        if min_connections < 1:
            raise ValueError("min_connections must be at least 1")
        if max_connections < min_connections:
            raise ValueError("max_connections must be >= min_connections")

        self.config = config
        self.min_connections = min_connections
        self.max_connections = max_connections
        self._pool: SimpleConnectionPool | None = None
        self._connected: bool = False

    def connect(self) -> None:
        """
        Establish a connection pool to the PostgreSQL database.

        This method is idempotent—calling it multiple times is safe.

        Raises
        ------
        psycopg2.OperationalError
            If unable to connect to the database server.
        psycopg2.DatabaseError
            If database-related error occurs during connection.

        Notes
        -----
        This method is automatically called when using the context manager.
        """
        if self._connected:
            logger.debug("Already connected to database, skipping reconnect")
            return

        try:
            self._pool = SimpleConnectionPool(
                self.min_connections,
                self.max_connections,
                host=self.config.host,
                port=self.config.port,
                database=self.config.database,
                user=self.config.user,
                password=self.config.password,
            )
            self._connected = True
            logger.info(
                f"Connected to PostgreSQL database '{self.config.database}' on {self.config.host}:{self.config.port}"
            )
        except (psycopg2.OperationalError, psycopg2.DatabaseError) as e:
            logger.exception(f"Failed to connect to PostgreSQL: {e}")
            raise

    def disconnect(self) -> None:
        """
        Close all connections in the pool.

        Releases all database connections and cleans up resources.
        This method is idempotent—calling it multiple times is safe.
        """
        if self._pool:
            try:
                self._pool.closeall()
                self._connected = False
                logger.info("Disconnected from PostgreSQL database")
            except psycopg2.DatabaseError as e:
                logger.exception(f"Database error during disconnect: {e}")
                raise

    @contextmanager
    def cursor(
        self,
        return_dict: bool = False,
    ) -> Generator[psycopg2.extensions.cursor, None, None]:
        """
        Context manager for database cursor operations.

        Automatically connects if not already connected. Safe to use multiple times.

        Parameters
        ----------
        dict_cursor : bool, optional
            Whether to return results as dictionaries instead of tuples. Default is False.

        Yields
        ------
        psycopg2.extensions.cursor
            Database cursor for executing read-only queries.

        Raises
        ------
        RuntimeError
            If connection pool is unavailable.
        psycopg2.DatabaseError
            If query execution fails.

        Examples
        --------
        >>> with db.cursor() as cur:
        ...     cur.execute("SELECT * FROM users WHERE id = %s", (1,))
        ...     result = cur.fetchone()
        """
        if self._pool is None:
            self.connect()
        if self._pool is None:
            raise RuntimeError("Failed to establish database connection pool")

        connection = self._pool.getconn()
        cursor = None
        try:
            if return_dict:
                cursor = connection.cursor(cursor_factory=extras.RealDictCursor)
            else:
                cursor = connection.cursor()
            yield cursor
        except psycopg2.DatabaseError as e:
            logger.exception(f"Database error during cursor operation: {e}")
            raise
        finally:
            if cursor:
                cursor.close()
            if self._pool:
                self._pool.putconn(connection)

    def execute(
        self,
        query: str,
        params: tuple[Any, ...] | list[Any] | None = None,
    ) -> list[tuple[Any, ...]]:
        """
        Execute a read-only query and return results.

        Parameters
        ----------
        query : str
            SQL query to execute.
        params : tuple or list, optional
            Parameters to bind to the query for safe SQL execution.

        Returns
        -------
        list of tuples
            Query results. Empty list if no results found.

        Raises
        ------
        psycopg2.DatabaseError
            If query execution fails.

        Examples
        --------
        >>> results = db.execute("SELECT * FROM users WHERE age > %s", (18,))
        >>> for row in results:
        ...     print(row)
        """
        with self.cursor(return_dict=False) as cur:
            cur.execute(query, params)
            return cur.fetchall()

    def execute_single(
        self,
        query: str,
        params: tuple[Any, ...] | list[Any] | None = None,
    ) -> tuple[Any, ...] | None:
        """
        Execute a read-only query and return the first result.

        Parameters
        ----------
        query : str
            SQL query to execute.
        params : tuple or list, optional
            Parameters to bind to the query.

        Returns
        -------
        tuple or None
            First row of results, or None if no results found.

        Raises
        ------
        psycopg2.DatabaseError
            If query execution fails.

        Examples
        --------
        >>> user = db.execute_single("SELECT * FROM users WHERE id = %s", (1,))
        """
        with self.cursor(return_dict=False) as cur:
            cur.execute(query, params)
            return cur.fetchone()

    def execute_dict(
        self,
        query: str,
        params: tuple[Any, ...] | list[Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Execute a read-only query and return results as dictionaries.

        Parameters
        ----------
        query : str
            SQL query to execute.
        params : tuple or list, optional
            Parameters to bind to the query.

        Returns
        -------
        list of dicts
            Query results with column names as keys.

        Raises
        ------
        psycopg2.DatabaseError
            If query execution fails.

        Examples
        --------
        >>> users = db.execute_dict("SELECT id, name, email FROM users")
        >>> for user in users:
        ...     print(user['name'])
        """
        with self.cursor(return_dict=True) as cur:
            cur.execute(query, params)
            return cur.fetchall()

    def __enter__(self) -> "PostgresClient":
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.disconnect()


class PostgresSparkReader:
    """
    PostgreSQL data reader for Apache Spark.

    This class provides functionality to read data from PostgreSQL tables
    into Spark DataFrames using JDBC connections.

    Parameters
    ----------
    spark : SparkSession
        Active Spark session.
    config : PostgresConfig
        PostgreSQL connection configuration.

    Attributes
    ----------
    spark : SparkSession
        The Spark session used for operations.
    config : PostgresConfig
        PostgreSQL connection configuration.

    Examples
    --------
    >>> from pyspark.sql import SparkSession
    >>> spark = SparkSession.builder.appName("postgres_reader").getOrCreate()
    >>> config = PostgresConfig(host="localhost", database="mydb")
    >>> reader = PostgresSparkReader(spark, config)
    >>> df = reader.read_table("users")
    >>> df.show()
    """

    def __init__(self, spark: SparkSession, config: PostgresConfig) -> None:
        """Initialize PostgreSQL Spark reader.

        Parameters
        ----------
        spark : SparkSession
            Active Spark session.
        config : PostgresConfig
            PostgreSQL connection configuration.

        Raises
        ------
        ValueError
            If spark session is None or config is invalid.
        """
        if not spark:
            raise ValueError("spark session cannot be None")
        self.spark = spark
        self.config = config
        logger.info(f"PostgresSparkReader initialized for {config.database} on {config.host}")

    def read_table(self, table: str, **options: Any) -> Any:
        """
        Read a table from PostgreSQL into a Spark DataFrame.

        Parameters
        ----------
        table : str
            Name of the PostgreSQL table to read.
        **options : Any
            Additional Spark JDBC options (e.g., numPartitions, partitionColumn, lowerBound, upperBound).

        Returns
        -------
        DataFrame
            Spark DataFrame containing the table data.

        Raises
        ------
        psycopg2.DatabaseError
            If table does not exist or query fails.

        Examples
        --------
        >>> df = loader.read_table("users")
        >>> df_partitioned = loader.read_table(
        ...     "users",
        ...     numPartitions=4,
        ...     partitionColumn="id",
        ...     lowerBound=1,
        ...     upperBound=1000
        ... )
        """
        try:
            df = self.spark.read.jdbc(
                url=self.config.jdbc_url,
                table=table,
                properties=self.config.jdbc_properties,
                **options,
            )
            logger.info(f"Successfully read table '{table}' from PostgreSQL")
            return df
        except (Py4JJavaError, psycopg2.DatabaseError) as e:
            logger.exception(f"Failed to read table '{table}' from PostgreSQL: {e}")
            raise

    def read_sql(self, query: str, **options: Any) -> Any:
        """
        Execute a SQL query on PostgreSQL and return results as a Spark DataFrame.

        Parameters
        ----------
        query : str
            SQL query to execute. Must be a valid SELECT statement.
        **options : Any
            Additional Spark JDBC options.

        Returns
        -------
        DataFrame
            Spark DataFrame containing query results.

        Raises
        ------
        psycopg2.DatabaseError
            If query execution fails.

        Examples
        --------
        >>> df = loader.read_sql("SELECT * FROM users WHERE age > 18")
        >>> df_partitioned = loader.read_sql(
        ...     "SELECT * FROM orders WHERE status = 'completed'",
        ...     numPartitions=8
        ... )
        """
        try:
            wrapped_query = f"({query}) AS subquery"
            df = self.spark.read.jdbc(
                url=self.config.jdbc_url,
                table=wrapped_query,
                properties=self.config.jdbc_properties,
                **options,
            )
            logger.info("Successfully executed SQL query and loaded into Spark DataFrame")
            return df
        except (Py4JJavaError, psycopg2.DatabaseError) as e:
            logger.exception(f"Failed to execute SQL query: {e}")
            raise

    def read_partitioned(
        self,
        table: str,
        partition_column: str,
        num_partitions: int = 4,
        lower_bound: int | None = None,
        upper_bound: int | None = None,
        **options: Any,
    ) -> DataFrame:
        """
        Read a table with partitioning for parallel data loading.

        Parameters
        ----------
        table : str
            Name of the PostgreSQL table to read.
        partition_column : str
            Column name to use for partitioning. Should be numeric or timestamp.
        num_partitions : int, optional
            Number of partitions to create. Default is 4.
        lower_bound : int, optional
            Lower bound value for partition column. If None, determined from data.
        upper_bound : int, optional
            Upper bound value for partition column. If None, determined from data.
        **options : Any
            Additional Spark JDBC options.

        Returns
        -------
        DataFrame
            Partitioned Spark DataFrame.

        Raises
        ------
        psycopg2.DatabaseError
            If table does not exist or query fails.

        Examples
        --------
        >>> df = loader.read_partitioned(
        ...     "large_table",
        ...     partition_column="id",
        ...     num_partitions=8,
        ...     lower_bound=1,
        ...     upper_bound=10000
        ... )
        """
        try:
            partition_options = {
                "numPartitions": num_partitions,
                "partitionColumn": partition_column,
            }

            if lower_bound is not None:
                partition_options["lowerBound"] = lower_bound
            if upper_bound is not None:
                partition_options["upperBound"] = upper_bound

            partition_options.update(options)

            df = self.spark.read.jdbc(
                url=self.config.jdbc_url,
                table=table,
                properties=self.config.jdbc_properties,
                **partition_options,
            )
            logger.info(f"Successfully read partitioned table '{table}' with {num_partitions} partitions")
            return df
        except (Py4JJavaError, psycopg2.DatabaseError) as e:
            logger.exception(f"Failed to read partitioned table '{table}': {e}")
            raise

    def schema(self, table: str) -> Any:
        """
        Get the schema of a PostgreSQL table.

        Parameters
        ----------
        table : str
            Name of the PostgreSQL table.

        Returns
        -------
        StructType
            Spark schema of the table.

        Raises
        ------
        psycopg2.DatabaseError
            If table does not exist.

        Examples
        --------
        >>> schema = loader.schema("users")
        >>> print(schema)
        """
        try:
            df = self.read_table(table, numPartitions=1)
            logger.info(f"Retrieved schema for table '{table}'")
            return df.schema
        except (Py4JJavaError, psycopg2.DatabaseError) as e:
            logger.exception(f"Failed to get schema for table '{table}': {e}")
            raise
