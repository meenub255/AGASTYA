import psycopg2
from psycopg2.extras import RealDictCursor

from backend.config import (
    ADMIN_DB_NAME,
    DATAMART_DB_NAME,
    DB_HOST,
    DB_PASSWORD,
    DB_PORT,
    DB_SSL_MODE,
    DB_USER,
    SOURCE_DB_NAME,
)


def _connect(db_name: str):
    return psycopg2.connect(
        dbname=db_name,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        sslmode=DB_SSL_MODE,
        cursor_factory=RealDictCursor,
    )


def get_admin_conn():
    return _connect(ADMIN_DB_NAME)


def get_source_conn():
    return _connect(SOURCE_DB_NAME)


def get_datamart_conn():
    from backend.config import DATAMART_SCHEMA_NAME
    conn = _connect(DATAMART_DB_NAME)
    with conn.cursor() as cur:
        cur.execute(f"SET search_path TO {DATAMART_SCHEMA_NAME}, public")
    return conn


def get_data_ops_conn():
    from backend.config import DATA_OPS_SCHEMA_NAME
    conn = _connect(ADMIN_DB_NAME)
    with conn.cursor() as cur:
        cur.execute(f"SET search_path TO {DATA_OPS_SCHEMA_NAME}, public")
    return conn


def get_conn():
    return get_datamart_conn()
