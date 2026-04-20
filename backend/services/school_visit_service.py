from backend.services.query_utils import fetch_all, fetch_one
from backend.config import DATAMART_SCHEMA_NAME


def get_school_visit_filters(region_name: str | None = None):
    # 1. Fetch all Regions always
    region_query = f"SELECT DISTINCT region_name FROM {DATAMART_SCHEMA_NAME}.dim_geography WHERE region_name IS NOT NULL ORDER BY region_name"
    regions = [row["region_name"] for row in fetch_all(region_query)]
    
    # 2. Fetch Areas and Programs based on Region (Dependent Logic & Data > 0)
    # Both Area and Program should now ONLY show if they have data in fact_session
    areas_query = f"""
        SELECT DISTINCT g.area_name AS area 
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        INNER JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        WHERE g.area_name IS NOT NULL
    """
    
    prog_query = f"""
        SELECT DISTINCT p.program_name 
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        INNER JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON p.sk_program_id = f.sk_program_id
        INNER JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        WHERE p.program_name IS NOT NULL
    """
    
    params = []
    if region_name and region_name != "Select Region":
        areas_query += " AND g.region_name = %s"
        prog_query += " AND g.region_name = %s"
        params.append(region_name)
    
    areas = [row["area"] for row in fetch_all(areas_query + " ORDER BY area", params)]
    
    # Only show programs if region is selected, and ONLY those with data
    programs = []
    if region_name and region_name != "Select Region":
        programs = [row["program_name"] for row in fetch_all(prog_query + " ORDER BY p.program_name", params)]

    years = [row["year_actual"] for row in fetch_all(f"SELECT DISTINCT year_actual FROM {DATAMART_SCHEMA_NAME}.dim_date WHERE year_actual IS NOT NULL ORDER BY year_actual DESC")]
    
    months = [{"id": row["month_actual"], "name": row["month_name"].strip()} for row in fetch_all(f"SELECT DISTINCT month_actual, TO_CHAR(TO_DATE(month_actual::text, 'MM'), 'Month') as month_name FROM {DATAMART_SCHEMA_NAME}.dim_date ORDER BY month_actual")]
    
    return {
        "regions": regions,
        "areas": areas,
        "programs": programs,
        "years": years,
        "months": months
    }


def get_school_visit_data(region=None, area=None, program=None, year=None, month=None, limit=15, offset=0, dt_params=None):
    from backend.services.query_utils import parse_datatables_params, get_datatables_sql

    where_clauses = ["TRUE"]
    params = []
    
    if region:
        where_clauses.append("g.region_name = %s")
        params.append(region)
    if area:
        where_clauses.append("g.area_name = %s")
        params.append(area)
    if program:
        where_clauses.append("p.program_name = %s")
        params.append(program)
    if year:
        where_clauses.append("d.year_actual = %s")
        params.append(int(year))
    if month:
        where_clauses.append("d.month_actual = %s")
        params.append(int(month))
    
    where_sql = " AND ".join(where_clauses)
    
    # Get KPIs (Using sidebar filters only)
    kpi_sql = f"""
        SELECT 
            COUNT(DISTINCT f.sk_school_id) as total_schools,
            COUNT(f.sk_fact_session_id) as total_sessions,
            SUM(COALESCE(e.total_exposure_count, 0)) as total_students
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
        WHERE {where_sql}
    """
    kpi_res = fetch_one(kpi_sql, params)

    # Monthly Sessions
    monthly_sql = f"""
        SELECT COUNT(f.sk_fact_session_id) as monthly_sessions
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
        WHERE {where_sql}
        AND d.month_actual = (
            SELECT MAX(d2.month_actual) 
            FROM {DATAMART_SCHEMA_NAME}.fact_session f2
            JOIN {DATAMART_SCHEMA_NAME}.dim_date d2 ON f2.date_id = d2.date_id
            JOIN {DATAMART_SCHEMA_NAME}.dim_geography g2 ON f2.sk_geography_id = g2.sk_geography_id
            JOIN {DATAMART_SCHEMA_NAME}.dim_program p2 ON f2.sk_program_id = p2.sk_program_id
            WHERE {where_sql}
        )
    """
    monthly_res = fetch_one(monthly_sql, params + params)

    kpis = {
        "total_schools": kpi_res.get("total_schools") or 0,
        "total_students": int(kpi_res.get("total_students") or 0),
        "total_sessions": int(kpi_res.get("total_sessions") or 0),
        "monthly_sessions": int(monthly_res.get("monthly_sessions") or 0) if monthly_res else 0
    }

    # DataTable Logic
    search_sql = "TRUE"
    search_params = []
    sort_sql = "ORDER BY school_name, program_name, class_name, section_name"
    
    if dt_params:
        searchable_cols = ["s.school_name", "p.program_name", "e.class_name", "e.section_name"]
        sortable_cols = ["school_name", "program_name", "class_name", "section_name", "sessions", "exposures"]
        
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
            INNER JOIN {DATAMART_SCHEMA_NAME}.dim_school s ON f.sk_school_id = s.sk_school_id
            INNER JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
            INNER JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            INNER JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
            INNER JOIN {DATAMART_SCHEMA_NAME}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {where_sql} AND {search_sql}
            GROUP BY s.school_name, p.program_name, e.class_name, e.section_name
        ) as sub
    """
    total_count = fetch_one(count_sql, params + search_params).get("count", 0)

    # Get paginated data
    sql = f"""
        SELECT 
            COALESCE(s.school_name, 'Unknown') as school_name,
            COALESCE(p.program_name, 'Unknown') as program_name,
            COALESCE(e.class_name, 'N/A') as class_name,
            COALESCE(e.section_name, 'N/A') as section_name,
            COUNT(DISTINCT f.session_nk_id) as sessions,
            SUM(COALESCE(e.total_exposure_count, 0)) as exposures
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        INNER JOIN {DATAMART_SCHEMA_NAME}.dim_school s ON f.sk_school_id = s.sk_school_id
        INNER JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
        INNER JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        INNER JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        INNER JOIN {DATAMART_SCHEMA_NAME}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
        WHERE {where_sql} AND {search_sql}
        GROUP BY s.school_name, p.program_name, e.class_name, e.section_name
        {sort_sql}
        LIMIT %s OFFSET %s
    """
    rows = fetch_all(sql, params + search_params + [limit, offset])
    
    return {
        "table": rows, 
        "total_count": total_count,
        "kpis": kpis
    }




