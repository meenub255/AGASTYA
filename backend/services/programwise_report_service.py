from backend.services.query_utils import fetch_all, fetch_one, get_list_filter_clause
from backend.config import DATAMART_SCHEMA_NAME

def get_programwise_report_filters():
    # INNER JOIN with fact_session to ensure data exists
    categories = [row["donor_name"] for row in fetch_all(f"""
        SELECT DISTINCT p.donor_name 
        FROM {DATAMART_SCHEMA_NAME}.dim_program p
        INNER JOIN {DATAMART_SCHEMA_NAME}.fact_session f ON p.sk_program_id = f.sk_program_id
        WHERE p.donor_name IS NOT NULL 
        ORDER BY p.donor_name
    """)]
    
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
        "categories": categories,
        "years": years,
        "months": months,
        "quarters": [1, 2, 3, 4]
    }


def get_programwise_report_data(category=None, years=None, month=None, quarter=None, limit=15, offset=0, dt_params=None):
    from backend.services.query_utils import build_standard_filters, calculate_ytd_kpis, get_datatables_sql
    
    # Build standard filters (handles YTD capping automatically)
    where_sql, params, max_month = build_standard_filters(
        years=years,
        month=month,
        quarter=quarter,
        date_alias="d"
    )
    
    # Add category (donor_name) filter if present
    if category:
        c, p = get_list_filter_clause("p.donor_name", category)
        if c != "TRUE":
            where_sql = where_sql + f" AND {c}" if where_sql != "TRUE" else c
            params.extend(p)
    
    kpi_defs = [
        {"key": "total_programs", "label": "Total Programs", "sql": "COUNT(DISTINCT p.program_name)", "icon": "fas fa-project-diagram", "color": "bg-info"},
        {"key": "total_schools", "label": "Total Schools", "sql": "COUNT(DISTINCT f.sk_school_id)", "icon": "fas fa-school", "color": "bg-success"},
        {"key": "total_sessions", "label": "Total Sessions", "sql": "COUNT(DISTINCT f.sk_fact_session_id)", "icon": "fas fa-chalkboard-teacher", "color": "bg-navy-blue"},
        {"key": "total_students", "label": "Total Students", "sql": "COALESCE(SUM(e.total_exposure_count), 0)", "icon": "fas fa-user-graduate", "color": "bg-danger"}
    ]
    
    from_clause = f"""
        {DATAMART_SCHEMA_NAME}.fact_session f
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
    """
    
    kpi_list, sparklines = calculate_ytd_kpis(
        kpi_defs=kpi_defs,
        from_clause=from_clause,
        years=years,
        month=month,
        quarter=quarter,
        program=category,
        program_expr="p.donor_name"
    )

    # 2. DataTable Logic
    search_sql = "TRUE"
    search_params = []
    sort_sql = 'ORDER BY "School Sessions" DESC'
    
    if dt_params:
        searchable_cols = ["g.region_name", "g.area_name", "p.program_name", "p.donor_name"]
        sortable_cols = ["Region Name", "Area Name", "Program Name", "Donor Name", "No of Schools visited", "Total Number of Days worked", "School Sessions", "Average Session Durat", "Total Exposure"]
        
        inner_search_sql, inner_search_params, inner_sort_sql = get_datatables_sql(dt_params, searchable_cols, sortable_cols)
        search_sql = inner_search_sql
        search_params = inner_search_params
        if inner_sort_sql:
            sort_sql = inner_sort_sql

    # Get total count (Filtered by sidebar AND table search)
    count_sql = f"""
        SELECT COUNT(*) FROM (
            SELECT p.program_name
            FROM {DATAMART_SCHEMA_NAME}.fact_session f
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
            WHERE {where_sql} AND {search_sql}
            GROUP BY p.program_name, g.region_name, g.area_name, p.donor_name
        ) as sub
    """
    total_count_row = fetch_one(count_sql, params + search_params)
    total_count = total_count_row.get("count", 0) if total_count_row else 0

    # Get paginated data
    sql = f"""
        SELECT 
            g.region_name as "Region Name",
            g.area_name as "Area Name",
            p.program_name as "Program Name",
            p.donor_name as "Donor Name",
            COUNT(DISTINCT f.sk_school_id) as "No of Schools visited",
            COUNT(DISTINCT f.date_id) as "Total Number of Days worked",
            COUNT(DISTINCT f.sk_fact_session_id) as "School Sessions",
            ROUND(AVG(COALESCE(f.session_duration_minutes, 0)), 2) as "Average Session Durat",
            SUM(COALESCE(e.total_exposure_count, 0)) as "Total Exposure"
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
        WHERE {where_sql} AND {search_sql}
        GROUP BY g.region_name, g.area_name, p.program_name, p.donor_name
        {sort_sql}
        LIMIT %s OFFSET %s
    """
    rows = fetch_all(sql, params + search_params + [limit, offset])
    
    # Chart 1: Schools Visited by Region (bar chart)
    compare_donor = isinstance(category, list) and len([v for v in category if v]) > 1
    
    group_sql = ""
    group_select = ""
    if compare_donor:
        group_sql = ", p.donor_name"
        group_select = ", COALESCE(p.donor_name, 'Unknown') AS group"

    schools_by_region = fetch_all(f"""
        SELECT COALESCE(g.region_name, 'Unknown') AS label,
               COUNT(DISTINCT f.sk_school_id) AS value
               {group_select}
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
        JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        WHERE {where_sql}
        GROUP BY g.region_name {group_sql} ORDER BY value DESC LIMIT 30
    """, params)

    # Chart 2: Sessions by Donor (pie chart)
    compare_year = isinstance(years, list) and len([v for v in years if v]) > 1
    yr_group_sql = ""
    yr_group_select = ""
    if compare_year:
        yr_group_sql = ", d.year_actual"
        yr_group_select = ", d.year_actual::text AS group"

    sessions_by_donor = fetch_all(f"""
        SELECT COALESCE(p.donor_name, 'Unknown') AS label,
               COUNT(DISTINCT f.sk_fact_session_id) AS value
               {yr_group_select}
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
        JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        WHERE {where_sql}
        GROUP BY p.donor_name {yr_group_sql} ORDER BY value DESC LIMIT 15
    """, params)

    return {
        "kpis": kpi_list,
        "sparklines": sparklines,
        "table": rows, 
        "total_count": int(total_count or 0),
        "charts": {
            "schools_by_region": [{
                "label": r["label"], 
                "value": float(r["value"]),
                **({"group": r["group"]} if "group" in r else {})
            } for r in schools_by_region],
            "sessions_by_donor": [{
                "label": r["label"], 
                "value": float(r["value"]),
                **({"group": r["group"]} if "group" in r else {})
            } for r in sessions_by_donor],
        }
    }
