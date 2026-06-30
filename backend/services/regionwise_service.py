import logging
from backend.services.query_utils import fetch_all, fetch_one, get_list_filter_clause
from backend.config import DATAMART_SCHEMA_NAME

logger = logging.getLogger(__name__)
DW = DATAMART_SCHEMA_NAME


def get_regionwise_filters(region_name=None):
    from backend.services.query_utils import get_list_filter_clause
    try:
        # INNER JOIN with fact_session to ensure data exists
        regions = [r["region_name"] for r in fetch_all(f"""
            SELECT DISTINCT g.region_name 
            FROM {DW}.dim_geography g
            INNER JOIN {DW}.fact_session f ON g.sk_geography_id = f.sk_geography_id
            WHERE g.region_name IS NOT NULL 
            ORDER BY g.region_name
        """)]
        
        where_sql, params = get_list_filter_clause("g.region_name", region_name)
        areas = [r["area_name"] for r in fetch_all(f"""
            SELECT DISTINCT g.area_name 
            FROM {DW}.dim_geography g
            INNER JOIN {DW}.fact_session f ON g.sk_geography_id = f.sk_geography_id
            WHERE {where_sql} AND g.area_name IS NOT NULL 
            ORDER BY g.area_name
        """, params)]
        
        years = [r["year_actual"] for r in fetch_all(f"""
            SELECT DISTINCT d.year_actual 
            FROM {DW}.dim_date d
            INNER JOIN {DW}.fact_session f ON d.date_id = f.date_id
            WHERE d.year_actual IS NOT NULL 
            ORDER BY d.year_actual DESC
        """)]
        months = [{"id": r["month_actual"], "name": r["month_name"].strip()} for r in fetch_all(f"""
            SELECT DISTINCT d.month_actual, TO_CHAR(TO_DATE(d.month_actual::text,'MM'),'Month') AS month_name 
            FROM {DW}.dim_date d
            INNER JOIN {DW}.fact_session f ON d.date_id = f.date_id
            ORDER BY d.month_actual
        """)]
        return {"regions": regions, "areas": areas, "years": years, "months": months, "quarters": [1, 2, 3, 4]}
    except Exception as e:
        logger.error(f"regionwise filters error: {e}")
        return {"regions": [], "areas": [], "years": [], "months": [], "quarters": []}


