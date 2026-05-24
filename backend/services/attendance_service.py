from backend.services.query_utils import fetch_all, fetch_one
from backend.config import DATAMART_SCHEMA_NAME


def get_attendance_filters():
    locations = fetch_all(f"""
        SELECT DISTINCT g.region_name, g.area_name AS area 
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        WHERE g.region_name IS NOT NULL 
        ORDER BY g.region_name, g.area_name
    """)
    
    years = [row["year_actual"] for row in fetch_all(f"""
        SELECT DISTINCT d.year_actual 
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        WHERE d.year_actual IS NOT NULL 
        ORDER BY d.year_actual DESC
    """)]
    
    months = [{"id": row["month_actual"], "name": row["month_name"].strip()} for row in fetch_all(f"""
        SELECT DISTINCT d.month_actual, TO_CHAR(TO_DATE(d.month_actual::text, 'MM'), 'Month') as month_name 
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        ORDER BY d.month_actual
    """)]
    
    return {
        "regions": sorted(list(set(row["region_name"] for row in locations))),
        "areas": sorted(list(set(row["area"] for row in locations if row.get("area")))),
        "years": years,
        "months": months
    }


def get_attendance_data(region=None, area=None, years=None, month=None, quarter=None, limit=15, offset=0, dt_params=None):
    from backend.services.query_utils import build_standard_filters, calculate_ytd_kpis, get_datatables_sql
    
    kpi_defs = [
        {"key": "total_staff", "label": "Total Field Staff", "sql": "COUNT(DISTINCT f.sk_user_id)", "icon": "fas fa-users-cog", "color": "linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%)"},
        {"key": "total_days_present", "label": "Cumulative Days Present", "sql": "COUNT(DISTINCT CONCAT(f.sk_user_id, '_', f.date_id))", "icon": "fas fa-calendar-check", "color": "linear-gradient(135deg, #22c55e 0%, #16a34a 100%)"},
        {"key": "total_sessions", "label": "Total Sessions Conducted", "sql": "COUNT(f.sk_fact_session_id)", "icon": "fas fa-chalkboard-teacher", "color": "linear-gradient(135deg, #001f3f 0%, #001226 100%)"},
        {"key": "avg_sessions", "label": "Avg Sessions / Day", "sql": "COUNT(f.sk_fact_session_id)::float / NULLIF(COUNT(DISTINCT CONCAT(f.sk_user_id, '_', f.date_id)), 0)", "icon": "fas fa-chart-line", "color": "linear-gradient(135deg, #e74c3c 0%, #c0392b 100%)"}
    ]
    
    from_clause = f"""
        {DATAMART_SCHEMA_NAME}.fact_session f
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
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

    # 2. DataTable Logic
    search_sql = "TRUE"
    search_params = []
    sort_sql = "ORDER BY days_present DESC, instructor_name ASC"
    
    if dt_params:
        # Define searchable and sortable columns (must match the SELECT aliases)
        searchable_cols = ["u.user_name", "g.region_name", "g.area_name"]
        sortable_cols = ["instructor_name", "region", "area", "days_present", "total_sessions"]
        
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
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_user u ON f.sk_user_id = u.sk_user_id
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
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
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_user u ON f.sk_user_id = u.sk_user_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
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
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
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
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
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
        "sparklines": sparklines,
        "table": rows, 
        "total_count": total_count,
        "charts": {
            "trend": {"labels": trend_labels, "data": trend_data},
            "region": {"labels": region_labels, "data": region_data}
        }
    }


