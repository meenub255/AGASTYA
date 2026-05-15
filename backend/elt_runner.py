from __future__ import annotations

from pathlib import Path

from psycopg2 import sql

from backend.config import (
    DATAMART_DB_NAME,
    DB_HOST,
    DB_PASSWORD,
    DB_PORT,
    DB_SSL_MODE,
    DB_USER,
    FDW_SOURCE_SCHEMA,
    MANAGED_SOURCE_TABLES,
    SOURCE_DB_NAME,
    SOURCE_SCHEMA_NAME,
    DATAMART_SCHEMA_NAME,
    SQL_DIR,
)
from backend.db import get_datamart_conn


INCLUDE_PREFIX = "-- include:"
DEFAULT_RUN_FILE = "elt_run.sql"
FDW_SERVER_NAME = "pramana_source_server"


def run_elt(script_name: str = DEFAULT_RUN_FILE) -> list[str]:
    script_path = SQL_DIR / script_name
    if not script_path.exists():
        raise FileNotFoundError(f"ELT script not found: {script_path}")

    with get_datamart_conn() as conn:
        _ensure_foreign_source_access(conn)
        
        with conn.cursor() as cur:
            cur.execute(f"SET search_path = {DATAMART_SCHEMA_NAME}, {SOURCE_SCHEMA_NAME}, {FDW_SOURCE_SCHEMA}, public")

        executed_files: list[str] = []
        for sql_text, resolved_path in _expand_script(script_path):
            with conn.cursor() as cur:
                cur.execute(_render_sql(sql_text))
            executed_files.append(resolved_path.name)

        return executed_files


def _ensure_foreign_source_access(conn) -> None:
    # If source and datamart are in the same database, we don't need FDW
    if SOURCE_DB_NAME == DATAMART_DB_NAME:
        return

    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS postgres_fdw")
        cur.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(FDW_SOURCE_SCHEMA)))
        cur.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(FDW_SOURCE_SCHEMA)))
        cur.execute(sql.SQL("DROP SERVER IF EXISTS {} CASCADE").format(sql.Identifier(FDW_SERVER_NAME)))
        cur.execute(
            sql.SQL(
                "CREATE SERVER {} FOREIGN DATA WRAPPER postgres_fdw OPTIONS (host %s, dbname %s, port %s, sslmode %s)"
            ).format(sql.Identifier(FDW_SERVER_NAME)),
            [DB_HOST, SOURCE_DB_NAME, str(DB_PORT), DB_SSL_MODE],
        )
        cur.execute(
            sql.SQL("CREATE USER MAPPING FOR CURRENT_USER SERVER {} OPTIONS (user %s, password %s)").format(
                sql.Identifier(FDW_SERVER_NAME)
            ),
            [DB_USER, DB_PASSWORD],
        )
        cur.execute(
            sql.SQL("IMPORT FOREIGN SCHEMA {} LIMIT TO ({}) FROM SERVER {} INTO {}").format(
                sql.Identifier(SOURCE_SCHEMA_NAME),
                sql.SQL(", ").join(sql.Identifier(t) for t in MANAGED_SOURCE_TABLES),
                sql.Identifier(FDW_SERVER_NAME),
                sql.Identifier(FDW_SOURCE_SCHEMA),
            )
        )


def _expand_script(script_path: Path) -> list[tuple[str, Path]]:
    statements: list[tuple[str, Path]] = []

    for raw_line in script_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or not line.startswith(INCLUDE_PREFIX):
            continue

        include_name = line.removeprefix(INCLUDE_PREFIX).strip()
        include_path = (script_path.parent / include_name).resolve()
        if not include_path.exists():
            raise FileNotFoundError(f"Included ELT script not found: {include_path}")
        statements.extend(_expand_script(include_path))

    if statements:
        return statements

    return [(script_path.read_text(encoding="utf-8"), script_path)]


def _render_sql(sql_text: str) -> str:
    return sql_text.replace("{{SOURCE_FDW_SCHEMA}}", FDW_SOURCE_SCHEMA)
