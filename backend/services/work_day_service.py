from backend.services.query_utils import fetch_all, fetch_one
from backend.config import DATAMART_SCHEMA_NAME


def get_work_day_filters():
    # INNER JOIN with fact_session to show only locations with data
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


def get_work_day_data(region=None, area=None, years=None, month=None, quarter=None, limit=15, offset=0, dt_params=None):
    from backend.services.query_utils import build_standard_filters, calc_trend, get_kpi_insight, get_datatables_sql
    from backend.config import DEFAULT_YEAR
    
    where_sql, params, max_month = build_standard_filters(
        years=years,
        region=region,
        area=area,
        month=month,
        quarter=quarter
    )
    
    effective_years = years
    if effective_years is None or (isinstance(effective_years, list) and len(effective_years) == 0):
        effective_years = [DEFAULT_YEAR]
    single_year = None
    if len(effective_years) == 1:
        try: single_year = int(effective_years[0])
        except (ValueError, TypeError): pass
    prev_year = single_year - 1 if single_year is not None else None
    
    # Current period KPIs
    kpi_sql = f"""
        SELECT 
            COUNT(DISTINCT f.sk_user_id) as total_instructors,
            COUNT(DISTINCT CONCAT(f.sk_user_id, '_', f.date_id)) as total_working_days,
            COUNT(DISTINCT f.sk_geography_id) as active_centers
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        WHERE {where_sql}
    """
    curr = fetch_one(kpi_sql, params)
    
    # Previous period KPIs
    prev_year_vals = [int(y) - 1 for y in effective_years]
    prev_where_sql, prev_params, _ = build_standard_filters(
        years=prev_year_vals, region=region, area=area, month=month, quarter=quarter
    )
    prev = fetch_one(f"""
        SELECT 
            COUNT(DISTINCT f.sk_user_id) as total_instructors,
            COUNT(DISTINCT CONCAT(f.sk_user_id, '_', f.date_id)) as total_working_days,
            COUNT(DISTINCT f.sk_geography_id) as active_centers
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        WHERE {prev_where_sql}
    """, prev_params)
    
    c_inst = int(curr.get('total_instructors', 0) or 0)
    p_inst = int(prev.get('total_instructors', 0) or 0)
    c_days = int(curr.get('total_working_days', 0) or 0)
    p_days = int(prev.get('total_working_days', 0) or 0)
    c_avg = round(c_days / c_inst, 2) if c_inst > 0 else 0
    p_avg = round(p_days / p_inst, 2) if p_inst > 0 else 0
    c_centers = int(curr.get('active_centers', 0) or 0)
    p_centers = int(prev.get('active_centers', 0) or 0)
    
    kpis_data = [
        {"label": "Total Instructors", "curr": c_inst, "prev": p_inst, "icon": "fas fa-users", "color": "bg-info"},
        {"label": "Total Working Days", "curr": c_days, "prev": p_days, "icon": "fas fa-calendar-check", "color": "bg-success"},
        {"label": "Avg Days/Instructor", "curr": c_avg, "prev": p_avg, "icon": "fas fa-chart-line", "color": "bg-navy-blue"},
        {"label": "Active Centers", "curr": c_centers, "prev": p_centers, "icon": "fas fa-map-marker-alt", "color": "bg-danger"}
    ]
    
    kpi_list = []
    sparklines = {}
    for item in kpis_data:
        trend = calc_trend(item["curr"], item["prev"])
        insights = get_kpi_insight(item["label"], float(item["curr"]), float(item["prev"]), single_year, prev_year, max_month, month, quarter)
        kpi_list.append({
            "label": item["label"], "value": item["curr"], "icon": item["icon"], "color": item["color"],
            "trend": trend, "insights": insights, "trends": [item["prev"], item["curr"]]
        })
        sparklines[item["label"].lower().replace(" ", "_")] = [item["prev"], item["curr"]]

    # 2. DataTable Logic
    search_sql = "TRUE"
    search_params = []
    sort_sql = "ORDER BY days_worked DESC, instructor_name ASC"
    
    if dt_params:
        searchable_cols = ["u.user_name", "g.region_name", "g.area_name"]
        sortable_cols = ["instructor_name", "region", "area", "days_worked"]
        
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
            COUNT(DISTINCT d.full_date) as days_worked,
            STRING_AGG(DISTINCT TO_CHAR(d.full_date, 'DD'), ', ' ORDER BY TO_CHAR(d.full_date, 'DD')) as dates_active
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
    
    return {
        "kpis": kpi_list,
        "sparklines": sparklines,
        "table": rows, 
        "total_count": total_count
    }
