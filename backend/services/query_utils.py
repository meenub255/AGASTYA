from collections.abc import Sequence

from backend.db import get_datamart_conn


def build_dimension_filters(
    *,
    start: int | None,
    end: int | None,
    region: str | None,
    program: str | None,
    date_expression: str | None = None,
    year_expression: str | None = None,
    location_expression: str | None = None,
    program_expression: str | None = None,
    instructor: str | None = None,
    instructor_expression: str | None = None,
) -> tuple[str, list[object]]:
    clauses: list[str] = []
    params: list[object] = []

    if start is not None:
        if year_expression:
            clauses.append(f"{year_expression} >= %s")
            params.append(start)
        elif date_expression:
            clauses.append(f"EXTRACT(YEAR FROM {date_expression}) >= %s")
            params.append(start)

    if end is not None:
        if year_expression:
            clauses.append(f"{year_expression} <= %s")
            params.append(end)
        elif date_expression:
            clauses.append(f"EXTRACT(YEAR FROM {date_expression}) <= %s")
            params.append(end)

    if region and location_expression:
        clauses.append(f"{location_expression} = %s")
        params.append(region)

    if program and program_expression:
        clauses.append(f"{program_expression} = %s")
        params.append(program)

    if instructor and instructor_expression:
        clauses.append(f"{instructor_expression} = %s")
        params.append(instructor)

    if not clauses:
        return "", params

    return "WHERE " + " AND ".join(clauses), params


def fetch_one(query: str, params: Sequence[object] | None = None) -> dict:
    with get_datamart_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params or [])
            row = cur.fetchone()
            return dict(row or {})


def fetch_all(query: str, params: Sequence[object] | None = None) -> list[dict]:
    with get_datamart_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params or [])
            return [dict(row) for row in cur.fetchall()]


def parse_datatables_params(params: dict):
    """
    Extracts DataTables parameters from a flat dictionary (e.g. request.query_params).
    """
    return {
        "draw": int(params.get("draw", 1)),
        "start": int(params.get("start", 0)),
        "length": int(params.get("length", 15)),
        "search_value": params.get("search[value]", ""),
        "sort_col_idx": int(params.get("order[0][column]", 0)) if "order[0][column]" in params else None,
        "sort_dir": params.get("order[0][dir]", "asc")
    }


def get_datatables_sql(dt_params: dict, searchable_columns: list[str], sortable_columns: list[str] = None):
    """
    Generates SQL snippets for searching and sorting.
    """
    search_sql = "1=1"
    search_params = []
    
    if dt_params["search_value"] and searchable_columns:
        clauses = []
        for col in searchable_columns:
            clauses.append(f"CAST({col} AS TEXT) ILIKE %s")
            search_params.append(f"%{dt_params['search_value']}%")
        search_sql = "(" + " OR ".join(clauses) + ")"

    sort_sql = ""
    if dt_params["sort_col_idx"] is not None and sortable_columns and dt_params["sort_col_idx"] < len(sortable_columns):
        col_name = sortable_columns[dt_params["sort_col_idx"]]
        if col_name:
            direction = "DESC" if dt_params["sort_dir"].lower() == "desc" else "ASC"
            sort_sql = f"ORDER BY {col_name} {direction}"

    return search_sql, search_params, sort_sql
