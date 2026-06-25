"""
Data Operations Service
-----------------------
Business logic for batch CRUD, SQL file management,
sequential batch execution, and execution logging.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from psycopg2 import sql as psql

from backend.config import (
    DATA_OPS_FILES_DIR,
    DATA_OPS_MAX_FILE_SIZE,
    DATA_OPS_SCHEMA_NAME,
    DATAMART_SCHEMA_NAME,
    FDW_SOURCE_SCHEMA,
    SOURCE_SCHEMA_NAME,
)
from backend.db import get_data_ops_conn, get_datamart_conn


SCHEMA = DATA_OPS_SCHEMA_NAME


# ── helpers ──────────────────────────────────────────────────
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _row_to_dict(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        elif isinstance(v, uuid.UUID):
            out[k] = str(v)
        else:
            out[k] = v
    return out


def _rows_to_list(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_row_to_dict(r) for r in rows]


def _ensure_upload_dir() -> Path:
    DATA_OPS_FILES_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_OPS_FILES_DIR


def _file_checksum(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


# ═══════════════════════════════════════════════════════════════
#  BATCH CRUD
# ═══════════════════════════════════════════════════════════════

def list_batches() -> list[dict[str, Any]]:
    conn = get_data_ops_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT b.*,
                       COALESCE(fc.file_count, 0) AS sql_files_count
                FROM {SCHEMA}.batch b
                LEFT JOIN (
                    SELECT batch_id, COUNT(*) AS file_count
                    FROM {SCHEMA}.sql_file
                    GROUP BY batch_id
                ) fc ON fc.batch_id = b.id
                ORDER BY b.updated_at DESC
            """)
            return _rows_to_list(cur.fetchall())
    finally:
        conn.close()


def get_batch(batch_id: str) -> dict[str, Any] | None:
    conn = get_data_ops_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM {SCHEMA}.batch WHERE id = %s",
                [batch_id],
            )
            batch = _row_to_dict(cur.fetchone())
            if batch is None:
                return None

            cur.execute(
                f"""SELECT * FROM {SCHEMA}.sql_file
                    WHERE batch_id = %s
                    ORDER BY execution_order, uploaded_at""",
                [batch_id],
            )
            batch["sql_files"] = _rows_to_list(cur.fetchall())
            return batch
    finally:
        conn.close()


