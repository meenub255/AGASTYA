from backend.services.query_utils import fetch_all, fetch_one
from backend.config import DATAMART_SCHEMA_NAME


def get_instructor_detail_filters():
    # Fetch from new dim_user and dim_date
    instructors = [row["user_name"] for row in fetch_all(f"SELECT DISTINCT user_name FROM {DATAMART_SCHEMA_NAME}.dim_user WHERE user_name IS NOT NULL ORDER BY user_name")]
    
    years = [row["year_actual"] for row in fetch_all(f"SELECT DISTINCT year_actual FROM {DATAMART_SCHEMA_NAME}.dim_date WHERE year_actual IS NOT NULL ORDER BY year_actual DESC")]
    
    months = [{"id": row["month_actual"], "name": row["month_name"].strip()} for row in fetch_all(f"SELECT DISTINCT month_actual, TO_CHAR(TO_DATE(month_actual::text, 'MM'), 'Month') as month_name FROM {DATAMART_SCHEMA_NAME}.dim_date ORDER BY month_actual")]
    
    return {
        "instructors": instructors,
        "years": years,
        "months": months
    }


def get_instructor_detail_data(instructor_name=None, year=None, month=None, limit=15, offset=0, dt_params=None):
    from backend.services.query_utils import parse_datatables_params, get_datatables_sql, get_list_filter_clause
    try:
        clauses = []
        params = []
        
        c, p = get_list_filter_clause("u.user_name", instructor_name)
        clauses.append(c); params.extend(p)
        
        c, p = get_list_filter_clause("d.year_actual", year, cast_type="int")
        clauses.append(c); params.extend(p)
        
        c, p = get_list_filter_clause("d.month_actual", month, cast_type="int")
        clauses.append(c); params.extend(p)
        
        where_sql = " AND ".join(clauses)
        
        # 1. Aggregated KPIs for top cards (sidebar filters only)
        kpi_sql = f"""
            SELECT 
                COUNT(DISTINCT f.session_nk_id) as total_sessions,
                SUM(COALESCE(e.total_exposure_count, 0)) as total_students,
                COUNT(DISTINCT f.sk_school_id) as unique_schools,
                SUM(COALESCE(f.no_of_teachers_participated, 0)) as teachers_trained
            FROM {DATAMART_SCHEMA_NAME}.fact_session f
            JOIN {DATAMART_SCHEMA_NAME}.dim_user u ON f.sk_user_id = u.sk_user_id
            JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
            LEFT JOIN {DATAMART_SCHEMA_NAME}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {where_sql}
        """
        kpi_res = fetch_one(kpi_sql, params)

        # 2. DataTable Logic
        search_sql = "TRUE"
        search_params = []
        sort_sql = "ORDER BY d.full_date DESC"
        
        if dt_params:
            searchable_cols = ["COALESCE(p.program_name, '')", "COALESCE(a.activity_name, '')", "COALESCE(s.school_name, '')", "COALESCE(e.class_name, '')"]
            sortable_cols = ["program_name", "date", "activity_name", "school_name", "class_name", "boys", "girls", "teachers"]
            
            inner_search_sql, inner_search_params, inner_sort_sql = get_datatables_sql(dt_params, searchable_cols, sortable_cols)
            search_sql = inner_search_sql
            search_params = inner_search_params
            if inner_sort_sql:
                mapping = {
                    "date": "d.full_date",
                    "activity_name": "a.activity_name",
                    "school_name": "s.school_name",
                    "class_name": "e.class_name",
                    "boys": "e.boys_count",
                    "girls": "e.girls_count",
                    "teachers": "f.no_of_teachers_participated"
                }
                for alias, db_col in mapping.items():
                    inner_sort_sql = inner_sort_sql.replace(alias, db_col)
                sort_sql = inner_sort_sql

        # 3. Get total count of granular rows (Session + Class)
        count_sql = f"""
            SELECT COUNT(*) as count
            FROM {DATAMART_SCHEMA_NAME}.fact_session f
            JOIN {DATAMART_SCHEMA_NAME}.dim_user u ON f.sk_user_id = u.sk_user_id
            JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
            JOIN {DATAMART_SCHEMA_NAME}.dim_school s ON f.sk_school_id = s.sk_school_id
            JOIN {DATAMART_SCHEMA_NAME}.dim_activity_type a ON f.sk_activity_type_id = a.sk_activity_type_id
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
            LEFT JOIN {DATAMART_SCHEMA_NAME}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {where_sql} AND {search_sql}
        """
        count_res = fetch_one(count_sql, params + search_params)
        total_count = int(count_res.get("count", 0)) if count_res else 0

        # 4. Get paginated granular data (9 Columns)
        sql = f"""
            SELECT 
                COALESCE(p.program_name, 'N/A') as program_name,
                d.full_date as date,
                COALESCE(a.activity_name, 'N/A') as activity_name,
                COALESCE(s.school_name, 'N/A') as school_name,
                COALESCE(e.class_name, 'N/A') as class_name,
                'N/A' as topic_name,
                COALESCE(e.boys_count, 0) as boys,
                COALESCE(e.girls_count, 0) as girls,
                COALESCE(f.no_of_teachers_participated, 0) as teachers
            FROM {DATAMART_SCHEMA_NAME}.fact_session f
            JOIN {DATAMART_SCHEMA_NAME}.dim_user u ON f.sk_user_id = u.sk_user_id
            JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
            JOIN {DATAMART_SCHEMA_NAME}.dim_school s ON f.sk_school_id = s.sk_school_id
            JOIN {DATAMART_SCHEMA_NAME}.dim_activity_type a ON f.sk_activity_type_id = a.sk_activity_type_id
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
            LEFT JOIN {DATAMART_SCHEMA_NAME}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {where_sql} AND {search_sql}
            {sort_sql}
            LIMIT %s OFFSET %s
        """
        rows = fetch_all(sql, params + search_params + [limit, offset])
        
        return {
            "kpis": [
                {"label": "Total Sessions", "value": int(kpi_res.get("total_sessions", 0) or 0), "icon": "fas fa-clock", "color": "bg-info"},
                {"label": "Total Students Reach", "value": int(kpi_res.get("total_students", 0) or 0), "icon": "fas fa-user-graduate", "color": "bg-success"},
                {"label": "Schools Covered", "value": int(kpi_res.get("unique_schools", 0) or 0), "icon": "fas fa-school", "color": "bg-navy-blue"},
                {"label": "Teachers Trained", "value": int(kpi_res.get("teachers_trained", 0) or 0), "icon": "fas fa-chalkboard-teacher", "color": "bg-danger"},
            ],
            "table": [{**row, "date": row["date"].strftime("%Y-%m-%d") if row["date"] else None} for row in rows],
            "total_count": total_count
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"kpis": [], "table": [], "total_count": 0, "error": str(e)}
