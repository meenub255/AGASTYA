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
    
    activity_types = [row["activity_name"] for row in fetch_all(f"""
        SELECT DISTINCT a.activity_name 
        FROM {DATAMART_SCHEMA_NAME}.dim_activity_type a
        INNER JOIN {DATAMART_SCHEMA_NAME}.fact_session f ON a.sk_activity_type_id = f.sk_activity_type_id
        WHERE a.activity_name IS NOT NULL
        ORDER BY a.activity_name
    """)]
    
    roles = [row["role_name"] for row in fetch_all(f"""
        SELECT DISTINCT u.role_name 
        FROM {DATAMART_SCHEMA_NAME}.dim_user u
        INNER JOIN {DATAMART_SCHEMA_NAME}.fact_session f ON u.sk_user_id = f.sk_user_id
        WHERE u.role_name IS NOT NULL
        ORDER BY u.role_name
    """)]
    
    return {
        "categories": categories,
        "years": years,
        "months": months,
        "quarters": [1, 2, 3, 4],
        "activity_types": activity_types,
        "roles": roles
    }


def get_programwise_report_data(category=None, years=None, month=None, quarter=None, limit=15, offset=0, dt_params=None, activity_types=None, roles=None):
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
    
    # Add activity_type filter if present
    if activity_types:
        c, p = get_list_filter_clause("a.activity_name", activity_types)
        if c != "TRUE":
            where_sql = where_sql + f" AND {c}" if where_sql != "TRUE" else c
            params.extend(p)
    
    # Add role filter if present
    if roles:
        c, p = get_list_filter_clause("u.role_name", roles)
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
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_activity_type a ON f.sk_activity_type_id = a.sk_activity_type_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_user u ON f.sk_user_id = u.sk_user_id
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
    sort_sql = 'ORDER BY "Total_Exposures" DESC'
    
    if dt_params:
        searchable_cols = ["g.region_name", "COALESCE(p.program_name, 'Unassigned')"]
        sortable_cols = ["State", "Program Name", "Total_Exposures", "No of Session", "Exp/Pgm", "Expo/Ignator", "Expo/Session", "NO of Ign", "WD"]
        
        inner_search_sql, inner_search_params, inner_sort_sql = get_datatables_sql(dt_params, searchable_cols, sortable_cols)
        search_sql = inner_search_sql
        search_params = inner_search_params
        if inner_sort_sql:
            sort_sql = inner_sort_sql

    # Get total count (Filtered by sidebar AND table search)
    count_sql = f"""
        SELECT COUNT(*) FROM (
            SELECT COALESCE(p.program_name, 'Unassigned') as program_name
            FROM {DATAMART_SCHEMA_NAME}.fact_session f
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_activity_type a ON f.sk_activity_type_id = a.sk_activity_type_id
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_user u ON f.sk_user_id = u.sk_user_id
            WHERE {where_sql} AND {search_sql}
            GROUP BY g.region_name, COALESCE(p.program_name, 'Unassigned')
        ) as sub
    """
    total_count_row = fetch_one(count_sql, params + search_params)
    total_count = total_count_row.get("count", 0) if total_count_row else 0

    # Get paginated data
    sql = f"""
        SELECT 
            g.region_name as "State",
            COALESCE(p.program_name, 'Unassigned') as "Program Name",
            SUM(COALESCE(e.total_exposure_count, 0)) as "Total_Exposures",
            COUNT(DISTINCT f.sk_fact_session_id) as "No of Session",
            ROUND(SUM(COALESCE(e.total_exposure_count, 0)) / NULLIF(COUNT(DISTINCT f.sk_fact_session_id), 0), 0) as "Exp/Pgm",
            ROUND(SUM(COALESCE(e.total_exposure_count, 0)) / NULLIF(COUNT(DISTINCT f.sk_user_id), 0), 0) as "Expo/Ignator",
            ROUND(SUM(COALESCE(e.total_exposure_count, 0)) / NULLIF(COUNT(DISTINCT f.sk_fact_session_id), 0), 0) as "Expo/Session",
            COUNT(DISTINCT f.sk_user_id) as "NO of Ign",
            COUNT(DISTINCT f.date_id) as "WD"
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_activity_type a ON f.sk_activity_type_id = a.sk_activity_type_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_user u ON f.sk_user_id = u.sk_user_id
        WHERE {where_sql} AND {search_sql}
        GROUP BY g.region_name, COALESCE(p.program_name, 'Unassigned')
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

    # Build WHERE clause for charts (without table search)
    chart_where_sql, chart_params, _ = build_standard_filters(
        years=years,
        month=month,
        quarter=quarter,
        date_alias="d"
    )
    if category:
        c, p = get_list_filter_clause("p.donor_name", category)
        if c != "TRUE":
            chart_where_sql = chart_where_sql + f" AND {c}" if chart_where_sql != "TRUE" else c
            chart_params.extend(p)
    if activity_types:
        c, p = get_list_filter_clause("a.activity_name", activity_types)
        if c != "TRUE":
            chart_where_sql = chart_where_sql + f" AND {c}" if chart_where_sql != "TRUE" else c
            chart_params.extend(p)
    if roles:
        c, p = get_list_filter_clause("u.role_name", roles)
        if c != "TRUE":
            chart_where_sql = chart_where_sql + f" AND {c}" if chart_where_sql != "TRUE" else c
            chart_params.extend(p)

    schools_by_region = fetch_all(f"""
        SELECT COALESCE(g.region_name, 'Unknown') AS label,
               COUNT(DISTINCT f.sk_school_id) AS value
               {group_select}
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
        JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_activity_type a ON f.sk_activity_type_id = a.sk_activity_type_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_user u ON f.sk_user_id = u.sk_user_id
        WHERE {chart_where_sql}
        GROUP BY g.region_name {group_sql} ORDER BY value DESC LIMIT 30
    """, chart_params)

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
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_activity_type a ON f.sk_activity_type_id = a.sk_activity_type_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_user u ON f.sk_user_id = u.sk_user_id
        WHERE {chart_where_sql}
        GROUP BY p.donor_name {yr_group_sql} ORDER BY value DESC LIMIT 15
    """, chart_params)

    # Program Type Summary
    program_type_summary = fetch_all(f"""
        SELECT
            COALESCE(t.code, 'Unknown') AS program_type,
            COALESCE(SUM(e.total_exposure_count), 0) AS total_exposures,
            COUNT(DISTINCT f.sk_fact_session_id) AS no_of_session,
            ROUND(COALESCE(SUM(e.total_exposure_count), 0) / NULLIF(COUNT(DISTINCT p.program_name), 0), 0) AS exp_pgm,
            ROUND(COALESCE(SUM(e.total_exposure_count), 0) / NULLIF(COUNT(DISTINCT f.sk_user_id), 0), 0) AS expo_ign,
            ROUND(COALESCE(SUM(e.total_exposure_count), 0) / NULLIF(COUNT(DISTINCT f.sk_fact_session_id), 0), 0) AS expo_session,
            COUNT(DISTINCT p.program_name) AS no_of_programs,
            COUNT(DISTINCT f.sk_user_id) AS no_of_ins,
            COUNT(DISTINCT f.date_id) AS wd
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
        LEFT JOIN source.txn_program tp ON p.nk_program_id::TEXT = tp.txn_program_id
        LEFT JOIN source.mst_program_type t ON tp.program_type_id = t.mst_program_type_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_activity_type a ON f.sk_activity_type_id = a.sk_activity_type_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_user u ON f.sk_user_id = u.sk_user_id
        WHERE {chart_where_sql} AND t.code IS NOT NULL
        GROUP BY t.code
        ORDER BY total_exposures DESC
    """, chart_params)

    return {
        "kpis": kpi_list,
        "sparklines": sparklines,
        "program_type_summary": program_type_summary,
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
