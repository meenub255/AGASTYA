import logging
from backend.services.query_utils import fetch_all, fetch_one, build_standard_filters, get_list_filter_clause
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
        months = [{"id": r["month_actual"], "name": r["month_name"].strip()} for r in fetch_all(f"""
            SELECT DISTINCT d.month_actual, TO_CHAR(TO_DATE(d.month_actual::text,'MM'),'Month') AS month_name 
            FROM {DW}.dim_date d
            INNER JOIN {DW}.fact_session f ON d.date_id = f.date_id
            ORDER BY d.month_actual
        """)]
        quarters = [1, 2, 3, 4]
        return {"instructors": instructors, "years": years, "months": months, "quarters": quarters}
    except Exception as e:
        logger.error(f"instructor feedback filters error: {e}")
        return {"instructors": [], "years": [], "months": [], "quarters": []}


def get_instructor_feedback_data(instructor_name=None, years=None, month=None, quarter=None, limit=15, offset=0, dt_params=None):
    from backend.services.query_utils import build_standard_filters, calculate_ytd_kpis, get_datatables_sql
    try:
        kpi_defs = [
            {"key": "total_instructors", "label": "Instructors Reviewed", "sql": "COUNT(DISTINCT f.sk_user_id)", "icon": "fas fa-users", "color": "linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%)"},
            {"key": "total_sessions", "label": "Total Sessions", "sql": "COUNT(DISTINCT f.sk_fact_session_id)", "icon": "fas fa-chalkboard-teacher", "color": "linear-gradient(135deg, #22c55e 0%, #16a34a 100%)"},
            {"key": "demo_sessions", "label": "Demo Sessions", "sql": "SUM(COALESCE(f.demo_session_count, 0))", "icon": "fas fa-flask", "color": "linear-gradient(135deg, #001f3f 0%, #001226 100%)"},
            {"key": "hands_on_sessions", "label": "Hands-on Sessions", "sql": "SUM(COALESCE(f.hands_on_session_count, 0))", "icon": "fas fa-hands", "color": "linear-gradient(135deg, #dc3545 0%, #c82333 100%)"}
        ]
        
        from_clause = f"""
            {DW}.fact_session f
            LEFT JOIN {DW}.dim_user u ON f.sk_user_id = u.sk_user_id
            LEFT JOIN {DW}.dim_date d ON f.date_id = d.date_id
        """
        
        kpi_list, sparklines = calculate_ytd_kpis(
            kpi_defs=kpi_defs,
            from_clause=from_clause,
            years=years,
            month=month,
            quarter=quarter,
            region=None # instructor feedback filter doesn't have region on sidebar
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

        return {"kpis": kpi_list, "sparklines": sparklines, "table": formatted, "total_count": int(total_count)}
    except Exception as e:
        logger.error(f"instructor feedback data error: {e}", exc_info=True)
        return {"kpis": [], "table": [], "total_count": 0}


def get_instructor_feedback_insights(instructor_name=None, years=None, month=None, quarter=None):
    try:
        where_sql, params, _ = build_standard_filters(years=years, month=month, quarter=quarter)

        if instructor_name:
            c, p = get_list_filter_clause("u.user_name", instructor_name)
            if c != "TRUE":
                where_sql = f"{where_sql} AND {c}" if where_sql != "TRUE" else c
                params.extend(p)

        base_join = f"""
            {DW}.fact_session f
            LEFT JOIN {DW}.dim_user u ON f.sk_user_id = u.sk_user_id
            LEFT JOIN {DW}.dim_date d ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_school sc ON f.sk_school_id = sc.sk_school_id
            LEFT JOIN {DW}.dim_activity_type a ON f.sk_activity_type_id = a.sk_activity_type_id
        """

        def _q(sql, extra_params=None):
            return fetch_all(sql, params + (extra_params or []))

        kpis_row = _q(f"""
            SELECT
                COUNT(DISTINCT f.sk_fact_session_id) AS total_sessions,
                COUNT(DISTINCT f.sk_user_id) AS total_ignators,
                COUNT(DISTINCT f.sk_school_id) AS total_schools,
                SUM(COALESCE(f.demo_session_count, 0)) AS demo_sessions,
                SUM(COALESCE(f.hands_on_session_count, 0)) AS hands_on_sessions,
                ROUND(AVG(NULLIF(COALESCE(f.session_duration_minutes, 0), 0)), 0) AS avg_duration,
                SUM(COALESCE(f.no_of_teachers_participated, 0)) AS total_teachers,
                SUM(COALESCE(f.community_men_count, 0) + COALESCE(f.community_women_count, 0)) AS total_community
            FROM {base_join}
            WHERE {where_sql}
        """)
        k = dict(kpis_row[0]) if kpis_row else {}

        demo = int(k.get("demo_sessions") or 0)
        hands_on = int(k.get("hands_on_sessions") or 0)
        total_act = demo + hands_on
        k["demo_pct"] = round(demo / total_act * 100, 1) if total_act else 0
        k["hands_on_pct"] = round(hands_on / total_act * 100, 1) if total_act else 0

        monthly = _q(f"""
            SELECT
                d.year_actual, d.month_actual,
                TO_CHAR(d.full_date, 'Mon YYYY') AS label,
                COUNT(DISTINCT f.sk_fact_session_id) AS sessions,
                SUM(COALESCE(f.demo_session_count, 0)) AS demos,
                SUM(COALESCE(f.hands_on_session_count, 0)) AS hands_on,
                COUNT(DISTINCT f.sk_user_id) AS active_ignators
            FROM {base_join}
            WHERE {where_sql}
            GROUP BY d.year_actual, d.month_actual, TO_CHAR(d.full_date, 'Mon YYYY')
            ORDER BY d.year_actual, d.month_actual
        """)

        top_ignators = _q(f"""
            SELECT
                COALESCE(u.user_name, 'Unknown') AS name,
                COUNT(DISTINCT f.sk_fact_session_id) AS sessions,
                COUNT(DISTINCT f.sk_school_id) AS schools,
                SUM(COALESCE(f.demo_session_count, 0) + COALESCE(f.hands_on_session_count, 0)) AS activities,
                ROUND(AVG(NULLIF(COALESCE(f.session_duration_minutes, 0), 0)), 0) AS avg_duration,
                SUM(COALESCE(f.no_of_teachers_participated, 0)) AS teachers
            FROM {base_join}
            WHERE {where_sql} AND u.user_name IS NOT NULL
            GROUP BY u.user_name
            ORDER BY sessions DESC
            LIMIT 10
        """)

        activity_mix = _q(f"""
            SELECT
                COALESCE(a.activity_name, 'Unknown') AS name,
                COUNT(*) AS count
            FROM {base_join}
            WHERE {where_sql}
            GROUP BY a.activity_name
            ORDER BY count DESC
        """)

        school_top = _q(f"""
            SELECT
                COALESCE(sc.school_name, 'N/A') AS name,
                COUNT(DISTINCT f.sk_fact_session_id) AS sessions,
                COUNT(DISTINCT f.sk_user_id) AS ignators,
                SUM(COALESCE(f.no_of_teachers_participated, 0)) AS teachers
            FROM {base_join}
            WHERE {where_sql}
              AND COALESCE(NULLIF(sc.school_name, 'NULL'), 'Unknown') NOT IN ('Unknown', 'N/A')
            GROUP BY sc.school_name
            ORDER BY sessions DESC
            LIMIT 10
        """)

        region_data = _q(f"""
            SELECT
                COALESCE(g.region_name, 'Unknown') AS name,
                COUNT(DISTINCT f.sk_fact_session_id) AS sessions,
                COUNT(DISTINCT f.sk_school_id) AS schools,
                COUNT(DISTINCT f.sk_user_id) AS ignators
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_user u ON f.sk_user_id = u.sk_user_id
            LEFT JOIN {DW}.dim_date d ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_school sc ON f.sk_school_id = sc.sk_school_id
            LEFT JOIN {DW}.dim_activity_type a ON f.sk_activity_type_id = a.sk_activity_type_id
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            WHERE {where_sql}
            GROUP BY g.region_name
            ORDER BY sessions DESC
        """)

        ignator_deep = _q(f"""
            SELECT
                COALESCE(u.user_name, 'Unknown') AS name,
                COUNT(DISTINCT f.sk_fact_session_id) AS sessions,
                COUNT(DISTINCT f.sk_school_id) AS schools,
                SUM(COALESCE(f.demo_session_count, 0)) AS demo,
                SUM(COALESCE(f.hands_on_session_count, 0)) AS hands_on,
                ROUND(AVG(NULLIF(COALESCE(f.session_duration_minutes, 0), 0)), 0) AS avg_duration,
                SUM(COALESCE(f.no_of_teachers_participated, 0)) AS teachers,
                SUM(COALESCE(f.community_men_count, 0) + COALESCE(f.community_women_count, 0)) AS community
            FROM {base_join}
            WHERE {where_sql} AND u.user_name IS NOT NULL
            GROUP BY u.user_name
            ORDER BY sessions DESC
        """)

        return {
            "kpis": k,
            "monthly": monthly,
            "top_ignators": top_ignators,
            "activity_mix": activity_mix,
            "school_top": school_top,
            "region_data": region_data,
            "ignator_deep": ignator_deep,
        }
    except Exception as e:
        logger.error(f"instructor feedback insights error: {e}", exc_info=True)
        return {"kpis": {}, "monthly": [], "top_ignators": [], "activity_mix": [], "school_top": [], "region_data": [], "ignator_deep": []}