def get_regionwise_data(region=None, area=None, years=None, month=None, quarter=None, limit=15, offset=0, dt_params=None, group_by="month"):
    from backend.services.query_utils import build_standard_filters, calculate_ytd_kpis, get_datatables_sql, get_time_grouping_expressions
    try:
        kpi_defs = [
            {"key": "total_sessions", "label": "Total Sessions", "sql": "COUNT(DISTINCT f.sk_fact_session_id)", "icon": "fas fa-chalkboard-teacher", "color": "bg-info"},
            {"key": "total_schools", "label": "Total Schools", "sql": "COUNT(DISTINCT f.sk_school_id)", "icon": "fas fa-school", "color": "bg-success"},
            {"key": "total_exposure", "label": "Total Exposure", "sql": "COALESCE(SUM(e.total_exposure_count), 0)", "icon": "fas fa-user-graduate", "color": "bg-navy-blue"},
            {"key": "avg_duration", "label": "Avg Session (min)", "sql": "ROUND(AVG(COALESCE(f.session_duration_minutes, 0)), 1)", "icon": "fas fa-clock", "color": "bg-danger"}
        ]
        
        from_clause = f"""
            {DW}.fact_session f
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d       ON f.date_id = d.date_id
            LEFT JOIN {DW}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
        """
        
        kpi_list, sparklines = calculate_ytd_kpis(
            kpi_defs=kpi_defs,
            from_clause=from_clause,
            years=years,
            region=region,
            area=area,
            month=month,
            quarter=quarter
        )
        
        where_sql, params, max_month = build_standard_filters(
            years=years,
            region=region,
            area=area,
            month=month,
            quarter=quarter
        )

        # DataTables search and sort
        search_sql = "TRUE"
        search_params = []
        sort_sql = "ORDER BY sessions DESC"
        
        if dt_params:
            searchable_cols = ["g.region_name", "g.area_name", "p.program_name"]
            sortable_cols = ["region_name", "area_name", "program_name", "sessions", "schools", "exposure", "demo_sessions", "hands_on_sessions"]
            inner_search_sql, inner_search_params, inner_sort_sql = get_datatables_sql(dt_params, searchable_cols, sortable_cols)
            search_sql = inner_search_sql
            search_params = inner_search_params
            if inner_sort_sql:
                sort_sql = inner_sort_sql

        total_count = fetch_one(f"""
            SELECT COUNT(*) FROM (
                SELECT g.region_name, g.area_name, p.program_name
                FROM {DW}.fact_session f
                LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
                LEFT JOIN {DW}.dim_date d       ON f.date_id = d.date_id
                LEFT JOIN {DW}.dim_program p    ON f.sk_program_id = p.sk_program_id
                WHERE {where_sql} AND {search_sql}
                GROUP BY g.region_name, g.area_name, p.program_name
            ) AS sub
        """, params + search_params).get("count", 0)

        table = fetch_all(f"""
            SELECT
                COALESCE(g.region_name, 'Unknown')               AS region_name,
                COALESCE(g.area_name, 'Unknown')                 AS area_name,
                COALESCE(p.program_name, 'Unknown')              AS program_name,
                COUNT(DISTINCT f.sk_fact_session_id)             AS sessions,
                COUNT(DISTINCT f.sk_school_id)                   AS schools,
                COALESCE(SUM(e.total_exposure_count), 0)         AS exposure,
                SUM(COALESCE(f.demo_session_count, 0))           AS demo_sessions,
                SUM(COALESCE(f.hands_on_session_count, 0))       AS hands_on_sessions
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d       ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_program p    ON f.sk_program_id = p.sk_program_id
            LEFT JOIN {DW}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {where_sql} AND {search_sql}
            GROUP BY g.region_name, g.area_name, p.program_name
            {sort_sql}
            LIMIT %s OFFSET %s
        """, params + search_params + [limit, offset])

        # Chart 1: Sessions by Program (bar chart)
        sessions_by_program = fetch_all(f"""
            SELECT COALESCE(p.program_name, 'Unknown') AS label,
                   COUNT(DISTINCT f.sk_fact_session_id) AS value
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d       ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_program p    ON f.sk_program_id = p.sk_program_id
            WHERE {where_sql} AND p.program_name IS NOT NULL
            GROUP BY p.program_name ORDER BY value DESC LIMIT 10
        """, params)

        # Build a separate WHERE for the trend chart (no year default — show all years)
        trend_clauses = []
        trend_params = []
        if region:
            tc, tp = get_list_filter_clause("g.region_name", region)
            if tc != "TRUE":
                trend_clauses.append(tc); trend_params.extend(tp)
        if area:
            tc, tp = get_list_filter_clause("g.area_name", area)
            if tc != "TRUE":
                trend_clauses.append(tc); trend_params.extend(tp)
        trend_where = " AND ".join(trend_clauses) if trend_clauses else "TRUE"

        label_expr, sort_expr, grp_expr = get_time_grouping_expressions(group_by)

        # Chart 2: Exposure Trend (dynamic date grouping)
        exposure_by_month = fetch_all(f"""
            SELECT {label_expr} AS label,
                   COALESCE(SUM(e.total_exposure_count), 0) AS value
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d       ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_program p    ON f.sk_program_id = p.sk_program_id
            LEFT JOIN {DW}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {trend_where} AND d.full_date IS NOT NULL
            GROUP BY {label_expr}
            ORDER BY {sort_expr}
        """, trend_params)

        # Regional Summary table
        regional_summary = fetch_all(f"""
            SELECT
                COALESCE(g.region_name, 'Unknown') AS region,
                COALESCE(SUM(e.total_exposure_count), 0) AS total_exposures,
                COUNT(DISTINCT f.sk_fact_session_id) AS no_of_session,
                ROUND(COALESCE(SUM(e.total_exposure_count), 0) / NULLIF(COUNT(DISTINCT p.program_name), 0), 0) AS exp_pgm,
                ROUND(COALESCE(SUM(e.total_exposure_count), 0) / NULLIF(COUNT(DISTINCT f.sk_user_id), 0), 0) AS expo_ign,
                ROUND(COALESCE(SUM(e.total_exposure_count), 0) / NULLIF(COUNT(DISTINCT f.sk_fact_session_id), 0), 0) AS expo_session,
                ROUND(COUNT(DISTINCT f.sk_fact_session_id)::NUMERIC / NULLIF(COUNT(DISTINCT f.sk_user_id), 0), 0) AS session_ignator,
                COUNT(DISTINCT p.program_name) AS no_of_programs,
                COUNT(DISTINCT f.sk_user_id) AS no_of_ignator,
                COUNT(DISTINCT f.date_id) AS wd
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_program p ON f.sk_program_id = p.sk_program_id
            LEFT JOIN {DW}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            LEFT JOIN {DW}.dim_user u ON f.sk_user_id = u.sk_user_id
            WHERE {where_sql} AND g.region_name IS NOT NULL
            GROUP BY g.region_name
            ORDER BY total_exposures DESC
        """, params)

        return {
            "kpis": kpi_list,
            "sparklines": sparklines,
            "charts": {
                "sessions_by_program": [{"label": r["label"], "value": float(r["value"])} for r in sessions_by_program],
                "exposure_by_month":   [{"label": r["label"], "value": float(r["value"])} for r in exposure_by_month],
            },
            "regional_summary": regional_summary,
            "table": table,
            "total_count": int(total_count),
        }
    except Exception as e:
        logger.error(f"regionwise data error: {e}", exc_info=True)
        return {"kpis": [], "sparklines": {}, "charts": {}, "table": [], "total_count": 0}


