from concurrent.futures import ThreadPoolExecutor

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


def get_unified_session_data(
    years: list[int | str] | None = None,
    region: str | list[str] | None = None,
    program: str | list[str] | None = None,
) -> dict:
    """
    Returns KPIs + chart data in a single call with parallel DB queries.
    Shape:
      { kpis: {...}, charts: { monthly: <ChartJS dataset>, region: <ChartJS dataset> } }
    """
    where_clause, params = build_dimension_filters(
        year=years,
        region=region,
        program=program,
        year_expression=YEAR_EXPRESSION,
        location_expression=LOCATION_EXPRESSION,
        program_expression=PROGRAM_EXPRESSION,
    )

    SQL_KPI = f"""
        SELECT COUNT(f.sk_fact_session_id) AS total_sessions,
               COUNT(DISTINCT f.sk_user_id) AS total_instructors,
               COUNT(DISTINCT g.region_name) AS active_regions,
               COUNT(DISTINCT p.program_name) AS total_programs
        FROM dw.fact_session f
        LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN dw.dim_program p ON p.sk_program_id = f.sk_program_id
        {where_clause}
    """

    SQL_MONTHLY = f"""
        SELECT TO_CHAR(DATE_TRUNC('month', d.full_date), 'YYYY-MM') AS label,
               COUNT(f.sk_fact_session_id) AS value
        FROM dw.fact_session f
        LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN dw.dim_program p ON p.sk_program_id = f.sk_program_id
        {where_clause}
        GROUP BY DATE_TRUNC('month', d.full_date)
        ORDER BY DATE_TRUNC('month', d.full_date)
    """

    SQL_REGION = f"""
        SELECT COALESCE(g.region_name, 'Unknown') AS label,
               COUNT(f.sk_fact_session_id) AS value
        FROM dw.fact_session f
        LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN dw.dim_program p ON p.sk_program_id = f.sk_program_id
        {where_clause}
        GROUP BY COALESCE(g.region_name, 'Unknown')
        ORDER BY value DESC, label
        LIMIT 20
    """

    PALETTE = [
        "#0d6efd", "#6610f2", "#6f42c1", "#d63384", "#dc3545",
        "#fd7e14", "#ffc107", "#198754", "#20c997", "#0dcaf0",
    ]

    with ThreadPoolExecutor(max_workers=3) as ex:
        f_kpi     = ex.submit(fetch_one, SQL_KPI,     params)
        f_monthly = ex.submit(fetch_all, SQL_MONTHLY, params)
        f_region  = ex.submit(fetch_all, SQL_REGION,  params)

    kpi_row      = f_kpi.result()
    monthly_rows = f_monthly.result()
    region_rows  = f_region.result()

    kpis = {
        "total_sessions":    int(kpi_row.get("total_sessions",    0) or 0),
        "total_instructors": int(kpi_row.get("total_instructors", 0) or 0),
        "active_regions":    int(kpi_row.get("active_regions",    0) or 0),
        "total_programs":    int(kpi_row.get("total_programs",    0) or 0),
    }

    monthly_labels = [r["label"] for r in monthly_rows]
    monthly_values = [float(r["value"]) for r in monthly_rows]
    monthly_chart = {
        "labels": monthly_labels,
        "datasets": [{
            "label": "Sessions",
            "data": monthly_values,
            "borderColor": PALETTE[0],
            "backgroundColor": PALETTE[0] + "33",
            "tension": 0.4,
            "fill": True,
            "pointRadius": 4,
            "pointBackgroundColor": PALETTE[0],
        }],
    }

    region_labels = [r["label"] for r in region_rows]
    region_values = [float(r["value"]) for r in region_rows]
    region_colors = [PALETTE[i % len(PALETTE)] for i in range(len(region_labels))]
    region_chart = {
        "labels": region_labels,
        "datasets": [{
            "label": "Sessions by Region",
            "data": region_values,
            "backgroundColor": region_colors,
            "borderColor":     [c + "cc" for c in region_colors],
            "borderWidth": 1,
        }],
    }

    return {
        "kpis": kpis,
        "charts": {
            "monthly": monthly_chart,
            "region":  region_chart,
        },
    }
