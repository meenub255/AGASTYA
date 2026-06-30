from backend.services.query_utils import fetch_all, fetch_one
from backend.config import DATAMART_SCHEMA_NAME


def get_instructor_detail_filters():
    instructors = [row["user_name"] for row in fetch_all(f"""
        SELECT DISTINCT u.user_name 
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        JOIN {DATAMART_SCHEMA_NAME}.dim_user u ON f.sk_user_id = u.sk_user_id
        WHERE u.user_name IS NOT NULL 
        ORDER BY u.user_name
    """)]
    
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
        "instructors": instructors,
        "years": years,
        "months": months
    }


def get_instructor_detail_data(instructor_name=None, years=None, month=None, quarter=None, limit=15, offset=0, dt_params=None):
    from backend.services.query_utils import build_standard_filters, calculate_ytd_kpis, get_datatables_sql
    try:
        kpi_defs = [
            {"key": "total_sessions", "label": "Total Sessions", "sql": "COUNT(DISTINCT f.session_nk_id)", "icon": "fas fa-clock", "color": "linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%)"},
            {"key": "total_students", "label": "Total Students Reach", "sql": "SUM(COALESCE(e.total_exposure_count, 0) + COALESCE(f.community_men_count, 0) + COALESCE(f.community_women_count, 0))", "icon": "fas fa-user-graduate", "color": "linear-gradient(135deg, #22c55e 0%, #16a34a 100%)"},
            {"key": "unique_schools", "label": "Schools Covered", "sql": "COUNT(DISTINCT f.sk_school_id)", "icon": "fas fa-school", "color": "linear-gradient(135deg, #001f3f 0%, #001226 100%)"},
            {"key": "teachers_trained", "label": "Teachers Trained", "sql": "SUM(CASE WHEN a.activity_name ILIKE ANY (ARRAY['%%Meeting%%', '%%Training%%']) THEN GREATEST(COALESCE(f.no_of_teachers_participated, 0), COALESCE(f.community_men_count, 0) + COALESCE(f.community_women_count, 0), 1) ELSE COALESCE(f.no_of_teachers_participated, 0) END)", "icon": "fas fa-chalkboard-teacher", "color": "linear-gradient(135deg, #dc3545 0%, #c82333 100%)"}
        ]
        
        from_clause = f"""
            {DATAMART_SCHEMA_NAME}.fact_session f
            JOIN {DATAMART_SCHEMA_NAME}.dim_user u ON f.sk_user_id = u.sk_user_id
            JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
            LEFT JOIN {DATAMART_SCHEMA_NAME}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_activity_type a ON f.sk_activity_type_id = a.sk_activity_type_id
        """
        
        kpi_list, sparklines = calculate_ytd_kpis(
            kpi_defs=kpi_defs,
            from_clause=from_clause,
            years=years,
            month=month,
            quarter=quarter,
            region=None # instructor detail filter doesn't have region on sidebar
        )
        
        where_sql, params, max_month = build_standard_filters(
            years=years,
            month=month,
            quarter=quarter
        )
        
        # Add instructor filter manually
        if instructor_name:
            from backend.services.query_utils import get_list_filter_clause
            c, p = get_list_filter_clause("u.user_name", instructor_name)
            if c != "TRUE":
                where_sql = f"{where_sql} AND {c}" if where_sql != "TRUE" else c
                params.extend(p)

        # 2. DataTable Logic
        search_sql = "TRUE"
        search_params = []
        sort_sql = "ORDER BY d.full_date DESC"
        
        if dt_params:
            searchable_cols = ["COALESCE(p.program_name, '')", "COALESCE(a.activity_name, '')", "COALESCE(s.school_name, '')", "COALESCE(e.class_name, '')"]
            sortable_cols = ["program_name", "date", "activity_name", "school_name", "class_name", "topic_name", "boys", "girls", "community", "teachers"]
            
            inner_search_sql, inner_search_params, inner_sort_sql = get_datatables_sql(dt_params, searchable_cols, sortable_cols)
            search_sql = inner_search_sql
            search_params = inner_search_params
            if inner_sort_sql:
                sort_sql = inner_sort_sql

        # 3. Get total count of granular rows (Session + Class)
        count_sql = f"""
            SELECT COUNT(*) as count
            FROM {DATAMART_SCHEMA_NAME}.fact_session f
            JOIN {DATAMART_SCHEMA_NAME}.dim_user u ON f.sk_user_id = u.sk_user_id
            JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
            JOIN {DATAMART_SCHEMA_NAME}.dim_activity_type a ON f.sk_activity_type_id = a.sk_activity_type_id
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_school s ON f.sk_school_id = s.sk_school_id
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
            LEFT JOIN {DATAMART_SCHEMA_NAME}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {where_sql} AND {search_sql}
        """
        count_res = fetch_one(count_sql, params + search_params)
        total_count = int(count_res.get("count", 0)) if count_res else 0

        # 4. Get paginated granular data (10 Columns)
        sql = f"""
            SELECT 
                COALESCE(p.program_name, '') as program_name,
                d.full_date as date,
                COALESCE(a.activity_name, '') as activity_name,
                COALESCE(s.school_name, '') as school_name,
                COALESCE(e.class_name, 'Adhoc') as class_name,
                COALESCE(st.topic_description, ra.details, '') as topic_name,
                COALESCE(e.boys_count, 0) as boys,
                COALESCE(e.girls_count, 0) as girls,
                COALESCE(f.community_men_count, 0) + COALESCE(f.community_women_count, 0) as community,
                CASE 
                    WHEN a.activity_name ILIKE ANY (ARRAY['%%Meeting%%', '%%Training%%']) 
                    THEN GREATEST(COALESCE(f.no_of_teachers_participated, 0), COALESCE(f.community_men_count, 0) + COALESCE(f.community_women_count, 0))
                    ELSE COALESCE(f.no_of_teachers_participated, 0)
                END as teachers
            FROM {DATAMART_SCHEMA_NAME}.fact_session f
            JOIN {DATAMART_SCHEMA_NAME}.dim_user u ON f.sk_user_id = u.sk_user_id
            JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
            JOIN {DATAMART_SCHEMA_NAME}.dim_activity_type a ON f.sk_activity_type_id = a.sk_activity_type_id
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_school s ON f.sk_school_id = s.sk_school_id
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_subject_topic st ON f.sk_subject_topic_id = st.sk_subject_topic_id
            LEFT JOIN {DATAMART_SCHEMA_NAME}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            LEFT JOIN source.rpt_adhoc_feedback ra ON (f.session_nk_id - 1000000)::TEXT = ra.adhoc_id AND f.session_nk_id >= 1000000
            WHERE {where_sql} AND {search_sql}
            {sort_sql}
            LIMIT %s OFFSET %s
        """
        rows = fetch_all(sql, params + search_params + [limit, offset])
        
        return {
            "kpis": kpi_list,
            "sparklines": sparklines,
            "table": [{**row, "date": row["date"].strftime("%Y-%m-%d") if row["date"] else None} for row in rows],
            "total_count": total_count
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"kpis": [], "table": [], "total_count": 0, "error": str(e)}
