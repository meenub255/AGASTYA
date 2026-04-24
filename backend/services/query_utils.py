from collections.abc import Sequence

from backend.db import get_datamart_conn

def get_list_filter_clause(column: str, value: str | list[str] | None, cast_type: str | None = None) -> tuple[str, list]:
    """
    Returns a SQL clause and params for both single values and lists.
    Uses ANY() for PostgreSQL lists.
    """
    if value is None or value == "" or (isinstance(value, list) and not value):
        return "TRUE", []
    
    if isinstance(value, list):
        # Filter out empty strings from list
        clean_values = [v for v in value if v and v != ""]
        if not clean_values:
            return "TRUE", []
        
        if cast_type == "int":
            clean_values = [int(v) for v in clean_values if str(v).isdigit()]
            if not clean_values: return "TRUE", []

        return f"{column} = ANY(%s)", [clean_values]
    
    if cast_type == "int" and str(value).isdigit():
        value = int(value)
        
    return f"{column} = %s", [value]


def build_dimension_filters(
    *,
    start: int | list[int] | str | list[str] | None = None,
    end: int | list[int] | str | list[str] | None = None,
    year: int | list[int] | str | list[str] | None = None,
    region: str | list[str] | None = None,
    program: str | list[str] | None = None,
    date_expression: str | None = None,
    year_expression: str | None = None,
    location_expression: str | None = None,
    program_expression: str | None = None,
    instructor: str | list[str] | None = None,
    instructor_expression: str | None = None,
) -> tuple[str, list[object]]:
    clauses: list[str] = []
    params: list[object] = []

    def add_list_filter(col, val, cast_type=None):
        if val is None or val == "" or (isinstance(val, list) and not val):
            return
        if isinstance(val, list):
            clean = [v for v in val if v and v != ""]
            if not clean: return
            if cast_type == "int":
                clean = [int(v) for v in clean if str(v).isdigit()]
                if not clean: return
            clauses.append(f"{col} = ANY(%s)")
            params.append(clean)
        else:
            if cast_type == "int" and str(val).isdigit():
                val = int(val)
            clauses.append(f"{col} = %s")
            params.append(val)

    # Support 'year' as an alternative to start/end if multi-select is used
    if year is not None:
        add_list_filter(year_expression or f"EXTRACT(YEAR FROM {date_expression})", year, cast_type="int")

    if start is not None:
        if isinstance(start, list):
            add_list_filter(year_expression or f"EXTRACT(YEAR FROM {date_expression})", start, cast_type="int")
        else:
            if year_expression:
                clauses.append(f"{year_expression} >= %s")
                params.append(int(start) if str(start).isdigit() else start)
            elif date_expression:
                clauses.append(f"EXTRACT(YEAR FROM {date_expression}) >= %s")
                params.append(int(start) if str(start).isdigit() else start)

    if end is not None:
        if not isinstance(end, list):
            if year_expression:
                clauses.append(f"{year_expression} <= %s")
                params.append(int(end) if str(end).isdigit() else end)
            elif date_expression:
                clauses.append(f"EXTRACT(YEAR FROM {date_expression}) <= %s")
                params.append(int(end) if str(end).isdigit() else end)

    if location_expression:
        add_list_filter(location_expression, region)

    if program_expression:
        add_list_filter(program_expression, program)

    if instructor_expression:
        add_list_filter(instructor_expression, instructor)

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
            sort_sql = f'ORDER BY "{col_name}" {direction}'

    return search_sql, search_params, sort_sql
