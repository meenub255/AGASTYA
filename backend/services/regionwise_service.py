import logging
from backend.services.query_utils import fetch_all, fetch_one
from backend.config import DATAMART_SCHEMA_NAME

logger = logging.getLogger(__name__)
DW = DATAMART_SCHEMA_NAME


def get_regionwise_filters(region_name=None):
    try:
        regions = [r["region_name"] for r in fetch_all(
            f"SELECT DISTINCT region_name FROM {DW}.dim_geography WHERE region_name IS NOT NULL ORDER BY region_name"
        )]
        areas = []
        if region_name:
            areas = [r["area_name"] for r in fetch_all(
                f"SELECT DISTINCT area_name FROM {DW}.dim_geography WHERE region_name = %s AND area_name IS NOT NULL ORDER BY area_name",
                [region_name]
            )]
        years = [r["year_actual"] for r in fetch_all(
            f"SELECT DISTINCT year_actual FROM {DW}.dim_date WHERE year_actual IS NOT NULL ORDER BY year_actual DESC"
        )]
        months = [{"id": r["month_actual"], "name": r["month_name"].strip()} for r in fetch_all(
            f"SELECT DISTINCT month_actual, TO_CHAR(TO_DATE(month_actual::text,'MM'),'Month') AS month_name FROM {DW}.dim_date ORDER BY month_actual"
        )]
        return {"regions": regions, "areas": areas, "years": years, "months": months}
    except Exception as e:
        logger.error(f"regionwise filters error: {e}")
        return {"regions": [], "areas": [], "years": [], "months": []}


def get_regionwise_data(region=None, area=None, year=None, month=None, limit=15, offset=0, dt_params=None):
    try:
        where_clauses = ["TRUE"]
        params = []
        if region:
            where_clauses.append("g.region_name = %s")
            params.append(region)
        if area:
            where_clauses.append("g.area_name = %s")
            params.append(area)
        if year:
            where_clauses.append("d.year_actual = %s")
            params.append(int(year))
        if month:
            where_clauses.append("d.month_actual = %s")
            params.append(int(month))
        where_sql = " AND ".join(where_clauses)

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

        kpis = [
            {"label": "Total Sessions",        "value": int(kpi_row.get("total_sessions", 0) or 0),  "icon": "fas fa-chalkboard-teacher", "color": "bg-info"},
            {"label": "Total Schools",          "value": int(kpi_row.get("total_schools", 0) or 0),   "icon": "fas fa-school",             "color": "bg-success"},
            {"label": "Total Exposure",         "value": int(kpi_row.get("total_exposure", 0) or 0),  "icon": "fas fa-user-graduate",      "color": "bg-navy-blue"},
            {"label": "Avg Session (min)",      "value": float(kpi_row.get("avg_duration", 0) or 0),  "icon": "fas fa-clock",              "color": "bg-danger"},
        ]

        total_count = fetch_one(f"""
            SELECT COUNT(*) FROM (
                SELECT g.region_name, g.area_name, p.program_name
                FROM {DW}.fact_session f
                LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
                LEFT JOIN {DW}.dim_date d       ON f.date_id = d.date_id
                LEFT JOIN {DW}.dim_program p    ON f.sk_program_id = p.sk_program_id
                WHERE {where_sql}
                GROUP BY g.region_name, g.area_name, p.program_name
            ) AS sub
        """, params).get("count", 0)

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
            WHERE {where_sql}
            GROUP BY g.region_name, g.area_name, p.program_name
            ORDER BY sessions DESC
            LIMIT %s OFFSET %s
        """, params + [limit, offset])

        return {"kpis": kpis, "table": table, "total_count": int(total_count)}
    except Exception as e:
        logger.error(f"regionwise data error: {e}", exc_info=True)
        return {"kpis": [], "table": [], "total_count": 0}
