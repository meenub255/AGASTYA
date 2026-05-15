from __future__ import annotations

import difflib
import io
import json
import math
import re
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from psycopg2 import sql
from psycopg2.extras import execute_values

from backend.config import MANAGED_SOURCE_TABLES, SOURCE_DB_NAME, TEMPLATES_DIR, SOURCE_SCHEMA_NAME
from backend.db import get_source_conn
from backend.elt_runner import run_elt
from backend.models.schemas import ApiMessage


router = APIRouter(tags=["upload"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
IGNORE_SHEET_VALUE = "__ignore__"
INTEGER_RANGES = {
    "int2": (-32768, 32767),
    "int4": (-2147483648, 2147483647),
    "int8": (-9223372036854775808, 9223372036854775807),
}
SMALL_NUMBERS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
}
TENS_NUMBERS = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
SCALE_NUMBERS = {
    "hundred": 100,
    "thousand": 1000,
    "million": 1000000,
    "billion": 1000000000,
}
TRUE_VALUES = {"true", "t", "yes", "y", "1"}
FALSE_VALUES = {"false", "f", "no", "n", "0"}


def _render_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        name="upload.html",
        request=request,
        context={
            "page_title": "Upload Excel",
            "page_id": "upload",
            "managed_tables": MANAGED_SOURCE_TABLES,
        },
    )


@router.get("/upload", response_class=HTMLResponse)
def upload_page(request: Request):
    return _render_page(request)


@router.post("/upload/truncate", response_model=ApiMessage)
def truncate_source_data():
    deleted_rows: dict[str, int] = {}
    with get_source_conn() as conn:
        with conn.cursor() as cur:
            for table_name in reversed(MANAGED_SOURCE_TABLES):
                cur.execute(
                    sql.SQL("SELECT COUNT(*) AS c FROM {}").format(sql.Identifier(SOURCE_SCHEMA_NAME, table_name))
                )
                deleted_rows[table_name] = int(cur.fetchone()["c"] or 0)
            _truncate_source_tables(cur, MANAGED_SOURCE_TABLES)

    return {
        "message": "Source tables truncated successfully for debugging.",
        "details": {
            "source_database": SOURCE_DB_NAME,
            "deleted_rows": deleted_rows,
        },
    }