def create_batch(
    name: str,
    description: str | None,
    environment: str,
    created_by: str = "system",
) -> dict[str, Any]:
    conn = get_data_ops_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""INSERT INTO {SCHEMA}.batch
                       (name, description, environment, status, created_by, created_at, updated_at)
                    VALUES (%s, %s, %s, 'draft', %s, %s, %s)
                    RETURNING *""",
                [name, description, environment.upper(), created_by, _now(), _now()],
            )
            row = _row_to_dict(cur.fetchone())
        conn.commit()
        return row
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_batch(
    batch_id: str,
    name: str | None = None,
    description: str | None = None,
    environment: str | None = None,
) -> dict[str, Any] | None:
    conn = get_data_ops_conn()
    try:
        sets: list[str] = []
        params: list[Any] = []
        if name is not None:
            sets.append("name = %s")
            params.append(name)
        if description is not None:
            sets.append("description = %s")
            params.append(description)
        if environment is not None:
            sets.append("environment = %s")
            params.append(environment.upper())
        if not sets:
            return get_batch(batch_id)
        sets.append("updated_at = %s")
        params.append(_now())
        params.append(batch_id)

        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE {SCHEMA}.batch SET {', '.join(sets)} WHERE id = %s RETURNING *",
                params,
            )
            row = _row_to_dict(cur.fetchone())
        conn.commit()
        return row
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def delete_batch(batch_id: str) -> bool:
    conn = get_data_ops_conn()
    try:
        # Get file paths to clean up from disk
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT file_path FROM {SCHEMA}.sql_file WHERE batch_id = %s",
                [batch_id],
            )
            file_paths = [r["file_path"] for r in cur.fetchall()]

            cur.execute(
                f"DELETE FROM {SCHEMA}.batch WHERE id = %s",
                [batch_id],
            )
            deleted = cur.rowcount > 0
        conn.commit()

        # Clean up files from disk
        if deleted:
            for fp in file_paths:
                try:
                    p = Path(fp)
                    if p.exists():
                        p.unlink()
                except OSError:
                    pass

        return deleted
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
#  SQL FILE MANAGEMENT
# ═══════════════════════════════════════════════════════════════

def upload_sql_file(
    batch_id: str,
    file_name: str,
    file_bytes: bytes,
    uploaded_by: str = "system",
) -> dict[str, Any]:
    if len(file_bytes) > DATA_OPS_MAX_FILE_SIZE:
        raise ValueError(
            f"File size ({len(file_bytes):,} bytes) exceeds maximum "
            f"({DATA_OPS_MAX_FILE_SIZE:,} bytes)."
        )

    if not file_name.lower().endswith(".sql"):
        raise ValueError("Only .sql files are allowed.")

    checksum = _file_checksum(file_bytes)
    content_text = file_bytes.decode("utf-8", errors="replace")
    upload_dir = _ensure_upload_dir() / batch_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Use a unique name to avoid collisions
    stored_name = f"{uuid.uuid4().hex[:8]}_{file_name}"
    file_path = upload_dir / stored_name
    file_path.write_bytes(file_bytes)

    conn = get_data_ops_conn()
    try:
        with conn.cursor() as cur:
            # Determine next execution order
            cur.execute(
                f"SELECT COALESCE(MAX(execution_order), 0) + 1 AS next_order FROM {SCHEMA}.sql_file WHERE batch_id = %s",
                [batch_id],
            )
            next_order = cur.fetchone()["next_order"]

            cur.execute(
                f"""INSERT INTO {SCHEMA}.sql_file
                       (batch_id, file_name, file_path, execution_order, checksum, file_size, content, uploaded_by, uploaded_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING *""",
                [
                    batch_id,
                    file_name,
                    str(file_path),
                    next_order,
                    checksum,
                    len(file_bytes),
                    content_text,
                    uploaded_by,
                    _now(),
                ],
            )
            row = _row_to_dict(cur.fetchone())

            # Touch parent batch updated_at
            cur.execute(
                f"UPDATE {SCHEMA}.batch SET updated_at = %s WHERE id = %s",
                [_now(), batch_id],
            )
        conn.commit()
        return row
    except Exception:
        conn.rollback()
        # Clean up written file on failure
        try:
            file_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    finally:
        conn.close()


def get_sql_file(file_id: str) -> dict[str, Any] | None:
    conn = get_data_ops_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM {SCHEMA}.sql_file WHERE id = %s",
                [file_id],
            )
            return _row_to_dict(cur.fetchone())
    finally:
        conn.close()


def delete_sql_file(file_id: str) -> bool:
    conn = get_data_ops_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT file_path, batch_id FROM {SCHEMA}.sql_file WHERE id = %s",
                [file_id],
            )
            row = cur.fetchone()
            if row is None:
                return False

            file_path = row["file_path"]
            batch_id = row["batch_id"]

            cur.execute(
                f"DELETE FROM {SCHEMA}.sql_file WHERE id = %s",
                [file_id],
            )

            # Reindex execution_order for remaining files in the batch
            cur.execute(
                f"""WITH ordered AS (
                        SELECT id, ROW_NUMBER() OVER (ORDER BY execution_order, uploaded_at) AS new_order
                        FROM {SCHEMA}.sql_file
                        WHERE batch_id = %s
                    )
                    UPDATE {SCHEMA}.sql_file sf
                    SET execution_order = o.new_order
                    FROM ordered o
                    WHERE sf.id = o.id""",
                [batch_id],
            )

            cur.execute(
                f"UPDATE {SCHEMA}.batch SET updated_at = %s WHERE id = %s",
                [_now(), batch_id],
            )
        conn.commit()

        # Clean up file
        try:
            p = Path(file_path)
            if p.exists():
                p.unlink()
        except OSError:
            pass

        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def reorder_sql_file(file_id: str, new_order: int) -> dict[str, Any] | None:
    """Move a file to a specific execution_order position. Other files shift accordingly."""
    conn = get_data_ops_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT batch_id, execution_order FROM {SCHEMA}.sql_file WHERE id = %s",
                [file_id],
            )
            row = cur.fetchone()
            if row is None:
                return None

            batch_id = row["batch_id"]
            old_order = row["execution_order"]

            if new_order == old_order:
                return get_sql_file(file_id)

            # Shift others
            if new_order < old_order:
                cur.execute(
                    f"""UPDATE {SCHEMA}.sql_file
                        SET execution_order = execution_order + 1
                        WHERE batch_id = %s AND execution_order >= %s AND execution_order < %s""",
                    [batch_id, new_order, old_order],
                )
            else:
                cur.execute(
                    f"""UPDATE {SCHEMA}.sql_file
                        SET execution_order = execution_order - 1
                        WHERE batch_id = %s AND execution_order > %s AND execution_order <= %s""",
                    [batch_id, old_order, new_order],
                )

            cur.execute(
                f"UPDATE {SCHEMA}.sql_file SET execution_order = %s WHERE id = %s",
                [new_order, file_id],
            )

            cur.execute(
                f"UPDATE {SCHEMA}.batch SET updated_at = %s WHERE id = %s",
                [_now(), batch_id],
            )
        conn.commit()
        return get_sql_file(file_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
#  BATCH EXECUTION
# ═══════════════════════════════════════════════════════════════

def execute_batch(batch_id: str, triggered_by: str = "system") -> dict[str, Any]:
    """
    Execute all SQL files in a batch sequentially.
    Stops on first failure. Updates batch and execution status.
    """
    # 1. Load the batch and its files
    batch = get_batch(batch_id)
    if batch is None:
        raise ValueError("Batch not found.")

    sql_files = batch.get("sql_files", [])
    if not sql_files:
        raise ValueError("Batch has no SQL files to execute.")

    if batch["status"] == "running":
        raise ValueError("Batch is already running.")

    # 2. Mark batch as running and create execution record
    ops_conn = get_data_ops_conn()
    try:
        with ops_conn.cursor() as cur:
            cur.execute(
                f"UPDATE {SCHEMA}.batch SET status = 'running', updated_at = %s WHERE id = %s",
                [_now(), batch_id],
            )
            cur.execute(
                f"""INSERT INTO {SCHEMA}.batch_execution
                       (batch_id, status, started_at, triggered_by)
                    VALUES (%s, 'running', %s, %s)
                    RETURNING *""",
                [batch_id, _now(), triggered_by],
            )
            execution = _row_to_dict(cur.fetchone())
            execution_id = execution["id"]

            # Pre-create log entries
            for sf in sql_files:
                cur.execute(
                    f"""INSERT INTO {SCHEMA}.execution_log
                           (execution_id, sql_file_id, file_name, status)
                        VALUES (%s, %s, %s, 'pending')""",
                    [execution_id, sf["id"], sf["file_name"]],
                )
        ops_conn.commit()
    except Exception:
        ops_conn.rollback()
        raise
    finally:
        ops_conn.close()

    # 3. Execute each SQL file sequentially against the datamart
    overall_status = "completed"

    for sf in sql_files:
        file_start = time.time()
        file_status = "success"
        error_msg = None

        try:
            sql_content = sf.get("content", "")
            if not sql_content:
                # Read from disk as fallback
                fp = Path(sf["file_path"])
                if fp.exists():
                    sql_content = fp.read_text(encoding="utf-8")
                else:
                    raise FileNotFoundError(f"SQL file not found on disk: {sf['file_path']}")

            if sql_content.strip():
                dm_conn = get_datamart_conn()
                try:
                    with dm_conn.cursor() as cur:
                        cur.execute(
                            f"SET search_path = {DATAMART_SCHEMA_NAME}, {SOURCE_SCHEMA_NAME}, {FDW_SOURCE_SCHEMA}, public"
                        )
                        cur.execute(sql_content)
                    dm_conn.commit()
                except Exception as exc:
                    dm_conn.rollback()
                    raise exc
                finally:
                    dm_conn.close()

        except Exception as exc:
            file_status = "failed"
            error_msg = str(exc)
            overall_status = "failed"

        duration_ms = int((time.time() - file_start) * 1000)

        # Update the log entry
        ops_conn = get_data_ops_conn()
        try:
            with ops_conn.cursor() as cur:
                cur.execute(
                    f"""UPDATE {SCHEMA}.execution_log
                        SET status = %s,
                            started_at = %s,
                            completed_at = %s,
                            duration_ms = %s,
                            error_message = %s
                        WHERE execution_id = %s AND sql_file_id = %s""",
                    [
                        file_status,
                        datetime.fromtimestamp(file_start, tz=timezone.utc),
                        _now(),
                        duration_ms,
                        error_msg,
                        execution_id,
                        sf["id"],
                    ],
                )
            ops_conn.commit()
        except Exception:
            ops_conn.rollback()
        finally:
            ops_conn.close()

        # Stop on failure
        if file_status == "failed":
            break

    # 4. Finalize execution and batch status
    ops_conn = get_data_ops_conn()
    try:
        with ops_conn.cursor() as cur:
            cur.execute(
                f"""UPDATE {SCHEMA}.batch_execution
                    SET status = %s, completed_at = %s
                    WHERE id = %s""",
                [overall_status, _now(), execution_id],
            )
            cur.execute(
                f"UPDATE {SCHEMA}.batch SET status = %s, updated_at = %s WHERE id = %s",
                [overall_status, _now(), batch_id],
            )
        ops_conn.commit()
    except Exception:
        ops_conn.rollback()
    finally:
        ops_conn.close()

    return get_execution(execution_id)


# ═══════════════════════════════════════════════════════════════
#  EXECUTION HISTORY
# ═══════════════════════════════════════════════════════════════

def list_executions(batch_id: str) -> list[dict[str, Any]]:
    conn = get_data_ops_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""SELECT be.*,
                           EXTRACT(EPOCH FROM (be.completed_at - be.started_at))::int * 1000 AS total_duration_ms
                    FROM {SCHEMA}.batch_execution be
                    WHERE be.batch_id = %s
                    ORDER BY be.started_at DESC""",
                [batch_id],
            )
            return _rows_to_list(cur.fetchall())
    finally:
        conn.close()


def get_execution(execution_id: str) -> dict[str, Any] | None:
    conn = get_data_ops_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM {SCHEMA}.batch_execution WHERE id = %s",
                [execution_id],
            )
            execution = _row_to_dict(cur.fetchone())
            if execution is None:
                return None

            cur.execute(
                f"""SELECT * FROM {SCHEMA}.execution_log
                    WHERE execution_id = %s
                    ORDER BY started_at NULLS LAST""",
                [execution_id],
            )
            execution["logs"] = _rows_to_list(cur.fetchall())
            return execution
    finally:
        conn.close()
