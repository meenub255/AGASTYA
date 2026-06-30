from backend.services.query_utils import fetch_all, fetch_one
from backend.config import DATAMART_SCHEMA_NAME


def get_arealead_summary_filters():
    locations_query = f"""
        SELECT DISTINCT g.region_name, g.area_name AS area 
        FROM {DATAMART_SCHEMA_NAME}.dim_geography g
        INNER JOIN {DATAMART_SCHEMA_NAME}.fact_session f ON g.sk_geography_id = f.sk_geography_id
        WHERE g.region_name IS NOT NULL 
        ORDER BY g.region_name, g.area_name
    """
    locations = fetch_all(locations_query)
    
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
        "regions": sorted(list(set(row["region_name"] for row in locations))),
        "areas": sorted(list(set(row["area"] for row in locations if row.get("area")))),
        "years": years,
        "months": months,
        "quarters": [1, 2, 3, 4]
    }


def get_arealead_summary_data(region=None, area=None, years=None, month=None, quarter=None, limit=15, offset=0, dt_params=None):
    from backend.services.query_utils import build_standard_filters, calculate_ytd_kpis, get_datatables_sql
    
    kpi_defs = [
        {"key": "total_leads", "label": "Area Leads", "sql": "COUNT(DISTINCT g.area_name)", "icon": "fas fa-user-tie", "color": "bg-info"},
        {"key": "total_instructors", "label": "Ignators", "sql": "COUNT(DISTINCT u.sk_user_id)", "icon": "fas fa-chalkboard-teacher", "color": "bg-success"},
        {"key": "total_sessions", "label": "Sessions", "sql": "COUNT(DISTINCT f.sk_fact_session_id)", "icon": "fas fa-layer-group", "color": "bg-navy-blue"},
        {"key": "total_students", "label": "Total Exposures", "sql": "SUM(COALESCE(e.total_exposure_count, 0))", "icon": "fas fa-user-graduate", "color": "bg-danger"}
    ]
    
    from_clause = f"""
        {DATAMART_SCHEMA_NAME}.fact_session f
        JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        JOIN {DATAMART_SCHEMA_NAME}.dim_user u ON f.sk_user_id = u.sk_user_id
        JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
    """
    
    kpi_list, sparklines = calculate_ytd_kpis(
        kpi_defs=kpi_defs,
        from_clause=from_clause,
        years=years,
        region=region,
        area=area,
        month=month,
        quarter=quarter
    )
    
    where_sql, params, max_month = build_standard_filters(
        years=years,
        region=region,
        area=area,
        month=month,
        quarter=quarter
    )

    search_sql = "TRUE"
    search_params = []
    sort_sql = "ORDER BY total_exposures DESC"
    
    if dt_params:
        searchable_cols = ["g.area_name", "g.region_name"]
        sortable_cols = ["area", "region", "total_exposures", "total_sessions", "exp_per_pgm", "expo_per_ignator", "expo_per_session", "no_of_pgm", "no_of_ign", "work_days"]
        
        inner_search_sql, inner_search_params, inner_sort_sql = get_datatables_sql(dt_params, searchable_cols, sortable_cols)
        search_sql = inner_search_sql
        search_params = inner_search_params
        if inner_sort_sql:
            sort_sql = inner_sort_sql

    count_sql = f"""
        SELECT COUNT(*) FROM (
            SELECT g.area_name
            FROM {DATAMART_SCHEMA_NAME}.fact_session f
            JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            JOIN {DATAMART_SCHEMA_NAME}.dim_user u ON f.sk_user_id = u.sk_user_id
            JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
            WHERE {where_sql} AND {search_sql}
            GROUP BY g.area_name, g.region_name
        ) as sub
    """
    total_count_row = fetch_one(count_sql, params + search_params)
    total_count = total_count_row.get("count", 0) if total_count_row else 0

    sql = f"""
        SELECT 
            g.area_name as area,
            g.region_name as region,
            SUM(COALESCE(e.total_exposure_count, 0)) as total_exposures,
            COUNT(DISTINCT f.sk_fact_session_id) as total_sessions,
            CASE WHEN COUNT(DISTINCT p.nk_program_id) = 0 THEN 0 
                 ELSE ROUND(SUM(COALESCE(e.total_exposure_count, 0))::numeric / COUNT(DISTINCT p.nk_program_id), 0) 
            END as exp_per_pgm,
            CASE WHEN COUNT(DISTINCT u.sk_user_id) = 0 THEN 0 
                 ELSE ROUND(SUM(COALESCE(e.total_exposure_count, 0))::numeric / COUNT(DISTINCT u.sk_user_id), 0) 
            END as expo_per_ignator,
            CASE WHEN COUNT(DISTINCT f.sk_fact_session_id) = 0 THEN 0 
                 ELSE ROUND(SUM(COALESCE(e.total_exposure_count, 0))::numeric / COUNT(DISTINCT f.sk_fact_session_id), 0) 
            END as expo_per_session,
            COUNT(DISTINCT p.nk_program_id) as no_of_pgm,
            COUNT(DISTINCT u.sk_user_id) as no_of_ign,
            COUNT(DISTINCT d.date_id) as work_days
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        JOIN {DATAMART_SCHEMA_NAME}.dim_user u ON f.sk_user_id = u.sk_user_id
        JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
        WHERE {where_sql} AND {search_sql}
        GROUP BY g.area_name, g.region_name
        {sort_sql}
        LIMIT %s OFFSET %s
    """
    rows = fetch_all(sql, params + search_params + [limit, offset])
    
    return {
        "kpis": kpi_list,
        "sparklines": sparklines,
        "table": rows, 
        "total_count": total_count
    }