@router.post("/upload", response_model=ApiMessage)
async def upload_workbook(
    file: UploadFile = File(...),
    mapping_json: str | None = Form(default=None),
    confirm_insert: bool = Form(default=False),
):
    filename = file.filename or ""
    if not filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please upload an Excel file with .xlsx or .xls extension.",
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The uploaded file is empty.")

    workbook = _read_workbook(file_bytes)
    user_mapping = _parse_mapping_json(mapping_json)

    with get_source_conn() as conn:
        available_tables = _fetch_available_tables(conn)
        missing_tables = [table_name for table_name in MANAGED_SOURCE_TABLES if table_name not in available_tables]
        if missing_tables:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    f"Configured source database '{SOURCE_DB_NAME}' is missing managed tables: "
                    f"{', '.join(missing_tables)}"
                ),
            )

        table_metadata = _fetch_table_metadata(conn, MANAGED_SOURCE_TABLES)
        import_plan = _build_import_plan(workbook, table_metadata, user_mapping)
        if import_plan["requires_configuration"]:
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "message": "Manual sheet or field mapping is required before the import can continue.",
                    "details": {
                        "requires_configuration": True,
                        "filename": filename,
                        "source_database": SOURCE_DB_NAME,
                        "available_tables": list(MANAGED_SOURCE_TABLES),
                        "table_catalog": import_plan["table_catalog"],
                        "sheets": import_plan["sheet_configs"],
                    },
                },
            )

        prepared_tables: dict[str, dict[str, Any]] = {}
        review_by_table: dict[str, dict[str, int]] = {}
        total_new_records = 0
        total_duplicate_records = 0
        total_candidate_records = 0

        with conn.cursor() as cur:
            for table_name in MANAGED_SOURCE_TABLES:
                table_plan = import_plan["table_plans"].get(table_name)
                if table_plan is None:
                    review_by_table[table_name] = {
                        "candidate_rows": 0,
                        "new_rows": 0,
                        "duplicate_rows": 0,
                    }
                    prepared_tables[table_name] = {
                        "selected_columns": [],
                        "new_records": [],
                    }
                    continue

                selected_columns, candidate_records = _prepare_records(
                    dataframe=workbook[table_plan["sheet_name"]],
                    table_metadata=table_metadata[table_name],
                    column_map=table_plan["column_map"],
                )
                new_records, duplicate_count = _partition_new_records(
                    cur=cur,
                    table_name=table_name,
                    selected_columns=selected_columns,
                    candidate_records=candidate_records,
                )
                prepared_tables[table_name] = {
                    "selected_columns": selected_columns,
                    "new_records": new_records,
                }
                review_by_table[table_name] = {
                    "candidate_rows": len(candidate_records),
                    "new_rows": len(new_records),
                    "duplicate_rows": duplicate_count,
                }
                total_candidate_records += len(candidate_records)
                total_new_records += len(new_records)
                total_duplicate_records += duplicate_count

        if total_new_records == 0:
            return {
                "message": "All uploaded rows already exist in the source database. No new records were inserted.",
                "details": {
                    "filename": filename,
                    "source_database": SOURCE_DB_NAME,
                    "inserted_rows": {table_name: 0 for table_name in MANAGED_SOURCE_TABLES},
                    "review": {
                        "candidate_rows": total_candidate_records,
                        "new_rows": 0,
                        "duplicate_rows": total_duplicate_records,
                        "by_table": review_by_table,
                    },
                    "executed_scripts": [],
                },
            }

        if total_duplicate_records > 0 and not confirm_insert:
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "message": (
                        f"Some uploaded rows already exist. There are {total_new_records} new records ready to insert."
                    ),
                    "details": {
                        "requires_confirmation": True,
                        "filename": filename,
                        "source_database": SOURCE_DB_NAME,
                        "review": {
                            "candidate_rows": total_candidate_records,
                            "new_rows": total_new_records,
                            "duplicate_rows": total_duplicate_records,
                            "by_table": review_by_table,
                        },
                    },
                },
            )

        inserted_rows: dict[str, int] = {}
        try:
            with conn.cursor() as cur:
                for table_name in MANAGED_SOURCE_TABLES:
                    prepared = prepared_tables[table_name]
                    inserted_rows[table_name] = _insert_records(
                        cur=cur,
                        table_name=table_name,
                        selected_columns=prepared["selected_columns"],
                        records=prepared["new_records"],
                    )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Source load failed: {exc}",
            ) from exc

    try:
        executed_scripts = run_elt()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Source load completed but ELT failed: {exc}",
        ) from exc

    return {
        "message": "Excel upload completed and only new rows were inserted successfully.",
        "details": {
            "filename": filename,
            "source_database": SOURCE_DB_NAME,
            "inserted_rows": inserted_rows,
            "review": {
                "candidate_rows": total_candidate_records,
                "new_rows": total_new_records,
                "duplicate_rows": total_duplicate_records,
                "by_table": review_by_table,
            },
            "executed_scripts": executed_scripts,
        },
    }


def _parse_mapping_json(mapping_json: str | None) -> dict[str, Any]:
    if not mapping_json:
        return {}

    try:
        payload = json.loads(mapping_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The submitted mapping configuration is not valid JSON.",
        ) from exc

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The submitted mapping configuration must be a JSON object.",
        )

    return payload


def _read_workbook(file_bytes: bytes) -> dict[str, Any]:
    try:
        import pandas as pd
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Pandas and openpyxl are required for Excel uploads. Install requirements before using /upload.",
        ) from exc

    try:
        workbook = pd.read_excel(io.BytesIO(file_bytes), sheet_name=None, dtype=object)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unable to read Excel file: {exc}") from exc

    return workbook


def _fetch_available_tables(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_name = ANY(%s)
            """,
            [SOURCE_SCHEMA_NAME, list(MANAGED_SOURCE_TABLES)],
        )
        return {row["table_name"] for row in cur.fetchall()}


def _fetch_table_metadata(conn, table_names: Iterable[str]) -> dict[str, list[dict[str, Any]]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name, column_name, is_nullable, column_default, data_type, udt_name
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = ANY(%s)
            ORDER BY table_name, ordinal_position
            """,
            [SOURCE_SCHEMA_NAME, list(table_names)],
        )
        metadata: dict[str, list[dict[str, Any]]] = {table_name: [] for table_name in table_names}
        for row in cur.fetchall():
            metadata[row["table_name"]].append(
                {
                    "column_name": row["column_name"],
                    "required": row["is_nullable"] == "NO" and row["column_default"] is None,
                    "data_type": row["data_type"],
                    "udt_name": row["udt_name"],
                }
            )
        return metadata


