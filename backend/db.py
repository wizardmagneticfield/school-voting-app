import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from psycopg2.pool import SimpleConnectionPool

_pool = None


def init_pool():
    global _pool
    _pool = SimpleConnectionPool(1, 10, os.environ.get(
        "DATABASE_URL", "postgresql://voting:voting@localhost:5432/voting"))


@contextmanager
def get_cursor():
    """Yields a dict cursor inside a transaction: commit on success, rollback on error."""
    conn = _pool.getconn()
    try:
        with conn:                      # psycopg2: commits or rolls back the transaction
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                yield cur
    finally:
        _pool.putconn(conn)


def init_schema():
    with open(os.path.join(os.path.dirname(__file__), "schema.sql")) as f, get_cursor() as cur:
        cur.execute(f.read())
