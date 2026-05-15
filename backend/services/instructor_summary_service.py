from backend.services.query_utils import fetch_all, fetch_one
from backend.config import DATAMART_SCHEMA_NAME


def get_instructor_summary_filters(year=None, region=None, area=None):
    from backend.services.query_utils import get_list_filter_clause
    try:
        # 1. Available Years
        years = [r["year_actual"] for r in fetch_all(
            f"SELECT DISTINCT d.year_actual FROM {DATAMART_SCHEMA_NAME}.fact_session f JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id ORDER BY d.year_actual DESC"
        )]

        # 2. Available Regions (filtered by year)
        y_clauses, y_params = get_list_filter_clause("d.year_actual", year, cast_type="int")
        regions = [r["region_name"] for r in fetch_all(f"""
            SELECT DISTINCT g.region_name 
            FROM {DATAMART_SCHEMA_NAME}.fact_session f 
            JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
            WHERE {y_clauses} AND g.region_name IS NOT NULL
            ORDER BY g.region_name
        """, y_params)]

        # 3. Available Areas (filtered by year and region)
        a_clauses, a_params = [], []
        c, p = get_list_filter_clause("d.year_actual", year, cast_type="int"); a_clauses.append(c); a_params.extend(p)
        c, p = get_list_filter_clause("g.region_name", region); a_clauses.append(c); a_params.extend(p)
        a_where = " AND ".join(a_clauses)
        areas = [r["area_name"] for r in fetch_all(f"""
            SELECT DISTINCT g.area_name 
            FROM {DATAMART_SCHEMA_NAME}.fact_session f 
            JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
            WHERE {a_where} AND g.area_name IS NOT NULL
            ORDER BY g.area_name
        """, a_params)]

        # 4. Available Months (filtered by year, region, and area)
        m_clauses, m_params = [], []
        c, p = get_list_filter_clause("d.year_actual", year, cast_type="int"); m_clauses.append(c); m_params.extend(p)
        c, p = get_list_filter_clause("g.region_name", region); m_clauses.append(c); m_params.extend(p)
        c, p = get_list_filter_clause("g.area_name", area); m_clauses.append(c); m_params.extend(p)
        m_where = " AND ".join(m_clauses)
        months = [{"id": r["month_actual"], "name": r["month_name"].strip()} for r in fetch_all(f"""
            SELECT DISTINCT d.month_actual, TO_CHAR(TO_DATE(d.month_actual::text,'MM'),'Month') AS month_name 
            FROM {DATAMART_SCHEMA_NAME}.fact_session f
            JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
            JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            WHERE {m_where}
            ORDER BY d.month_actual
        """, m_params)]

        return {
            "regions": regions,
            "areas": areas,
            "years": years,
            "months": months
        }
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"instructor summary filters error: {e}")
        return {"regions": [], "areas": [], "years": [], "months": []}


