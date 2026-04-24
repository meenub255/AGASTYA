import logging
from backend.services.query_utils import fetch_all, fetch_one
from backend.config import DATAMART_SCHEMA_NAME

logger = logging.getLogger(__name__)
DW = DATAMART_SCHEMA_NAME


def get_performance_mgmt_filters():
    try:
        regions = [r["region_name"] for r in fetch_all(
            f"SELECT DISTINCT region_name FROM {DW}.dim_geography WHERE region_name IS NOT NULL ORDER BY region_name"
        )]
        years = [r["year_actual"] for r in fetch_all(
            f"SELECT DISTINCT year_actual FROM {DW}.dim_date WHERE year_actual IS NOT NULL ORDER BY year_actual DESC"
        )]
        months = [{"id": r["month_actual"], "name": r["month_name"].strip()} for r in fetch_all(
            f"SELECT DISTINCT month_actual, TO_CHAR(TO_DATE(month_actual::text,'MM'),'Month') AS month_name FROM {DW}.dim_date ORDER BY month_actual"
        )]
        return {"regions": regions, "years": years, "months": months}
    except Exception as e:
        logger.error(f"performance mgmt filters error: {e}")
        return {"regions": [], "years": [], "months": []}


def get_performance_mgmt_data(region=None, year=None, month=None, limit=15, offset=0, dt_params=None):
    from backend.services.query_utils import parse_datatables_params, get_datatables_sql, get_list_filter_clause
    try:
        clauses = []
        params = []
        
        c, p = get_list_filter_clause("g.region_name", region)
        clauses.append(c); params.extend(p)
        
        c, p = get_list_filter_clause("d.year_actual", year, cast_type="int")
        clauses.append(c); params.extend(p)
        
        c, p = get_list_filter_clause("d.month_actual", month, cast_type="int")
        clauses.append(c); params.extend(p)
        
        where_sql = " AND ".join(clauses)

        # KPI Query (sidebar filters only)
        kpi_row = fetch_one(f"""
            SELECT
                COUNT(DISTINCT f.sk_user_id)                   AS total_instructors,
                COUNT(DISTINCT f.sk_fact_session_id)           AS total_sessions,
                COALESCE(SUM(e.total_exposure_count), 0)       AS total_students
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d       ON f.date_id = d.date_id
            LEFT JOIN {DW}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {where_sql}
        """, params)

        total_instructors = int(kpi_row.get("total_instructors", 0) or 0)
        total_sessions    = int(kpi_row.get("total_sessions", 0) or 0)
        avg_per_inst      = round(total_sessions / total_instructors, 1) if total_instructors else 0

        kpis = [
            {"label": "Total Instructors",        "value": total_instructors,                                      "icon": "fas fa-users",              "color": "bg-info"},
            {"label": "Avg Sessions/Instructor",   "value": avg_per_inst,                                           "icon": "fas fa-chart-line",         "color": "bg-success"},
            {"label": "Total Sessions",            "value": total_sessions,                                         "icon": "fas fa-chalkboard-teacher", "color": "bg-navy-blue"},
            {"label": "Total Students Impacted",   "value": int(kpi_row.get("total_students", 0) or 0),            "icon": "fas fa-user-graduate",      "color": "bg-danger"},
        ]

        # DataTable Logic
        search_sql = "TRUE"
        search_params = []
        sort_sql = "ORDER BY sessions DESC"
        
        if dt_params:
            searchable_cols = ["u.user_name", "u.role_name", "g.region_name"]
            sortable_cols = ["instructor_name", "role", "region_name", "programs", "sessions", "schools", "students_impacted", "avg_duration_min"]
            
            inner_search_sql, inner_search_params, inner_sort_sql = get_datatables_sql(dt_params, searchable_cols, sortable_cols)
            search_sql = inner_search_sql
            search_params = inner_search_params
            if inner_sort_sql:
                sort_sql = inner_sort_sql

        # Get total count (Filtered by sidebar AND table search)
        count_sql = f"""
            SELECT COUNT(*) FROM (
                SELECT u.user_name
                FROM {DW}.fact_session f
                LEFT JOIN {DW}.dim_user u       ON f.sk_user_id = u.sk_user_id
                LEFT JOIN {DW}.dim_geography g  ON f.sk_geography_id = g.sk_geography_id
                LEFT JOIN {DW}.dim_date d       ON f.date_id = d.date_id
                WHERE {where_sql} AND {search_sql}
                GROUP BY u.user_name, u.role_name, g.region_name
            ) as sub
        """
        total_count = fetch_one(count_sql, params + search_params).get("count", 0)

        # Get paginated data
        table = fetch_all(f"""
            SELECT
                COALESCE(u.user_name, 'Unknown')                   AS instructor_name,
                COALESCE(u.role_name, 'Unknown')                   AS role,
                COALESCE(g.region_name, 'Unknown')                 AS region_name,
                COUNT(DISTINCT f.sk_program_id)                    AS programs,
                COUNT(DISTINCT f.sk_fact_session_id)               AS sessions,
                COUNT(DISTINCT f.sk_school_id)                     AS schools,
                COALESCE(SUM(e.total_exposure_count), 0)           AS students_impacted,
                ROUND(AVG(COALESCE(f.session_duration_minutes,0)),1) AS avg_duration_min
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_user u       ON f.sk_user_id = u.sk_user_id
            LEFT JOIN {DW}.dim_geography g  ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d       ON f.date_id = d.date_id
            LEFT JOIN {DW}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {where_sql} AND {search_sql}
            GROUP BY u.user_name, u.role_name, g.region_name
            {sort_sql}
            LIMIT %s OFFSET %s
        """, params + search_params + [limit, offset])

        return {"kpis": kpis, "table": table, "total_count": int(total_count)}

        return {"kpis": kpis, "table": table, "total_count": int(total_count)}
    except Exception as e:
        logger.error(f"performance mgmt data error: {e}", exc_info=True)
        return {"kpis": [], "table": [], "total_count": 0}
