from backend.services.query_utils import fetch_all, fetch_one
from backend.config import DATAMART_SCHEMA_NAME


def get_arealead_summary_filters():
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


def get_arealead_summary_data(region=None, area=None, year=None, month=None, limit=15, offset=0, dt_params=None):
    from backend.services.query_utils import parse_datatables_params, get_datatables_sql, get_list_filter_clause
    clauses = []
    params = []
    
    c, p = get_list_filter_clause("g.region_name", region)
    clauses.append(c); params.extend(p)
    
    c, p = get_list_filter_clause("g.area_name", area)
    clauses.append(c); params.extend(p)
    
    c, p = get_list_filter_clause("d.year_actual", year, cast_type="int")
    clauses.append(c); params.extend(p)
    
    c, p = get_list_filter_clause("d.month_actual", month, cast_type="int")
    clauses.append(c); params.extend(p)
    
    where_sql = " AND ".join(clauses)
    
    # 1. KPI Query (sidebar filters only)
    kpi_sql = f"""
        SELECT 
            COUNT(DISTINCT g.area_name) as total_leads,
            COUNT(DISTINCT u.sk_user_id) as total_instructors,
            COUNT(DISTINCT f.sk_fact_session_id) as total_sessions,
            SUM(COALESCE(e.total_exposure_count, 0)) as total_students
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        JOIN {DATAMART_SCHEMA_NAME}.dim_user u ON f.sk_user_id = u.sk_user_id
        JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
        WHERE {where_sql}
    """
    kpis_raw = fetch_one(kpi_sql, params)
    
    kpi_list = [
        {"label": "Total Area Leads", "value": kpis_raw.get('total_leads', 0), "icon": "fas fa-user-tie", "color": "bg-info"},
        {"label": "Total Instructors", "value": kpis_raw.get('total_instructors', 0), "icon": "fas fa-chalkboard-teacher", "color": "bg-success"},
        {"label": "Total Sessions", "value": kpis_raw.get('total_sessions', 0), "icon": "fas fa-layer-group", "color": "bg-navy-blue"},
        {"label": "Total Students Impacted", "value": kpis_raw.get('total_students', 0), "icon": "fas fa-user-graduate", "color": "bg-danger"}
    ]

    # 2. DataTable Logic
    search_sql = "TRUE"
    search_params = []
    sort_sql = "ORDER BY g.region_name, g.area_name"
    
    if dt_params:
        searchable_cols = ["g.area_name", "g.region_name"]
        sortable_cols = ["area", "region", "total_instructors", "total_sessions", "total_students"]
        
        inner_search_sql, inner_search_params, inner_sort_sql = get_datatables_sql(dt_params, searchable_cols, sortable_cols)
        search_sql = inner_search_sql
        search_params = inner_search_params
        if inner_sort_sql:
            sort_sql = inner_sort_sql

    # Get total count (Filtered by sidebar AND table search)
    count_sql = f"""
        SELECT COUNT(*) FROM (
            SELECT g.area_name
            FROM {DATAMART_SCHEMA_NAME}.fact_session f
            JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            JOIN {DATAMART_SCHEMA_NAME}.dim_user u ON f.sk_user_id = u.sk_user_id
            JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
            WHERE {where_sql} AND {search_sql}
            GROUP BY g.area_name, g.region_name
        ) as sub
    """
    total_count_row = fetch_one(count_sql, params + search_params)
    total_count = total_count_row.get("count", 0) if total_count_row else 0

    # Get paginated data
    sql = f"""
        SELECT 
            g.area_name as area,
            g.region_name as region,
            COUNT(DISTINCT u.sk_user_id) as total_instructors,
            COUNT(DISTINCT f.sk_fact_session_id) as total_sessions,
            SUM(COALESCE(e.total_exposure_count, 0)) as total_students
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        JOIN {DATAMART_SCHEMA_NAME}.dim_user u ON f.sk_user_id = u.sk_user_id
        JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
        WHERE {where_sql} AND {search_sql}
        GROUP BY g.area_name, g.region_name
        {sort_sql}
        LIMIT %s OFFSET %s
    """
    rows = fetch_all(sql, params + search_params + [limit, offset])
    
    return {
        "kpis": kpi_list,
        "table": rows, 
        "total_count": total_count
    }
