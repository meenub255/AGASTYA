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
            WHERE {where_sql}
            GROUP BY p.program_name ORDER BY value DESC LIMIT 10
        """, params)

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
            WHERE {where_sql} AND d.full_date IS NOT NULL
            GROUP BY {grp_expr}
            ORDER BY {sort_expr}
        """, params)

        return {
            "kpis": kpi_list,
            "sparklines": sparklines,
            "charts": {
                "sessions_by_program": [{"label": r["label"], "value": float(r["value"])} for r in sessions_by_program],
                "exposure_by_month":   [{"label": r["label"], "value": float(r["value"])} for r in exposure_by_month],
            },
            "table": table,
            "total_count": int(total_count),
        }
    except Exception as e:
        logger.error(f"regionwise data error: {e}", exc_info=True)
        return {"kpis": [], "sparklines": {}, "charts": {}, "table": [], "total_count": 0}

