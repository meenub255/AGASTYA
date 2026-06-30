from backend.services.query_utils import fetch_all, fetch_one
from backend.config import DATAMART_SCHEMA_NAME


def get_school_visit_filters(region_name: str | list[str] | None = None):
    from backend.services.query_utils import get_list_filter_clause
    # 1. Fetch all Regions always
    region_query = f"SELECT DISTINCT region_name FROM {DATAMART_SCHEMA_NAME}.dim_geography WHERE region_name IS NOT NULL ORDER BY region_name"
    regions = [row["region_name"] for row in fetch_all(region_query)]
    
    # 2. Fetch Areas and Programs based on Region (Dependent Logic & Data > 0)
    where_sql, params = get_list_filter_clause("g.region_name", region_name)
    
    areas_query = f"""
        SELECT DISTINCT g.area_name AS area 
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        INNER JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        WHERE g.area_name IS NOT NULL AND {where_sql}
    """
    
    prog_query = f"""
        SELECT DISTINCT p.program_name 
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        INNER JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON p.sk_program_id = f.sk_program_id
        INNER JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        WHERE p.program_name IS NOT NULL AND {where_sql}
    """
    
    areas = [row["area"] for row in fetch_all(areas_query + " ORDER BY area", params)]
    
    # Only show programs if region is selected, and ONLY those with data
    programs = []
    if region_name:
        programs = [row["program_name"] for row in fetch_all(prog_query + " ORDER BY p.program_name", params)]

    years = [row["year_actual"] for row in fetch_all(f"""
        SELECT DISTINCT d.year_actual 
        FROM {DATAMART_SCHEMA_NAME}.dim_date d
        INNER JOIN {DATAMART_SCHEMA_NAME}.fact_session f ON d.date_id = f.date_id
        WHERE d.year_actual IS NOT NULL 
        ORDER BY d.year_actual DESC
    """)]
    
    months = [{"id": row["month_actual"], "name": row["month_name"].strip()} for row in fetch_all(f"""
        SELECT DISTINCT d.month_actual, TO_CHAR(TO_DATE(d.month_actual::text, 'MM'), 'Month') as month_name 
        FROM {DATAMART_SCHEMA_NAME}.dim_date d
        INNER JOIN {DATAMART_SCHEMA_NAME}.fact_session f ON d.date_id = f.date_id
        ORDER BY d.month_actual
    """)]
    
    return {
        "regions": regions,
        "areas": areas,
        "programs": programs,
        "years": years,
        "months": months,
        "quarters": [1, 2, 3, 4]
    }


