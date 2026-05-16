import logging
from backend.services.query_utils import fetch_all, fetch_one
from backend.config import DATAMART_SCHEMA_NAME

logger = logging.getLogger(__name__)
DW = DATAMART_SCHEMA_NAME


def get_instructor_feedback_filters():
    try:
        instructors = [r["user_name"] for r in fetch_all(f"""
            SELECT DISTINCT u.user_name 
            FROM {DW}.fact_session f
            JOIN {DW}.dim_user u ON f.sk_user_id = u.sk_user_id
            WHERE u.user_name IS NOT NULL 
            ORDER BY u.user_name
        """)]
        years = [r["year_actual"] for r in fetch_all(f"""
            SELECT DISTINCT d.year_actual 
            FROM {DW}.fact_session f
            JOIN {DW}.dim_date d ON f.date_id = d.date_id
            WHERE d.year_actual IS NOT NULL 
            ORDER BY d.year_actual DESC
        """)]
        return {"instructors": instructors, "years": years}
    except Exception as e:
        logger.error(f"instructor feedback filters error: {e}")
        return {"instructors": [], "years": []}


def get_instructor_feedback_data(instructor_name=None, years=None, limit=15, offset=0, dt_params=None):
    from backend.services.query_utils import parse_datatables_params, get_datatables_sql, get_list_filter_clause
    try:
        clauses = []
        params = []
        
        c, p = get_list_filter_clause("u.user_name", instructor_name)
        clauses.append(c); params.extend(p)
        
        c, p = get_list_filter_clause("d.year_actual", years, cast_type="int")
        clauses.append(c); params.extend(p)
        
        where_sql = " AND ".join(clauses)

        # KPIs (sidebar filters only)
        kpi_row = fetch_one(f"""
            SELECT
                COUNT(DISTINCT f.sk_user_id)             AS total_instructors,
                COUNT(DISTINCT f.sk_fact_session_id)     AS total_sessions,
                SUM(COALESCE(f.demo_session_count, 0))   AS demo_sessions,
                SUM(COALESCE(f.hands_on_session_count,0))AS hands_on_sessions
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_user u  ON f.sk_user_id = u.sk_user_id
            LEFT JOIN {DW}.dim_date d  ON f.date_id = d.date_id
            WHERE {where_sql}
        """, params)

        kpis = [
            {"label": "Instructors Reviewed",  "value": int(kpi_row.get("total_instructors", 0) or 0),  "icon": "fas fa-users",              "color": "bg-info"},
            {"label": "Total Sessions",        "value": int(kpi_row.get("total_sessions", 0) or 0),     "icon": "fas fa-chalkboard-teacher", "color": "bg-success"},
            {"label": "Demo Sessions",         "value": int(kpi_row.get("demo_sessions", 0) or 0),      "icon": "fas fa-flask",              "color": "bg-navy-blue"},
            {"label": "Hands-on Sessions",     "value": int(kpi_row.get("hands_on_sessions", 0) or 0),  "icon": "fas fa-hands",              "color": "bg-danger"},
        ]

        # DataTable Logic
        search_sql = "TRUE"
        search_params = []
        sort_sql = "ORDER BY d.full_date DESC"
        
        if dt_params:
            searchable_cols = ["COALESCE(u.user_name, 'Unknown')", "COALESCE(sc.school_name, 'Unknown')", "COALESCE(a.activity_name, 'Unknown')"]
            sortable_cols = ["instructor_name", "session_date", "school_name", "activity_name", "demo_sessions", "hands_on_sessions", "duration_minutes"]
            
            inner_search_sql, inner_search_params, inner_sort_sql = get_datatables_sql(dt_params, searchable_cols, sortable_cols)
            search_sql = inner_search_sql
            search_params = inner_search_params
            if inner_sort_sql:
                # Map frontend aliases to DB columns if needed
                mapping = {
                    "instructor_name": "u.user_name",
                    "session_date": "d.full_date",
                    "school_name": "sc.school_name",
                    "activity_name": "a.activity_name"
                }
                for alias, db_col in mapping.items():
                    inner_sort_sql = inner_sort_sql.replace(alias, db_col)
                sort_sql = inner_sort_sql

        total_count = fetch_one(f"""
            SELECT COUNT(DISTINCT f.sk_fact_session_id) AS count
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_user u          ON f.sk_user_id = u.sk_user_id
            LEFT JOIN {DW}.dim_date d          ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_school sc       ON f.sk_school_id = sc.sk_school_id
            LEFT JOIN {DW}.dim_activity_type a ON f.sk_activity_type_id = a.sk_activity_type_id
            WHERE {where_sql} AND {search_sql}
        """, params + search_params).get("count", 0)

        rows = fetch_all(f"""
            SELECT
                COALESCE(u.user_name, 'Unknown')                    AS instructor_name,
                d.full_date                                          AS session_date,
                COALESCE(
                    NULLIF(NULLIF(sc.school_name, 'NULL'), 'Unknown'), 
                    NULLIF(ra.village, ''), 
                    'N/A'
                ) AS school_name,
                COALESCE(a.activity_name, 'Unknown')                AS activity_name,
                COALESCE(f.demo_session_count, 0)                   AS demo_sessions,
                COALESCE(f.hands_on_session_count, 0)               AS hands_on_sessions,
                COALESCE(f.session_duration_minutes, 0)             AS duration_minutes
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_user u          ON f.sk_user_id = u.sk_user_id
            LEFT JOIN {DW}.dim_date d          ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_school sc       ON f.sk_school_id = sc.sk_school_id
            LEFT JOIN {DW}.dim_activity_type a ON f.sk_activity_type_id = a.sk_activity_type_id
            LEFT JOIN source.rpt_adhoc_feedback ra ON (f.session_nk_id - 1000000)::TEXT = ra.adhoc_id AND f.session_nk_id >= 1000000
            WHERE {where_sql} AND {search_sql}
            {sort_sql}
            LIMIT %s OFFSET %s
        """, params + search_params + [limit, offset])

        formatted = []
        for r in rows:
            row = dict(r)
            if row.get("session_date"):
                row["session_date"] = row["session_date"].strftime("%Y-%m-%d")
            formatted.append(row)

        return {"kpis": kpis, "table": formatted, "total_count": int(total_count)}
    except Exception as e:
        logger.error(f"instructor feedback data error: {e}", exc_info=True)
        return {"kpis": [], "table": [], "total_count": 0}
