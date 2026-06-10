from backend.services.query_utils import fetch_all, fetch_one
from backend.config import DATAMART_SCHEMA_NAME

def get_session_count(years: list[int | str] | None = None) -> int:
    from backend.services.query_utils import build_standard_filters
    where_clause, params, _ = build_standard_filters(
        years=years,
        date_alias="d"
    )
    row = fetch_one(
        f"""
        SELECT COUNT(f.sk_fact_session_id) AS count
        FROM dw.fact_session f
        LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
        WHERE {where_clause}
        """,
        params,
    )
    return int(row.get("count", 0) or 0)


def get_session_kpis(
    years: list[int | str] | None = None,
    region: str | list[str] | None = None,
    program: str | list[str] | None = None,
    month: list[int | str] | None = None,
    quarter: list[int | str] | None = None,
) -> dict:
    from backend.services.query_utils import calculate_ytd_kpis
    
    kpi_defs = [
        {"key": "total_sessions", "label": "Total Sessions", "sql": "COUNT(f.sk_fact_session_id)", "icon": "fas fa-chalkboard-teacher", "color": "bg-navy-blue"},
        {"key": "total_instructors", "label": "Active Instructors", "sql": "COUNT(DISTINCT f.sk_user_id)", "icon": "fas fa-users", "color": "bg-success"},
        {"key": "active_regions", "label": "Active Regions", "sql": "COUNT(DISTINCT g.region_name)", "icon": "fas fa-map-marked-alt", "color": "bg-info"},
        {"key": "total_programs", "label": "Total Programs", "sql": "COUNT(DISTINCT p.program_name)", "icon": "fas fa-project-diagram", "color": "bg-warning"}
    ]
    
    from_clause = f"""
        dw.fact_session f
        LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN dw.dim_program p ON p.sk_program_id = f.sk_program_id
    """
    
    kpis, sparklines = calculate_ytd_kpis(
        kpi_defs=kpi_defs,
        from_clause=from_clause,
        years=years,
        region=region,
        program=program,
        month=month,
        quarter=quarter
    )
    
    return {
        "kpis": kpis,
        "sparklines": sparklines
    }


def get_monthly_sessions(
    years: list[int | str] | None = None,
    region: str | list[str] | None = None,
    program: str | list[str] | None = None,
    month: list[int | str] | None = None,
    quarter: list[int | str] | None = None,
    group_by: str = "month",
) -> list[dict]:
    from backend.services.query_utils import build_standard_filters, get_time_grouping_expressions
    where_clause, params, _ = build_standard_filters(
        years=years,
        region=region,
        area=None,
        program=program,
        month=month,
        quarter=quarter,
        date_alias="d"
    )
    label_expr, sort_expr, grp_expr = get_time_grouping_expressions(group_by)
    rows = fetch_all(
        f"""
        SELECT
            {label_expr} AS label,
            COUNT(f.sk_fact_session_id) AS value
        FROM dw.fact_session f
        LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN dw.dim_program p ON p.sk_program_id = f.sk_program_id
        WHERE {where_clause}
        GROUP BY {grp_expr}
        ORDER BY {sort_expr}
        """,
        params,
    )
    return [{"label": row["label"], "value": float(row["value"])} for row in rows]


def get_sessions_by_region(
    years: list[int | str] | None = None,
    region: str | list[str] | None = None,
    program: str | list[str] | None = None,
    month: list[int | str] | None = None,
    quarter: list[int | str] | None = None,
) -> list[dict]:
    from backend.services.query_utils import build_standard_filters
    where_clause, params, _ = build_standard_filters(
        years=years,
        region=region,
        area=None,
        program=program,
        month=month,
        quarter=quarter,
        date_alias="d"
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
        WHERE {where_clause}
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
    month: list[int | str] | None = None,
    quarter: list[int | str] | None = None,
    group_by: str = "month",
) -> dict:
    kpis_data = get_session_kpis(years, region, program, month, quarter)
    monthly_rows = get_monthly_sessions(years, region, program, month, quarter, group_by)
    region_rows = get_sessions_by_region(years, region, program, month, quarter)


    PALETTE = [
        "#0d6efd", "#6610f2", "#6f42c1", "#d63384", "#dc3545",
        "#fd7e14", "#ffc107", "#198754", "#20c997", "#0dcaf0",
    ]

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
        "kpis": kpis_data["kpis"],
        "sparklines": kpis_data["sparklines"],
        "charts": {
            "monthly": monthly_chart,
            "region":  region_chart,
        },
    }