def _build_import_plan(
    workbook: dict[str, Any],
    table_metadata: dict[str, list[dict[str, Any]]],
    user_mapping: dict[str, Any],
) -> dict[str, Any]:
    sheet_targets = user_mapping.get("sheet_targets", {}) if isinstance(user_mapping, dict) else {}
    column_mappings = user_mapping.get("column_mappings", {}) if isinstance(user_mapping, dict) else {}

    table_catalog = {
        table_name: [
            {
                "target_column": column["column_name"],
                "required": column["required"],
                "data_type": column["data_type"],
            }
            for column in columns
        ]
        for table_name, columns in table_metadata.items()
    }

    requires_configuration = False
    assigned_targets: dict[str, str] = {}
    table_plans: dict[str, dict[str, Any]] = {}
    sheet_configs: list[dict[str, Any]] = []

    for sheet_name, dataframe in workbook.items():
        source_columns = [str(name).strip() for name in dataframe.columns if name is not None and str(name).strip()]
        exact_match = sheet_name in table_metadata
        suggested_target = None if exact_match else _suggest_target_table(sheet_name)
        configured_target = sheet_targets.get(sheet_name)
        selected_target = configured_target if configured_target is not None else (sheet_name if exact_match else suggested_target)
        ignored = selected_target == IGNORE_SHEET_VALUE
        sheet_issues: list[str] = []
        column_configs: list[dict[str, Any]] = []
        unmatched_source_columns = list(source_columns)
        resolved_target = None if ignored else selected_target

        if not exact_match and configured_target is None:
            requires_configuration = True
            sheet_issues.append(
                "This sheet name does not match a configured source table. Choose a target table or ignore it."
            )

        if resolved_target and resolved_target not in table_metadata:
            requires_configuration = True
            sheet_issues.append(f"The selected target table '{resolved_target}' is not valid.")
            resolved_target = None

        if resolved_target and resolved_target in assigned_targets and assigned_targets[resolved_target] != sheet_name:
            requires_configuration = True
            sheet_issues.append(
                f"Target table '{resolved_target}' is already mapped from sheet '{assigned_targets[resolved_target]}'."
            )
        elif resolved_target:
            assigned_targets[resolved_target] = sheet_name

        if resolved_target:
            source_lookup = {_normalize_identifier(column): column for column in source_columns}
            configured_columns = column_mappings.get(sheet_name, {}) if isinstance(column_mappings, dict) else {}
            selected_column_map: dict[str, str] = {}
            used_source_columns: set[str] = set()

            for column_meta in table_metadata[resolved_target]:
                target_column = column_meta["column_name"]
                auto_source = source_lookup.get(_normalize_identifier(target_column))
                chosen_source = configured_columns.get(target_column)

                if chosen_source == "":
                    chosen_source = None
                elif chosen_source is None:
                    chosen_source = auto_source
                elif chosen_source not in source_columns:
                    chosen_source = None
                    requires_configuration = True
                    sheet_issues.append(
                        f"Column mapping for '{target_column}' points to a source column that does not exist anymore."
                    )

                if chosen_source:
                    used_source_columns.add(chosen_source)
                    selected_column_map[target_column] = chosen_source
                elif column_meta["required"]:
                    requires_configuration = True
                    sheet_issues.append(f"Required target column '{target_column}' needs a source column mapping.")

                column_configs.append(
                    {
                        "target_column": target_column,
                        "required": column_meta["required"],
                        "data_type": column_meta["data_type"],
                        "selected_source": chosen_source,
                        "auto_source": auto_source,
                    }
                )

            unmatched_source_columns = [column for column in source_columns if column not in used_source_columns]
            if not sheet_issues and resolved_target:
                table_plans[resolved_target] = {
                    "sheet_name": sheet_name,
                    "column_map": selected_column_map,
                }

        sheet_configs.append(
            {
                "sheet_name": sheet_name,
                "source_columns": source_columns,
                "selected_target": selected_target or "",
                "suggested_target": suggested_target or "",
                "exact_match": exact_match,
                "ignored": ignored,
                "issues": list(dict.fromkeys(sheet_issues)),
                "column_mappings": column_configs,
                "unmatched_source_columns": unmatched_source_columns,
            }
        )

    return {
        "requires_configuration": requires_configuration,
        "table_catalog": table_catalog,
        "sheet_configs": sheet_configs,
        "table_plans": table_plans,
    }


