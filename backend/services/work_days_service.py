from backend.services.query_utils import fetch_all, fetch_one, get_list_filter_clause, get_datatables_sql
from backend.config import DATAMART_SCHEMA_NAME

DW = DATAMART_SCHEMA_NAME

def get_work_days_filters(region_name: str | list[str] | None = None):
    region_query = f"SELECT DISTINCT region_name FROM {DW}.dim_geography WHERE region_name IS NOT NULL ORDER BY region_name"
    regions = [row["region_name"] for row in fetch_all(region_query)]
    
    where_sql, params = get_list_filter_clause("region_name", region_name)
    area_query = f"SELECT DISTINCT area_name FROM {DW}.dim_geography WHERE area_name IS NOT NULL AND {where_sql} ORDER BY area_name"
    areas = [row["area_name"] for row in fetch_all(area_query, params)]
    
    year_query = f"SELECT DISTINCT year_actual FROM {DW}.dim_date ORDER BY year_actual DESC"
    years = [row["year_actual"] for row in fetch_all(year_query)]
    
    month_query = f"SELECT DISTINCT month_actual, TO_CHAR(TO_DATE(month_actual::text, 'MM'), 'Month') as month_name FROM {DW}.dim_date ORDER BY month_actual"
    months = [{"id": row["month_actual"], "name": row["month_name"].strip()} for row in fetch_all(month_query)]
    
    return {"regions": regions, "areas": areas, "years": years, "months": months}

def get_work_days_data(region=None, area=None, years=None, month=None, limit=15, offset=0, dt_params=None):
    clauses = []
    params = []
    
    c, p = get_list_filter_clause("g.region_name", region)
    clauses.append(c); params.extend(p)
    
    c, p = get_list_filter_clause("g.area_name", area)
    clauses.append(c); params.extend(p)
    
    c, p = get_list_filter_clause("d.year_actual", years, cast_type="int")
    clauses.append(c); params.extend(p)
    
    c, p = get_list_filter_clause("d.month_actual", month, cast_type="int")
    clauses.append(c); params.extend(p)
    
    where_sql = " AND ".join(clauses)
    
    # KPIs
    kpi_raw = fetch_one(f"""
        SELECT 
            COUNT(DISTINCT f.sk_user_id) as total_instructors,
            COUNT(DISTINCT CONCAT(f.sk_user_id, '_', f.date_id)) as total_working_days,
            COUNT(DISTINCT f.sk_geography_id) as active_centers
        FROM {DW}.fact_session f
        JOIN {DW}.dim_date d ON f.date_id = d.date_id
        JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        WHERE {where_sql}
    """, params)
    
    instructors = kpi_raw.get('total_instructors', 0) or 0
    working_days = kpi_raw.get('total_working_days', 0) or 0
    avg_days = round(working_days / instructors, 2) if instructors > 0 else 0
    
    kpi_list = [
        {"label": "Total Instructors", "value": instructors, "icon": "fas fa-users", "color": "bg-info"},
        {"label": "Total Working Days", "value": working_days, "icon": "fas fa-calendar-check", "color": "bg-success"},
        {"label": "Avg Days/Instructor", "value": avg_days, "icon": "fas fa-chart-line", "color": "bg-navy-blue"},
        {"label": "Active Centers", "value": kpi_raw.get('active_centers', 0) or 0, "icon": "fas fa-map-marker-alt", "color": "bg-danger"}
    ]

    # DataTable Logic
    search_sql = "1=1"
    search_params = []
    sort_sql = "ORDER BY total_days DESC, instructor_name ASC"
    
    if dt_params:
        searchable_cols = ["u.user_name", "g.region_name", "g.area_name"]
        sortable_cols = ["instructor_name", "region_area", "total_days"]
        
        inner_search_sql, inner_search_params, inner_sort_sql = get_datatables_sql(dt_params, searchable_cols, sortable_cols)
        search_sql = inner_search_sql
        search_params = inner_search_params
        if inner_sort_sql:
            sort_sql = inner_sort_sql

    total_rows_row = fetch_one(f"""
        SELECT COUNT(*) FROM (
            SELECT u.sk_user_id
            FROM {DW}.fact_session f
            JOIN {DW}.dim_user u ON f.sk_user_id = u.sk_user_id
            JOIN {DW}.dim_date d ON f.date_id = d.date_id
            JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            WHERE {where_sql} AND {search_sql}
            GROUP BY u.sk_user_id, g.region_name, g.area_name
        ) as sub
    """, params + search_params)
    total_rows = total_rows_row.get("count", 0) if total_rows_row else 0

    rows = fetch_all(f"""
        SELECT 
            u.user_name as instructor_name,
            CONCAT(g.region_name, ' / ', g.area_name) as region_area,
            COUNT(DISTINCT d.date_id) as total_days,
            STRING_AGG(DISTINCT TO_CHAR(d.full_date, 'DD'), ', ' ORDER BY TO_CHAR(d.full_date, 'DD')) as dates_active
        FROM {DW}.fact_session f
        JOIN {DW}.dim_user u ON f.sk_user_id = u.sk_user_id
        JOIN {DW}.dim_date d ON f.date_id = d.date_id
        JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        WHERE {where_sql} AND {search_sql}
        GROUP BY u.user_name, g.region_name, g.area_name
        {sort_sql}
        LIMIT %s OFFSET %s
    """, params + search_params + [limit, offset])

    return {
        "kpis": kpi_list,
        "table": rows,
        "total_count": int(total_rows)
    }