def get_instructor_summary_data(region=None, area=None, year=None, month=None, limit=15, offset=0, dt_params=None):
    from backend.services.query_utils import parse_datatables_params, get_datatables_sql, get_list_filter_clause
 
    where_clauses = []
    params = []
    
    r_clause, r_params = get_list_filter_clause("g.region_name", region)
    where_clauses.append(r_clause)
    params.extend(r_params)

    a_clause, a_params = get_list_filter_clause("g.area_name", area)
    where_clauses.append(a_clause)
    params.extend(a_params)

    y_clause, y_params = get_list_filter_clause("d.year_actual", year, cast_type="int")
    where_clauses.append(y_clause)
    params.extend(y_params)

    m_clause, m_params = get_list_filter_clause("d.month_actual", month, cast_type="int")
    where_clauses.append(m_clause)
    params.extend(m_params)
    
    where_sql = " AND ".join(where_clauses)
    
    # Get KPIs (limited by sidebar filters only)
    kpi_sql = f"""
        SELECT 
            COUNT(DISTINCT d.full_date) as days_worked,
            COUNT(f.sk_fact_session_id) as total_sessions,
            SUM(COALESCE(e.total_exposure_count, 0) + COALESCE(f.community_men_count, 0) + COALESCE(f.community_women_count, 0)) as total_exposures,
            SUM(CASE WHEN 
                a.activity_name ILIKE ANY (ARRAY['%%YIL%%', '%%Young Instructor Leader%%', '%%SF%%', '%%Science Fair%%', '%%CV%%', '%%Community Visit%%']) 
                OR p.program_name ILIKE ANY (ARRAY['%%YIL%%', '%%SF%%', '%%CV%%', '%%Community%%'])
                OR st.topic_description ILIKE ANY (ARRAY['%%YIL%%', '%%Science Fair%%'])
                THEN COALESCE(e.total_exposure_count, 0) + COALESCE(f.community_men_count, 0) + COALESCE(f.community_women_count, 0) ELSE 0 END) as combined_exposures
        FROM {DATAMART_SCHEMA_NAME}.dim_user u
        LEFT JOIN {DATAMART_SCHEMA_NAME}.fact_session f ON u.sk_user_id = f.sk_user_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_activity_type a ON f.sk_activity_type_id = a.sk_activity_type_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_subject_topic st ON f.sk_subject_topic_id = st.sk_subject_topic_id
        WHERE {where_sql or 'TRUE'}
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
            WHERE {where_sql or 'TRUE'} AND {search_sql}
            GROUP BY u.sk_user_id
        ) as sub
    """
    total_count = fetch_one(count_sql, params + search_params).get("count", 0)

    # Main query to aggregate instructor metrics
    main_sql = f"""
        SELECT 
            u.user_name as instructor_name,
            COUNT(DISTINCT d.full_date) as days_worked,
            COUNT(DISTINCT CASE WHEN a.activity_name ILIKE '%%School%%' OR a.activity_name ILIKE '%%Direct%%' THEN f.sk_fact_session_id END) as school_sessions,
            COUNT(f.sk_fact_session_id) as total_sessions,
            SUM(COALESCE(e.total_exposure_count, 0) + COALESCE(f.community_men_count, 0) + COALESCE(f.community_women_count, 0)) as total_exposures,
            COUNT(DISTINCT CASE WHEN a.activity_name ILIKE '%%Fair%%' OR p.program_name ILIKE '%%Fair%%' OR st.topic_description ILIKE '%%Fair%%' THEN f.sk_fact_session_id END) as fair_count,
            COUNT(DISTINCT CASE WHEN a.activity_name ILIKE '%%Training%%' OR a.activity_name ILIKE '%%Meeting%%' THEN f.sk_fact_session_id END) as training_exposures,
            SUM(CASE WHEN a.activity_name ILIKE '%%Science Fair%%' OR p.program_name ILIKE '%%SF%%' OR st.topic_description ILIKE '%%Science Fair%%' THEN COALESCE(e.total_exposure_count, 0) + COALESCE(f.community_men_count, 0) + COALESCE(f.community_women_count, 0) ELSE 0 END) as sf_exposures,
            COUNT(DISTINCT CASE WHEN a.activity_name ILIKE '%%Young Instructor Leader%%' OR p.program_name ILIKE '%%YIL%%' OR st.topic_description ILIKE '%%YIL%%' THEN f.sk_fact_session_id END) as yil_sessions,
            SUM(CASE WHEN a.activity_name ILIKE '%%Young Instructor Leader%%' OR p.program_name ILIKE '%%YIL%%' OR st.topic_description ILIKE '%%YIL%%' THEN COALESCE(e.total_exposure_count, 0) + COALESCE(f.community_men_count, 0) + COALESCE(f.community_women_count, 0) ELSE 0 END) as yil_exposures,
            COUNT(DISTINCT CASE WHEN a.activity_name ILIKE '%%Community Visit%%' OR p.program_name ILIKE '%%CV%%' OR p.program_name ILIKE '%%Community%%' THEN f.sk_fact_session_id END) as cv_visits,
            SUM(CASE WHEN a.activity_name ILIKE '%%Community Visit%%' OR p.program_name ILIKE '%%CV%%' OR p.program_name ILIKE '%%Community%%' THEN COALESCE(e.total_exposure_count, 0) + COALESCE(f.community_men_count, 0) + COALESCE(f.community_women_count, 0) ELSE 0 END) as cv_exposures
        FROM {DATAMART_SCHEMA_NAME}.dim_user u
        LEFT JOIN {DATAMART_SCHEMA_NAME}.fact_session f ON u.sk_user_id = f.sk_user_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_activity_type a ON f.sk_activity_type_id = a.sk_activity_type_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_subject_topic st ON f.sk_subject_topic_id = st.sk_subject_topic_id
        WHERE {where_sql or 'TRUE'} AND {search_sql}
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


def get_monthly_instructor_summary(region=None, area=None, year=None, month=None):
    from backend.services.query_utils import get_list_filter_clause
    
    where_clauses = []
    params = []
    
    r_clause, r_params = get_list_filter_clause("g.region_name", region)
    where_clauses.append(r_clause)
    params.extend(r_params)

    a_clause, a_params = get_list_filter_clause("g.area_name", area)
    where_clauses.append(a_clause)
    params.extend(a_params)

    y_clause, y_params = get_list_filter_clause("d.year_actual", year, cast_type="int")
    where_clauses.append(y_clause)
    params.extend(y_params)

    m_clause, m_params = get_list_filter_clause("d.month_actual", month, cast_type="int")
    where_clauses.append(m_clause)
    params.extend(m_params)
    
    where_sql = " AND ".join(where_clauses)
    
    # Check if we should group by year (comparison mode)
    is_multi_year = isinstance(year, list) and len([v for v in year if v]) > 1
    
    group_col = "d.year_actual::text" if is_multi_year else "'All Years'"
    
    query = f"""
        SELECT 
            d.month_name as label,
            {group_col} as group,
            COUNT(f.sk_fact_session_id) as value,
            d.month_actual as month_sort
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        WHERE {where_sql or 'TRUE'}
        GROUP BY d.month_name, {group_col}, d.month_actual
        ORDER BY d.month_actual, {group_col}
    """
    return fetch_all(query, params)