def _truncate_source_tables(cur, table_names: Iterable[str]) -> None:
    identifiers = [sql.Identifier(SOURCE_SCHEMA_NAME, table_name) for table_name in table_names]
    statement = sql.SQL("TRUNCATE TABLE {} RESTART IDENTITY CASCADE").format(sql.SQL(", ").join(identifiers))
    cur.execute(statement)


def _prepare_records(
    dataframe: Any,
    table_metadata: list[dict[str, Any]],
    column_map: dict[str, str],
) -> tuple[list[str], list[tuple[Any, ...]]]:
    trimmed = dataframe.dropna(how="all")
    if trimmed.empty:
        return [], []

    selected_metadata = [
        column_meta
        for column_meta in table_metadata
        if column_meta["column_name"] in column_map and column_map[column_meta["column_name"]] in trimmed.columns
    ]
    if not selected_metadata:
        return [], []

    selected_columns = [column_meta["column_name"] for column_meta in selected_metadata]
    records: list[tuple[Any, ...]] = []
    for row in trimmed.to_dict(orient="records"):
        record = tuple(
            _coerce_value(row.get(column_map[column_meta["column_name"]]), column_meta)
            for column_meta in selected_metadata
        )
        if any(value is not None for value in record):
            records.append(record)

    return selected_columns, records


def _partition_new_records(
    cur,
    table_name: str,
    selected_columns: list[str],
    candidate_records: list[tuple[Any, ...]],
) -> tuple[list[tuple[Any, ...]], int]:
    if not selected_columns or not candidate_records:
        return [], 0

    existing_records = _fetch_existing_records(cur, table_name, selected_columns)
    seen_records: set[tuple[Any, ...]] = set()
    new_records: list[tuple[Any, ...]] = []
    duplicate_count = 0

    for record in candidate_records:
        normalized = tuple(_normalize_record_value(value) for value in record)
        if normalized in seen_records or normalized in existing_records:
            duplicate_count += 1
            continue
        seen_records.add(normalized)
        new_records.append(record)

    return new_records, duplicate_count


def _fetch_existing_records(cur, table_name: str, selected_columns: list[str]) -> set[tuple[Any, ...]]:
    if not selected_columns:
        return set()

    statement = sql.SQL("SELECT DISTINCT {} FROM {}") .format(
        sql.SQL(", ").join(sql.Identifier(column_name) for column_name in selected_columns),
        sql.Identifier(SOURCE_SCHEMA_NAME, table_name),
    )
    cur.execute(statement)
    return {
        tuple(_normalize_record_value(row.get(column_name)) for column_name in selected_columns)
        for row in cur.fetchall()
    }


def _insert_records(cur, table_name: str, selected_columns: list[str], records: list[tuple[Any, ...]]) -> int:
    if not selected_columns or not records:
        return 0

    insert_sql = sql.SQL("INSERT INTO {} ({}) VALUES %s").format(
        sql.Identifier(SOURCE_SCHEMA_NAME, table_name),
        sql.SQL(", ").join(sql.Identifier(column_name) for column_name in selected_columns),
    )
    execute_values(cur, insert_sql.as_string(cur.connection), records, page_size=500)
    return len(records)


def _normalize_record_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return value.normalize() if value == value.to_integral() else value.normalize()
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    return value