def get_school_visit_data(region=None, area=None, program=None, years=None, month=None, quarter=None, limit=15, offset=0, dt_params=None, group_by="month"):
    from backend.services.query_utils import build_standard_filters, calculate_ytd_kpis, get_datatables_sql, get_time_grouping_expressions

    kpi_defs = [
        {"key": "total_schools", "label": "Total Schools", "sql": "COUNT(DISTINCT f.sk_school_id)", "icon": "fas fa-school", "color": "bg-info"},
        {"key": "total_students", "label": "Total Students", "sql": "COALESCE(SUM(e.total_exposure_count), 0)", "icon": "fas fa-user-graduate", "color": "bg-success"},
        {"key": "total_sessions", "label": "Total Sessions", "sql": "COUNT(DISTINCT f.sk_fact_session_id)", "icon": "fas fa-chalkboard-teacher", "color": "bg-navy-blue"},
        {"key": "total_days", "label": "Total Days Worked", "sql": "COUNT(DISTINCT f.date_id)", "icon": "fas fa-calendar-alt", "color": "bg-danger"}
    ]
    
    from_clause = f"""
        {DATAMART_SCHEMA_NAME}.fact_session f
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
    """
    
    kpi_list, sparklines = calculate_ytd_kpis(
        kpi_defs=kpi_defs,
        from_clause=from_clause,
        years=years,
        region=region,
        area=area,
        program=program,
        month=month,
        quarter=quarter
    )
    
    where_sql, params, max_month = build_standard_filters(
        years=years,
        region=region,
        area=area,
        program=program,
        month=month,
        quarter=quarter
    )

    # DataTable Logic
    search_sql = "TRUE"
    search_params = []
    sort_sql = "ORDER BY region_name, area_name, program_name, school_name"
    
    if dt_params:
        searchable_cols = ["s.school_name", "p.program_name", "g.region_name", "g.area_name"]
        sortable_cols = ["region_name", "area_name", "program_name", "school_name", "students_reached"]
        
        inner_search_sql, inner_search_params, inner_sort_sql = get_datatables_sql(dt_params, searchable_cols, sortable_cols)
        search_sql = inner_search_sql
        search_params = inner_search_params
        if inner_sort_sql:
            sort_sql = inner_sort_sql

    # Get total row count for pagination
    count_sql = f"""
        SELECT COUNT(*) FROM (
            SELECT s.school_name
            FROM {DATAMART_SCHEMA_NAME}.fact_session f
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_school s ON f.sk_school_id = s.sk_school_id
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
            LEFT JOIN {DATAMART_SCHEMA_NAME}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {where_sql} AND {search_sql}
            GROUP BY g.region_name, g.area_name, p.program_name, s.school_name
        ) as sub
    """
    total_count = fetch_one(count_sql, params + search_params).get("count", 0)

    # Get paginated data
    sql = f"""
        SELECT 
            COALESCE(g.region_name, 'Unknown') as region_name,
            COALESCE(g.area_name, 'Unknown') as area_name,
            COALESCE(p.program_name, 'Unknown') as program_name,
            COALESCE(s.school_name, 'Unknown') as school_name,
            SUM(COALESCE(e.total_exposure_count, 0)) as students_reached
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_school s ON f.sk_school_id = s.sk_school_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
        WHERE {where_sql} AND {search_sql}
        GROUP BY g.region_name, g.area_name, p.program_name, s.school_name
        {sort_sql}
        LIMIT %s OFFSET %s
    """
    rows = fetch_all(sql, params + search_params + [limit, offset])

    # School Visit Summary (grouped by school)
    school_summary = fetch_all(f"""
        SELECT
            COALESCE(g.region_name, 'Unknown') AS region,
            COALESCE(g.area_name, 'Unknown') AS area,
            COALESCE(s.school_name, 'Unknown') AS school_name,
            COALESCE(SUM(e.total_exposure_count), 0) AS total_exposure,
            COUNT(DISTINCT f.sk_fact_session_id) AS sessions,
            COUNT(DISTINCT p.program_name) AS programs
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_school s ON f.sk_school_id = s.sk_school_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
        WHERE {where_sql} AND s.school_name IS NOT NULL
        GROUP BY g.region_name, g.area_name, s.school_name
        ORDER BY total_exposure DESC
    """, params)

    # Chart 1: Sessions by Program (pie chart)
    sessions_by_program = fetch_all(f"""
        SELECT COALESCE(p.program_name, 'Unknown') AS label,
               COUNT(DISTINCT f.sk_fact_session_id) AS value
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        WHERE {where_sql}
        GROUP BY p.program_name ORDER BY value DESC LIMIT 8
    """, params)

    label_expr, sort_expr, grp_expr = get_time_grouping_expressions(group_by)

    # Chart 2: Sessions Trend (dynamic time-series)
    sessions_by_month = fetch_all(f"""
        SELECT {label_expr} AS label,
               COUNT(DISTINCT f.sk_fact_session_id) AS value
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        WHERE {where_sql} AND d.full_date IS NOT NULL
        GROUP BY {label_expr}
        ORDER BY {sort_expr}
    """, params)

    # Chart 3: Top 10 Schools by Exposure
    top_schools = fetch_all(f"""
        SELECT COALESCE(s.school_name, 'Unknown') AS label,
               COALESCE(SUM(e.total_exposure_count), 0) AS value
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_school s ON f.sk_school_id = s.sk_school_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
        WHERE {where_sql} AND s.school_name IS NOT NULL
        GROUP BY s.school_name
        ORDER BY value DESC LIMIT 10
    """, params)

    # Chart 4: Sessions by Area
    sessions_by_area = fetch_all(f"""
        SELECT COALESCE(g.area_name, 'Unknown') AS label,
               COUNT(DISTINCT f.sk_fact_session_id) AS value
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        WHERE {where_sql} AND g.area_name IS NOT NULL
        GROUP BY g.area_name
        ORDER BY value DESC LIMIT 10
    """, params)

    return {
        "table": rows, 
        "total_count": total_count,
        "kpis": kpi_list,
        "sparklines": sparklines,
        "school_summary": school_summary,
        "charts": {
            "sessions_by_program": [{"label": r["label"], "value": float(r["value"])} for r in sessions_by_program],
            "sessions_trend_monthly": [{"label": r["label"], "value": float(r["value"])} for r in sessions_by_month],
            "top_schools": [{"label": r["label"], "value": float(r["value"])} for r in top_schools],
            "sessions_by_area": [{"label": r["label"], "value": float(r["value"])} for r in sessions_by_area],
        }
    }
