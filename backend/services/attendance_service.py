from backend.services.query_utils import fetch_all, fetch_one
from backend.config import DATAMART_SCHEMA_NAME


def get_attendance_filters():
    locations = fetch_all(f"""
        SELECT DISTINCT g.region_name, g.area_name AS area 
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        WHERE g.region_name IS NOT NULL 
        ORDER BY g.region_name, g.area_name
    """)
    
    years = [row["year_actual"] for row in fetch_all(f"""
        SELECT DISTINCT d.year_actual 
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        WHERE d.year_actual IS NOT NULL 
        ORDER BY d.year_actual DESC
    """)]
    
    months = [{"id": row["month_actual"], "name": row["month_name"].strip()} for row in fetch_all(f"""
        SELECT DISTINCT d.month_actual, TO_CHAR(TO_DATE(d.month_actual::text, 'MM'), 'Month') as month_name 
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        ORDER BY d.month_actual
    """)]
    
    return {
        "regions": sorted(list(set(row["region_name"] for row in locations))),
        "areas": sorted(list(set(row["area"] for row in locations if row.get("area")))),
        "years": years,
        "months": months
    }


def get_attendance_data(region=None, area=None, year=None, month=None, limit=15, offset=0, dt_params=None):
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
    
    # 1. KPI Query (remains mostly same, limited by sidebar filters only)
    kpi_sql = f"""
        SELECT 
            COUNT(DISTINCT f.sk_user_id) as total_staff,
            COUNT(f.sk_fact_session_id) as total_sessions,
            COUNT(DISTINCT CONCAT(f.sk_user_id, '_', f.date_id)) as total_days_present
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        WHERE {where_sql}
    """
    kpis_raw = fetch_one(kpi_sql, params)
    
    staff = kpis_raw.get('total_staff', 0)
    sessions = kpis_raw.get('total_sessions', 0)
    days_present = kpis_raw.get('total_days_present', 0)
    avg_sessions = round(sessions / days_present, 2) if days_present > 0 else 0

    kpi_list = [
        {"label": "Total Field Staff", "value": staff, "icon": "fas fa-users-cog", "color": "bg-info"},
        {"label": "Cumulative Days Present", "value": days_present, "icon": "fas fa-calendar-check", "color": "bg-success"},
        {"label": "Total Sessions Conducted", "value": sessions, "icon": "fas fa-chalkboard-teacher", "color": "bg-navy-blue"},
        {"label": "Avg Sessions / Day", "value": avg_sessions, "icon": "fas fa-chart-line", "color": "bg-danger"}
    ]

    # 2. DataTable Logic
    search_sql = "TRUE"
    search_params = []
    sort_sql = "ORDER BY days_present DESC, instructor_name ASC"
    
    if dt_params:
        # Define searchable and sortable columns (must match the SELECT aliases)
        searchable_cols = ["u.user_name", "g.region_name", "g.area_name"]
        sortable_cols = ["u.user_name", "g.region_name", "g.area_name", "days_present", "total_sessions"]
        
        # We need a subquery or HAVING to search/sort by aggregates if we want to be fancy,
        # but for now let's use a subquery for the full joined set.
        inner_search_sql, inner_search_params, inner_sort_sql = get_datatables_sql(dt_params, searchable_cols, sortable_cols)
        search_sql = inner_search_sql
        search_params = inner_search_params
        if inner_sort_sql:
            sort_sql = inner_sort_sql

    # Get total count (Filtered by sidebar AND table search)
    count_sql = f"""
        SELECT COUNT(*) FROM (
            SELECT u.user_name
            FROM {DATAMART_SCHEMA_NAME}.fact_session f
            JOIN {DATAMART_SCHEMA_NAME}.dim_user u ON f.sk_user_id = u.sk_user_id
            JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
            JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            WHERE {where_sql} AND {search_sql}
            GROUP BY u.user_name, g.region_name, g.area_name
        ) as sub
    """
    total_count_row = fetch_one(count_sql, params + search_params)
    total_count = total_count_row.get("count", 0) if total_count_row else 0

    # Get paginated data
    sql = f"""
        SELECT 
            u.user_name as instructor_name,
            g.region_name as region,
            COALESCE(g.area_name, 'N/A') as area,
            COUNT(DISTINCT d.full_date) as days_present,
            COUNT(f.sk_fact_session_id) as total_sessions
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        JOIN {DATAMART_SCHEMA_NAME}.dim_user u ON f.sk_user_id = u.sk_user_id
        JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        WHERE {where_sql} AND {search_sql}
        GROUP BY u.user_name, g.region_name, g.area_name
        {sort_sql}
        LIMIT %s OFFSET %s
    """
    rows = fetch_all(sql, params + search_params + [limit, offset])

    # 3. Chart Logic (Trend Chart)
    # If a specific month is selected, show days in month. Else, show months in year.
    period_col = "d.full_date" if month else "d.month_actual"
    period_alias = "period_val"

    trend_rows = fetch_all(f"""
        SELECT 
            {period_col} as {period_alias}, 
            COUNT(f.sk_fact_session_id) as metric
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        WHERE {where_sql}
        GROUP BY {period_col}
        ORDER BY {period_col} ASC
    """, params)

    trend_labels = []
    trend_data = []
    import calendar
    for r in trend_rows:
        val = r[period_alias]
        if not month:
            val = calendar.month_abbr[int(val)] if val else "Unknown"
        else:
            val = str(val)  # Date string
        trend_labels.append(val)
        trend_data.append(int(r["metric"]))

    # 4. Chart Logic (Region Chart)
    region_rows = fetch_all(f"""
        SELECT 
            COALESCE(g.region_name, 'Unknown') as region_name, 
            COUNT(f.sk_fact_session_id) as metric
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        WHERE {where_sql}
        GROUP BY g.region_name
        ORDER BY metric DESC
    """, params)

    region_labels = []
    region_data = []
    for r in region_rows:
        region_labels.append(r["region_name"])
        region_data.append(int(r["metric"]))

    return {
        "kpis": kpi_list,
        "table": rows, 
        "total_count": total_count,
        "charts": {
            "trend": {"labels": trend_labels, "data": trend_data},
            "region": {"labels": region_labels, "data": region_data}
        }
    }