def _coerce_value(value: Any, column_meta: dict[str, Any]) -> Any:
    normalized_value = _normalize_cell_value(value)
    if normalized_value is None:
        return None

    udt_name = column_meta.get("udt_name")
    data_type = column_meta.get("data_type")

    if udt_name in INTEGER_RANGES:
        return _coerce_integer(normalized_value, udt_name)

    if data_type in {"numeric", "double precision", "real", "decimal"}:
        return _coerce_decimal(normalized_value)

    if data_type == "boolean":
        return _coerce_boolean(normalized_value)

    if data_type == "date":
        return _coerce_date(normalized_value)

    if data_type and data_type.startswith("timestamp"):
        return _coerce_timestamp(normalized_value)

    return normalized_value


def _coerce_integer(value: Any, udt_name: str) -> int | None:
    numeric_value = _as_number(value)
    if numeric_value is None:
        return None

    try:
        coerced = int(numeric_value)
    except (TypeError, ValueError, OverflowError):
        return None

    lower_bound, upper_bound = INTEGER_RANGES[udt_name]
    if coerced < lower_bound or coerced > upper_bound:
        return None

    return coerced


def _coerce_decimal(value: Any) -> Decimal | None:
    numeric_value = _as_number(value)
    if numeric_value is None:
        return None

    try:
        return Decimal(str(numeric_value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _coerce_boolean(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float, Decimal)):
        return bool(value)

    cleaned = str(value).strip().lower()
    if cleaned in TRUE_VALUES:
        return True
    if cleaned in FALSE_VALUES:
        return False
    return None


def _coerce_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    try:
        import pandas as pd

        parsed = pd.to_datetime(value, errors="coerce")
    except Exception:
        return None

    if parsed is None or getattr(parsed, "isna", lambda: False)():
        return None

    try:
        return parsed.to_pydatetime().date()
    except Exception:
        return None


def _coerce_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value

    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())

    try:
        import pandas as pd

        parsed = pd.to_datetime(value, errors="coerce")
    except Exception:
        return None

    if parsed is None or getattr(parsed, "isna", lambda: False)():
        return None

    try:
        return parsed.to_pydatetime()
    except Exception:
        return None


def _as_number(value: Any) -> Decimal | None:
    if isinstance(value, bool):
        return Decimal(int(value))

    if isinstance(value, Decimal):
        return value

    if isinstance(value, int):
        return Decimal(value)

    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return Decimal(str(value))

    cleaned = str(value).strip().lower().replace(",", "")
    if not cleaned:
        return None

    if re.fullmatch(r"[-+]?\d+(\.\d+)?", cleaned):
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None

    words_value = _words_to_number(cleaned)
    if words_value is not None:
        return Decimal(words_value)

    return None


def _words_to_number(text: str) -> int | None:
    normalized = text.replace("-", " ")
    normalized = re.sub(r"\band\b", " ", normalized)
    tokens = [token for token in normalized.split() if token]
    if not tokens:
        return None

    total = 0
    current = 0
    matched_token = False

    for token in tokens:
        if token in SMALL_NUMBERS:
            current += SMALL_NUMBERS[token]
            matched_token = True
        elif token in TENS_NUMBERS:
            current += TENS_NUMBERS[token]
            matched_token = True
        elif token == "hundred":
            current = max(current, 1) * 100
            matched_token = True
        elif token in {"thousand", "million", "billion"}:
            scale = SCALE_NUMBERS[token]
            current = max(current, 1)
            total += current * scale
            current = 0
            matched_token = True
        else:
            return None

    if not matched_token:
        return None

    return total + current


def _suggest_target_table(sheet_name: str) -> str | None:
    normalized_sheet_name = _normalize_identifier(sheet_name)
    normalized_targets = {_normalize_identifier(table_name): table_name for table_name in MANAGED_SOURCE_TABLES}

    if normalized_sheet_name in normalized_targets:
        return normalized_targets[normalized_sheet_name]

    close_matches = difflib.get_close_matches(normalized_sheet_name, normalized_targets.keys(), n=1, cutoff=0.6)
    if close_matches:
        return normalized_targets[close_matches[0]]

    return None


def _normalize_identifier(value: Any) -> str:
    text = str(value).strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def _normalize_cell_value(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None

    if isinstance(value, Decimal):
        return value

    if isinstance(value, (datetime, date)):
        return value

    if hasattr(value, "to_pydatetime"):
        return value.to_pydatetime()

    if hasattr(value, "item") and not isinstance(value, (bytes, bytearray)):
        try:
            return value.item()
        except Exception:
            return value

    return value