def get_state_summary(region=None, area=None, years=None, month=None, quarter=None):
    from backend.services.query_utils import build_standard_filters
    try:
        where_sql, params, _ = build_standard_filters(years=years, region=region, area=area, month=month, quarter=quarter)

        STATE_MAP = {
            'SOUTH_KARNATAKA_1': 'Karnataka', 'SOUTH_KARNATAKA_2': 'Karnataka',
            'NORTH_KARNATAKA_1': 'Karnataka', 'NORTH_KARNATAKA_2': 'Karnataka',
            'Kuppam': 'Karnataka',
            'MAHARASHTRA_1': 'Maharashtra', 'MAHARASHTRA_2': 'Maharashtra',
            'AP_AND_TELANGANA': 'Telangana',
            'GUJARAT': 'Gujarat',
            'NORTH_1': 'Uttar Pradesh', 'NORTH_2': 'Uttar Pradesh',
            'TAMIL NADU': 'Tamil Nadu',
            'BTR': 'Assam',
        }

        rows = fetch_all(f"""
            SELECT
                COALESCE(g.region_name, 'Unknown') AS region_name,
                COALESCE(SUM(e.total_exposure_count), 0) AS total_exposures,
                COUNT(DISTINCT f.sk_fact_session_id) AS no_of_session,
                ROUND(COALESCE(SUM(e.total_exposure_count), 0) / NULLIF(COUNT(DISTINCT p.program_name), 0), 0) AS exp_pgm,
                ROUND(COALESCE(SUM(e.total_exposure_count), 0) / NULLIF(COUNT(DISTINCT f.sk_user_id), 0), 0) AS expo_ign,
                ROUND(COALESCE(SUM(e.total_exposure_count), 0) / NULLIF(COUNT(DISTINCT f.sk_fact_session_id), 0), 0) AS expo_session,
                COUNT(DISTINCT p.program_name) AS no_of_pgm,
                COUNT(DISTINCT f.sk_user_id) AS no_of_ign,
                COUNT(DISTINCT f.date_id) AS wd
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_program p ON f.sk_program_id = p.sk_program_id
            LEFT JOIN {DW}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {where_sql} AND g.region_name IS NOT NULL
            GROUP BY g.region_name
        """, params)

        state_agg = {}
        for row in rows:
            state = STATE_MAP.get(row["region_name"], row["region_name"])
            if state not in state_agg:
                state_agg[state] = {"total_exposures": 0, "no_of_session": 0, "no_of_pgm": 0, "no_of_ign": 0, "wd": 0}
            s = state_agg[state]
            s["total_exposures"] += int(row["total_exposures"]) or 0
            s["no_of_session"] += int(row["no_of_session"]) or 0
            s["no_of_pgm"] += int(row["no_of_pgm"]) or 0
            s["no_of_ign"] += int(row["no_of_ign"]) or 0
            s["wd"] = max(s["wd"], int(row["wd"]) or 0)

        result = []
        for state, vals in state_agg.items():
            e = vals["total_exposures"]
            pgm = vals["no_of_pgm"]
            ign = vals["no_of_ign"]
            sess = vals["no_of_session"]
            result.append({
                "state": state,
                "total_exposures": e,
                "no_of_session": sess,
                "exp_pgm": round(e / pgm) if pgm else 0,
                "expo_ign": round(e / ign) if ign else 0,
                "expo_session": round(e / sess) if sess else 0,
                "no_of_pgm": pgm,
                "no_of_ign": ign,
                "wd": vals["wd"],
            })

        result.sort(key=lambda x: x["total_exposures"], reverse=True)
        return result
    except Exception as e:
        logger.error(f"state summary error: {e}", exc_info=True)
        return []

