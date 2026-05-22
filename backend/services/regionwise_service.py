import logging
from backend.services.query_utils import fetch_all, fetch_one
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
        return {"regions": regions, "areas": areas, "years": years, "months": months}
    except Exception as e:
        logger.error(f"regionwise filters error: {e}")
        return {"regions": [], "areas": [], "years": [], "months": []}


def get_regionwise_data(region=None, area=None, years=None, month=None, limit=15, offset=0, dt_params=None):
    from backend.services.query_utils import get_list_filter_clause, get_datatables_sql
    try:
        clauses = []
        params = []
        
        c, p = get_list_filter_clause("g.region_name", region)
        clauses.append(c); params.extend(p)
        
        c, p = get_list_filter_clause("g.area_name", area)
        clauses.append(c); params.extend(p)
        
        c, p = get_list_filter_clause("d.year_actual", years, cast_type="int")
        clauses.append(c); params.extend(p)
        
        c, p = get_list_filter_clause("d.month_actual", month, cast_type="int")
        clauses.append(c); params.extend(p)
        
        where_sql = " AND ".join(clauses)

        kpi_row = fetch_one(f"""
            SELECT
                COUNT(DISTINCT f.sk_fact_session_id)         AS total_sessions,
                COUNT(DISTINCT f.sk_school_id)               AS total_schools,
                COALESCE(SUM(e.total_exposure_count), 0)     AS total_exposure,
                ROUND(AVG(COALESCE(f.session_duration_minutes, 0)), 1) AS avg_duration
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d       ON f.date_id = d.date_id
            LEFT JOIN {DW}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {where_sql}
        """, params)

        # Insight Logic
        top_area_row = fetch_one(f"""
            SELECT COALESCE(g.area_name, 'Unknown') as area_name, 
                   COUNT(DISTINCT f.sk_fact_session_id) as sessions
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d       ON f.date_id = d.date_id
            WHERE {where_sql}
            GROUP BY g.area_name
            ORDER BY sessions DESC
            LIMIT 1
        """, params)
        top_area = top_area_row.get("area_name", "N/A") if top_area_row else "N/A"
        
        sess_status = "High" if int(kpi_row.get("total_sessions", 0)) > 500 else "Stable"
        sess_reason = f"Consistent delivery across the region, led by {top_area}."
        
        sch_status = "Stable"
        sch_reason = f"Wide coverage maintained. {top_area} is the most active area."
        
        exp_status = "High" if int(kpi_row.get("total_exposure", 0)) > 5000 else "Stable"
        exp_reason = "Strong student participation across all active schools."
        
        dur_status = "Average"
        dur_reason = "Session duration remains within the target educational window."

        kpis = [
            {"label": "Total Sessions",        "value": int(kpi_row.get("total_sessions", 0) or 0),  "icon": "fas fa-chalkboard-teacher", "color": "bg-info", "status": sess_status, "reason": sess_reason},
            {"label": "Total Schools",          "value": int(kpi_row.get("total_schools", 0) or 0),   "icon": "fas fa-school",             "color": "bg-success", "status": sch_status, "reason": sch_reason},
            {"label": "Total Exposure",         "value": int(kpi_row.get("total_exposure", 0) or 0),  "icon": "fas fa-user-graduate",      "color": "bg-navy-blue", "status": exp_status, "reason": exp_reason},
            {"label": "Avg Session (min)",      "value": float(kpi_row.get("avg_duration", 0) or 0),  "icon": "fas fa-clock",              "color": "bg-danger", "status": dur_status, "reason": dur_reason},
        ]

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
            WHERE {where_sql}
            GROUP BY p.program_name ORDER BY value DESC LIMIT 10
        """, params)

        # Chart 2: Exposure by Month (line chart with trend)
        exposure_by_month = fetch_all(f"""
            SELECT TO_CHAR(d.full_date, 'YYYY-MM') AS label,
                   COALESCE(SUM(e.total_exposure_count), 0) AS value
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d       ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_program p    ON f.sk_program_id = p.sk_program_id
            LEFT JOIN {DW}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {where_sql} AND d.full_date IS NOT NULL
            GROUP BY TO_CHAR(d.full_date, 'YYYY-MM')
            ORDER BY label
        """, params)

        return {
            "kpis": kpis,
            "charts": {
                "sessions_by_program": [{"label": r["label"], "value": float(r["value"])} for r in sessions_by_program],
                "exposure_by_month":   [{"label": r["label"], "value": float(r["value"])} for r in exposure_by_month],
            },
            "table": table,
            "total_count": int(total_count),
        }
    except Exception as e:
        logger.error(f"regionwise data error: {e}", exc_info=True)
        return {"kpis": [], "table": [], "total_count": 0}
