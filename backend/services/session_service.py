from backend.services.query_utils import build_dimension_filters, fetch_all, fetch_one


LOCATION_EXPRESSION = "g.region_name"
PROGRAM_EXPRESSION = "p.program_name"
YEAR_EXPRESSION = "d.year_actual"


def get_session_count(years: list[int | str] | None = None) -> int:
    where_clause, params = build_dimension_filters(
        year=years,
        region=None,
        program=None,
        year_expression=YEAR_EXPRESSION,
    )
    row = fetch_one(
        f"""
        SELECT COUNT(f.sk_fact_session_id) AS count
        FROM dw.fact_session f
        LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
        {where_clause}
        """,
        params,
    )
    return int(row.get("count", 0) or 0)


def get_session_kpis(
    years: list[int | str] | None = None,
    region: str | list[str] | None = None,
    program: str | list[str] | None = None,
) -> dict[str, int]:
    where_clause, params = build_dimension_filters(
        year=years,
        region=region,
        program=program,
        year_expression=YEAR_EXPRESSION,
        location_expression=LOCATION_EXPRESSION,
        program_expression=PROGRAM_EXPRESSION,
    )
    row = fetch_one(
        f"""
        SELECT
            COUNT(f.sk_fact_session_id) AS total_sessions,
            COUNT(DISTINCT f.sk_user_id) AS total_instructors,
            COUNT(DISTINCT g.region_name) AS active_regions,
            COUNT(DISTINCT p.program_name) AS total_programs
        FROM dw.fact_session f
        LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN dw.dim_program p ON p.sk_program_id = f.sk_program_id
        {where_clause}
        """,
        params,
    )
    return {
        "total_sessions": int(row.get("total_sessions", 0) or 0),
        "total_instructors": int(row.get("total_instructors", 0) or 0),
        "active_regions": int(row.get("active_regions", 0) or 0),
        "total_programs": int(row.get("total_programs", 0) or 0),
    }


def get_monthly_sessions(
    years: list[int | str] | None = None,
    region: str | list[str] | None = None,
    program: str | list[str] | None = None,
) -> list[dict]:
    where_clause, params = build_dimension_filters(
        year=years,
        region=region,
        program=program,
        year_expression=YEAR_EXPRESSION,
        location_expression=LOCATION_EXPRESSION,
        program_expression=PROGRAM_EXPRESSION,
    )
    rows = fetch_all(
        f"""
        SELECT
            TO_CHAR(DATE_TRUNC('month', d.full_date), 'YYYY-MM') AS label,
            COUNT(f.sk_fact_session_id) AS value
        FROM dw.fact_session f
        LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN dw.dim_program p ON p.sk_program_id = f.sk_program_id
        {where_clause}
        GROUP BY DATE_TRUNC('month', d.full_date)
        ORDER BY DATE_TRUNC('month', d.full_date)
        """,
        params,
    )
    return [{"label": row["label"], "value": float(row["value"])} for row in rows]


def get_sessions_by_region(
    years: list[int | str] | None = None,
    region: str | list[str] | None = None,
    program: str | list[str] | None = None,
) -> list[dict]:
    where_clause, params = build_dimension_filters(
        year=years,
        region=region,
        program=program,
        year_expression=YEAR_EXPRESSION,
        location_expression=LOCATION_EXPRESSION,
        program_expression=PROGRAM_EXPRESSION,
    )
    rows = fetch_all(
        f"""
        SELECT
            COALESCE(g.region_name, 'Unknown') AS label,
            COUNT(f.sk_fact_session_id) AS value
        FROM dw.fact_session f
        LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN dw.dim_program p ON p.sk_program_id = f.sk_program_id
        {where_clause}
        GROUP BY COALESCE(g.region_name, 'Unknown')
        ORDER BY value DESC, label
        LIMIT 20
        """,
        params,
    )
    return [{"label": row["label"], "value": float(row["value"])} for row in rows]


def get_available_years() -> list[int]:
    rows = fetch_all(
        f"""
        SELECT DISTINCT d.year_actual AS year
        FROM dw.fact_session f
        JOIN dw.dim_date d ON d.date_id = f.date_id
        WHERE d.year_actual IS NOT NULL
        ORDER BY d.year_actual
        """
    )
    return [int(row["year"]) for row in rows if row.get("year") is not None]
