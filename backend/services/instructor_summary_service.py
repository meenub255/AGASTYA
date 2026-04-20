from backend.services.query_utils import fetch_all, fetch_one
from backend.config import DATAMART_SCHEMA_NAME


def get_instructor_summary_filters():
    # Fetch from new dim_geography joined with fact_session to show only locations with data
    locations_query = f"""
        SELECT DISTINCT g.region_name, g.area_name AS area 
        FROM {DATAMART_SCHEMA_NAME}.dim_geography g
        INNER JOIN {DATAMART_SCHEMA_NAME}.fact_session f ON g.sk_geography_id = f.sk_geography_id
        WHERE g.region_name IS NOT NULL 
        ORDER BY g.region_name, g.area_name
    """
    locations = fetch_all(locations_query)
    
    years = [row["year_actual"] for row in fetch_all(f"SELECT DISTINCT year_actual FROM {DATAMART_SCHEMA_NAME}.dim_date WHERE year_actual IS NOT NULL ORDER BY year_actual DESC")]
    
    months = [{"id": row["month_actual"], "name": row["month_name"].strip()} for row in fetch_all(f"SELECT DISTINCT month_actual, TO_CHAR(TO_DATE(month_actual::text, 'MM'), 'Month') as month_name FROM {DATAMART_SCHEMA_NAME}.dim_date ORDER BY month_actual")]
    
    return {
        "regions": sorted(list(set(row["region_name"] for row in locations))),
        "areas": sorted(list(set(row["area"] for row in locations if row.get("area")))),
        "years": years,
        "months": months
    }


def get_instructor_summary_data(region=None, area=None, year=None, month=None, limit=15, offset=0, dt_params=None):
    from backend.services.query_utils import parse_datatables_params, get_datatables_sql

    where_clauses = ["TRUE"]
    params = []
    
    if region:
        where_clauses.append("g.region_name = %s")
        params.append(region)
    if area:
        where_clauses.append("g.area_name = %s")
        params.append(area)
    if year:
        where_clauses.append("d.year_actual = %s")
        params.append(int(year))
    if month:
        where_clauses.append("d.month_actual = %s")
        params.append(int(month))
    
    where_sql = " AND ".join(where_clauses)
    
    # Get KPIs (limited by sidebar filters only)
    kpi_sql = f"""
        SELECT 
            COUNT(DISTINCT d.full_date) as days_worked,
            COUNT(f.sk_fact_session_id) as total_sessions,
            SUM(COALESCE(e.total_exposure_count, 0)) as total_exposures,
            SUM(CASE WHEN a.activity_name ILIKE ANY (ARRAY['%%YIL%%', '%%SF%%', '%%CV%%']) THEN COALESCE(e.total_exposure_count, 0) ELSE 0 END) as combined_exposures
        FROM {DATAMART_SCHEMA_NAME}.dim_user u
        LEFT JOIN {DATAMART_SCHEMA_NAME}.fact_session f ON u.sk_user_id = f.sk_user_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_activity_type a ON f.sk_activity_type_id = a.sk_activity_type_id
        WHERE {where_sql}
    """
    kpi_res = fetch_one(kpi_sql, params)
    
    total_exp = int(kpi_res["total_exposures"] or 0)
    comb_exp = int(kpi_res["combined_exposures"] or 0)
    
    kpis = {
        "days_worked": kpi_res["days_worked"] or 0,
        "total_sessions": int(kpi_res["total_sessions"] or 0),
        "school_exposures": total_exp - comb_exp,
        "combined_exposures": comb_exp
    }

    # DataTable Logic
    search_sql = "TRUE"
    search_params = []
    sort_sql = "ORDER BY instructor_name ASC"
    
    if dt_params:
        searchable_cols = ["u.user_name"]
        sortable_cols = ["instructor_name", "days_worked", "school_sessions", "total_sessions", "total_exposures", "fair_count", "training_exposures", "sf_exposures", "yil_sessions", "yil_exposures", "cv_visits", "cv_exposures"]
        
        inner_search_sql, inner_search_params, inner_sort_sql = get_datatables_sql(dt_params, searchable_cols, sortable_cols)
        search_sql = inner_search_sql
        search_params = inner_search_params
        if inner_sort_sql:
            sort_sql = inner_sort_sql

    # Get total count for pagination
    count_sql = f"""
        SELECT COUNT(*) FROM (
            SELECT u.sk_user_id
            FROM {DATAMART_SCHEMA_NAME}.dim_user u
            JOIN {DATAMART_SCHEMA_NAME}.fact_session f ON u.sk_user_id = f.sk_user_id
            JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
            WHERE {where_sql} AND {search_sql}
            GROUP BY u.sk_user_id
        ) as sub
    """
    total_count = fetch_one(count_sql, params + search_params).get("count", 0)

    # Main query to aggregate instructor metrics
    main_sql = f"""
        SELECT 
            u.user_name as instructor_name,
            COUNT(DISTINCT d.full_date) as days_worked,
            COUNT(DISTINCT f.sk_fact_session_id) as school_sessions,
            COUNT(f.sk_fact_session_id) as total_sessions,
            SUM(COALESCE(e.total_exposure_count, 0)) as total_exposures,
            COUNT(DISTINCT CASE WHEN a.activity_name ILIKE '%%Fair%%' THEN f.sk_fact_session_id END) as fair_count,
            SUM(CASE WHEN a.activity_name ILIKE '%%Training%%' THEN COALESCE(e.total_exposure_count, 0) ELSE 0 END) as training_exposures,
            SUM(CASE WHEN a.activity_name ILIKE '%%SF%%' THEN COALESCE(e.total_exposure_count, 0) ELSE 0 END) as sf_exposures,
            COUNT(DISTINCT CASE WHEN a.activity_name ILIKE '%%YIL%%' THEN f.sk_fact_session_id END) as yil_sessions,
            SUM(CASE WHEN a.activity_name ILIKE '%%YIL%%' THEN COALESCE(e.total_exposure_count, 0) ELSE 0 END) as yil_exposures,
            COUNT(DISTINCT CASE WHEN a.activity_name ILIKE '%%CV%%' THEN f.sk_fact_session_id END) as cv_visits,
            SUM(CASE WHEN a.activity_name ILIKE '%%CV%%' THEN COALESCE(e.total_exposure_count, 0) ELSE 0 END) as cv_exposures
        FROM {DATAMART_SCHEMA_NAME}.dim_user u
        LEFT JOIN {DATAMART_SCHEMA_NAME}.fact_session f ON u.sk_user_id = f.sk_user_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_activity_type a ON f.sk_activity_type_id = a.sk_activity_type_id
        WHERE {where_sql} AND {search_sql}
        GROUP BY u.sk_user_id, u.user_name
        {sort_sql}
        LIMIT %s OFFSET %s
    """
    table_data = fetch_all(main_sql, params + search_params + [limit, offset])
    
    return {
        "table": table_data,
        "total_count": total_count,
        "kpis": kpis
    }


