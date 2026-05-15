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
        "months": months
    }


def get_programwise_report_data(category=None, year=None, month=None, limit=15, offset=0, dt_params=None):
    from backend.services.query_utils import parse_datatables_params, get_datatables_sql
    where_clauses = []
    params = []
    
    # Use helper for list-based filters
    c_clause, c_params = get_list_filter_clause("p.donor_name", category)
    where_clauses.append(c_clause)
    params.extend(c_params)
    
    y_clause, y_params = get_list_filter_clause("d.year_actual", year, cast_type="int")
    where_clauses.append(y_clause)
    params.extend(y_params)
    
    m_clause, m_params = get_list_filter_clause("d.month_actual", month, cast_type="int")
    where_clauses.append(m_clause)
    params.extend(m_params)
    
    where_sql = " AND ".join(where_clauses)
    
    # 1. KPI Query (sidebar filters only)
    kpi_sql = f"""
        SELECT 
            COALESCE(COUNT(DISTINCT p.program_name), 0) as total_programs,
            COALESCE(COUNT(DISTINCT f.sk_school_id), 0) as total_schools,
            COALESCE(COUNT(DISTINCT f.sk_fact_session_id), 0) as total_sessions,
            COALESCE(SUM(e.total_exposure_count), 0) as total_students
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
        WHERE {where_sql}
    """
    kpis_raw = fetch_one(kpi_sql, params)
    
    # Insight Logic
    top_donor_row = fetch_one(f"""
        SELECT COALESCE(p.donor_name, 'Unknown') as donor_name,
               COUNT(DISTINCT f.sk_fact_session_id) as sessions
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        WHERE {where_sql}
        GROUP BY p.donor_name
        ORDER BY sessions DESC
        LIMIT 1
    """, params)
    top_donor = top_donor_row.get("donor_name", "N/A") if top_donor_row else "N/A"

    kpis = [
        {"label": "Total Programs", "value": int(kpis_raw.get('total_programs', 0) or 0), "icon": "fas fa-project-diagram", "color": "bg-info", "status": "Stable", "reason": f"Active projects including top contributor {top_donor}."},
        {"label": "Total Schools", "value": int(kpis_raw.get('total_schools', 0) or 0), "icon": "fas fa-school", "color": "bg-success", "status": "High", "reason": f"Wide implementation reach across {int(kpis_raw.get('total_schools', 0) or 0)} campuses."},
        {"label": "Total Sessions", "value": int(kpis_raw.get('total_sessions', 0) or 0), "icon": "fas fa-chalkboard-teacher", "color": "bg-navy-blue", "status": "Stable", "reason": f"Delivery consistent with {top_donor} requirements."},
        {"label": "Total Students", "value": int(kpis_raw.get('total_students', 0) or 0), "icon": "fas fa-user-graduate", "color": "bg-danger", "status": "Growth", "reason": f"Broad educational impact with strong enrollment."}
    ]

    # 2. DataTable Logic
    search_sql = "TRUE"
    search_params = []
    sort_sql = 'ORDER BY "School Sessions" DESC'
    
    if dt_params:
        searchable_cols = ["g.region_name", "g.area_name", "p.program_name", "p.donor_name"]
        sortable_cols = ["Region Name", "Area Name", "Program Name", "Donor Name", "No of Schools visited", "Total Number of Days worked", "School Sessions", "Average Session Durat", "Total Exposure"]
        # Map some columns to actual complex SQL if needed, but here simple aliases work for Postgres "ORDER BY"
        
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
    # Comparison Logic: If multiple donors are selected, group by donor as well
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

    # Chart 2: Sessions by Donor (pie chart) - usually doesn't need grouping unless comparing years
    compare_year = isinstance(year, list) and len([v for v in year if v]) > 1
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
        "kpis": kpis,
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

